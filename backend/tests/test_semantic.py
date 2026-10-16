"""Tests for embeddings, semantic search and hybrid (RRF) search.

A tiny fake embedder (hashed bag of words) stands in for the real model so the
tests run without the 470 MB download. One test uses the real model when it is present.
Database tests use a synthetic fixture PDF and are skipped when no database is running.
"""

import hashlib
import re

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import embed, embeddings, ingest, main
from app.db import connect, init_schema
from app.main import app, reciprocal_rank_fusion

KEY = "pytest-semantic-fixture"


class FakeEmbedder:
    """Deterministic stand-in: each word adds 1 to a hashed dimension, then L2-normalise."""

    name = "fake-test-embedder"

    def _embed(self, texts):
        out = np.zeros((len(texts), embeddings.EMBED_DIM))
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % embeddings.EMBED_DIM] += 1
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)

    embed_queries = embed_passages = _embed


# ---------- pure functions ----------

def test_rrf_scores_are_sum_of_reciprocal_ranks():
    fused = dict(reciprocal_rank_fusion([1, 2, 3], [3, 4], k=60))
    assert fused[3] == pytest.approx(1 / 63 + 1 / 61)
    assert fused[1] == pytest.approx(1 / 61)
    assert fused[4] == pytest.approx(1 / 62)


def test_rrf_rewards_agreement_between_methods():
    order = [cid for cid, _ in reciprocal_rank_fusion([10, 20, 30], [30, 40, 50])]
    assert order[0] == 30            # found by both lists beats a single first place
    assert set(order) == {10, 20, 30, 40, 50}  # no duplicates, nothing lost


def test_to_pgvector_formats_every_dimension():
    text = embed.to_pgvector(np.array([0.5, -0.25, 1e-8]))
    assert text.startswith("[") and text.endswith("]")
    assert [float(x) for x in text[1:-1].split(",")] == pytest.approx([0.5, -0.25, 1e-8])


@pytest.mark.skipif(not (embeddings.model_dir() / "onnx" / "model.onnx").exists(), reason="embedding model not downloaded")
def test_real_model_puts_paraphrase_closer_than_unrelated_text():
    e = embeddings.E5Embedder(embeddings.model_dir())
    q = e.embed_queries(["Who cleaned the silt out of village tanks?"])[0]
    p = e.embed_passages(["Farmers removed sediment from the tank bed every summer.", "The stock market closed higher today."])
    assert p.shape == (2, embeddings.EMBED_DIM)
    assert np.linalg.norm(p, axis=1) == pytest.approx([1.0, 1.0])
    assert q @ p[0] > q @ p[1]


# ---------- database-backed ----------

@pytest.fixture()
def conn():
    try:
        c = connect()
    except psycopg.OperationalError:
        pytest.skip("database not available")
    init_schema(c)
    yield c
    c.execute("DELETE FROM documents WHERE source_key = %s", (KEY,))
    c.commit()
    c.close()


@pytest.fixture()
def fixture_doc(conn, tmp_path, monkeypatch):
    import pymupdf

    pdf = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Synthetic page one about zqsluice gates opened by the zqwarden.")
    doc.new_page().insert_text((72, 72), "Synthetic page two about zqsilt removal from the zqtank bed.")
    doc.save(pdf)
    monkeypatch.setattr(ingest, "REPO_ROOT", tmp_path)
    entry = {"source_key": KEY, "file": "fixture.pdf", "title": "Semantic fixture", "authors": ["Nobody"],
             "source_url": "https://example.org/fixture.pdf"}
    assert ingest.ingest_entry(conn, entry, force=True).startswith("ok")
    doc_id = conn.execute("SELECT id FROM documents WHERE source_key = %s", (KEY,)).fetchone()["id"]
    fake = FakeEmbedder()
    monkeypatch.setattr(main, "get_embedder", lambda: fake)
    return doc_id, fake


def fixture_hits(body):
    return [h for h in body["hits"] if h["document"]["source_key"] == KEY]


def test_embedding_is_incremental(conn, fixture_doc):
    doc_id, fake = fixture_doc
    assert embed.embed_missing(conn, fake, document_ids=[doc_id]) == 2
    assert embed.embed_missing(conn, fake, document_ids=[doc_id]) == 0   # nothing recomputed
    assert embed.embed_missing(conn, fake, force=True, document_ids=[doc_id]) == 2
    rows = conn.execute("SELECT embedding_model, vector_dims(embedding) AS dims FROM chunks WHERE document_id = %s", (doc_id,)).fetchall()
    assert all(r["embedding_model"] == fake.name and r["dims"] == embeddings.EMBED_DIM for r in rows)


def test_reingest_clears_vectors_so_they_are_recomputed(conn, fixture_doc, tmp_path):
    doc_id, fake = fixture_doc
    embed.embed_missing(conn, fake, document_ids=[doc_id])
    entry = {"source_key": KEY, "file": "fixture.pdf", "title": "Semantic fixture"}
    ingest.ingest_entry(conn, entry, force=True)
    assert embed.embed_missing(conn, fake, document_ids=[doc_id]) == 2


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_semantic_and_hybrid_keep_page_and_source_citation(conn, fixture_doc, mode):
    doc_id, fake = fixture_doc
    embed.embed_missing(conn, fake, document_ids=[doc_id])
    body = TestClient(app).get("/api/search", params={"q": "zqsilt zqtank", "mode": mode, "limit": 50}).json()
    hits = fixture_hits(body)
    assert hits, body
    assert hits[0]["page_number"] == 2
    assert hits[0]["document"]["title"] == "Semantic fixture"
    assert hits[0]["document"]["source_url"] == "https://example.org/fixture.pdf"
    assert body["method"] == {"semantic": "semantic", "hybrid": "hybrid-rrf"}[mode]
    assert len({h["chunk_id"] for h in body["hits"]}) == len(body["hits"])  # no duplicate chunks


def test_keyword_mode_is_unchanged_default(conn, fixture_doc):
    body = TestClient(app).get("/api/search", params={"q": "zqsilt"}).json()
    assert body["method"] == "keyword-all"
    assert [h["page_number"] for h in fixture_hits(body)] == [2]


def test_empty_query_is_rejected(conn):
    client = TestClient(app)
    assert client.get("/api/search", params={"q": "   "}).status_code == 422
    assert client.get("/api/search", params={"q": ""}).status_code == 422


def test_semantic_without_embeddings_returns_clear_error(conn, monkeypatch):
    class NeverUsedModel(FakeEmbedder):
        name = "model-with-no-vectors"

    monkeypatch.setattr(main, "get_embedder", lambda: NeverUsedModel())
    res = TestClient(app).get("/api/search", params={"q": "tank", "mode": "semantic"})
    assert res.status_code == 503 and "python -m app.embed" in res.json()["detail"]


def test_missing_model_files_return_clear_error(conn, monkeypatch):
    def missing():
        raise embeddings.ModelMissingError("embedding model not found. Run: python -m app.embed")

    monkeypatch.setattr(main, "get_embedder", missing)
    res = TestClient(app).get("/api/search", params={"q": "tank", "mode": "hybrid"})
    assert res.status_code == 503 and "app.embed" in res.json()["detail"]


def test_database_down_returns_503(monkeypatch):
    def broken():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "connect", broken)
    res = TestClient(app).get("/api/search", params={"q": "tank"})
    assert res.status_code == 503 and "Database unavailable" in res.json()["detail"]

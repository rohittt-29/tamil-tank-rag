"""End-to-end test: build a small PDF, ingest it into Postgres, search via the API.

The PDF text below is a synthetic test fixture, not a real source document.
Needs a running database (DATABASE_URL); skipped otherwise.
"""

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import ingest
from app.db import connect, init_schema
from app.main import HL_START, app

KEY = "pytest-fixture"


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
def fixture_entry(tmp_path, monkeypatch):
    pdf = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Synthetic page one about sluice gates.")
    doc.new_page().insert_text((72, 72), "Synthetic page two about qwfixture desilting the tank bed.")
    doc.save(pdf)
    monkeypatch.setattr(ingest, "REPO_ROOT", tmp_path)
    return {"source_key": KEY, "file": "fixture.pdf", "title": "Test fixture", "authors": ["Nobody"]}


def test_ingest_then_search_returns_page_reference(conn, fixture_entry):
    assert ingest.ingest_entry(conn, fixture_entry).startswith("ok")
    assert ingest.ingest_entry(conn, fixture_entry).startswith("skip")  # idempotent

    client = TestClient(app)
    body = client.get("/api/search", params={"q": "qwfixture desilting"}).json()
    hits = [h for h in body["hits"] if h["document"]["title"] == "Test fixture"]
    assert len(hits) == 1
    assert hits[0]["page_number"] == 2
    assert HL_START in hits[0]["snippet"]


def test_missing_file_is_recorded_as_failed(conn, fixture_entry):
    fixture_entry["file"] = "does-not-exist.pdf"
    assert ingest.ingest_entry(conn, fixture_entry).startswith("FAILED")
    status = conn.execute("SELECT status, error FROM documents WHERE source_key = %s", (KEY,)).fetchone()
    assert status["status"] == "failed" and "not found" in status["error"]


def test_drop_overlapping_neighbours_keeps_best_of_adjacent_chunks():
    from app.main import drop_overlapping_neighbours

    rows = [{"id": 1, "chunk_index": 5}, {"id": 1, "chunk_index": 4}, {"id": 1, "chunk_index": 9}, {"id": 2, "chunk_index": 4}]
    assert drop_overlapping_neighbours(rows) == [rows[0], rows[2], rows[3]]

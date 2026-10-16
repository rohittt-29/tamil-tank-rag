"""HTTP API: keyword, semantic and hybrid search over ingested chunks, plus the document list."""

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .db import connect
from .embed import to_pgvector
from .embeddings import ModelMissingError, get_embedder

app = FastAPI(title="Tamil Tank Irrigation Knowledge API", version="0.2.0")

# ts_headline marks matched words with these markers; the frontend turns them into <mark>.
HL_START, HL_STOP = "\u0002", "\u0003"


class Document(BaseModel):
    id: int
    source_key: str
    title: str
    authors: list[str]
    year: int | None
    language: str
    source_org: str | None
    source_url: str | None
    doi: str | None
    license: str | None
    page_count: int | None
    status: str
    error: str | None


class SearchHit(BaseModel):
    chunk_id: int
    page_number: int
    section: str
    snippet: str  # contains HL_START / HL_STOP markers around matched terms
    score: float  # keyword: ts_rank_cd · semantic: cosine similarity · hybrid: RRF score
    document: Document


class SearchResponse(BaseModel):
    query: str
    method: str
    total: int
    hits: list[SearchHit]
    warning: str | None = None


DOC_COLUMNS = (
    "d.id, d.source_key, d.title, d.authors, d.year, d.language, d.source_org, d.source_url, "
    "d.doi, d.license, d.page_count, d.status, d.error"
)
CHUNK_COLUMNS = "c.id AS chunk_id, c.page_number, c.chunk_index, c.section"
HEADLINE = f"ts_headline('english', c.text, query.tsq, 'StartSel={HL_START}, StopSel={HL_STOP}, MaxWords=45, MinWords=20, MaxFragments=2') AS snippet"

# Turns the user's text into a tsquery. "all": every word must match (websearch syntax).
# "any": word1 | word2 | ..., so long questions still match and ranking rewards more matched words.
QUERY_CTE = """
    WITH parsed AS (SELECT websearch_to_tsquery('english', %(q)s) AS tsq),
    query AS (
        SELECT CASE WHEN %(any)s AND tsq::text <> ''
                    THEN replace(plainto_tsquery('english', %(q)s)::text, '&', '|')::tsquery
                    ELSE tsq END AS tsq
        FROM parsed
    )
"""

# Upper bound on matching chunks considered per query before de-duplication.
# Fine for a corpus of tens of documents; revisit when the collection grows.
MAX_CANDIDATES = 500
# Hybrid search fuses the top RRF_DEPTH results of each method.
RRF_DEPTH = 50
# Standard Reciprocal Rank Fusion constant (Cormack et al., 2009); larger k flattens rank differences.
RRF_K = 60


@app.exception_handler(psycopg.OperationalError)
def database_unavailable(_: Request, exc: psycopg.OperationalError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"Database unavailable: {exc}".strip()})


@app.get("/api/health")
def health() -> dict:
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/documents", response_model=list[Document])
def list_documents() -> list[dict]:
    with connect() as conn:
        return conn.execute(f"SELECT {DOC_COLUMNS} FROM documents d ORDER BY d.id").fetchall()


def drop_overlapping_neighbours(rows: list[dict]) -> list[dict]:
    """Keep the best-ranked of any two hits that are adjacent chunks of one document.

    Neighbouring chunks share 30 words of overlap, so they often match the same
    sentence; showing both looks like a duplicate result. Rows must be sorted best first.
    """
    kept: list[dict] = []
    taken: set[tuple[int, int]] = set()
    for r in rows:
        key = (r["id"], r["chunk_index"])
        if (r["id"], r["chunk_index"] - 1) in taken or (r["id"], r["chunk_index"] + 1) in taken:
            continue
        taken.add(key)
        kept.append(r)
    return kept


def reciprocal_rank_fusion(*rankings: list[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Merge ranked lists of ids: score(id) = sum over lists of 1 / (k + rank), rank starting at 1.

    Uses only ranks, so the very different score scales of keyword ranking and cosine
    similarity never need to be normalised against each other. Ties keep a stable order.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def keyword_rows(conn: psycopg.Connection, q: str, refs: bool, any_words: bool, limit: int) -> list[dict]:
    sql = f"""{QUERY_CTE}
        SELECT {CHUNK_COLUMNS}, ts_rank_cd(c.tsv, query.tsq) AS score, {HEADLINE}, {DOC_COLUMNS}
        FROM chunks c JOIN documents d ON d.id = c.document_id, query
        WHERE c.tsv @@ query.tsq AND (%(refs)s OR c.section = 'body')
        ORDER BY score DESC, c.id
        LIMIT %(max)s
    """
    return conn.execute(sql, {"q": q, "refs": refs, "any": any_words, "max": limit}).fetchall()


def embedding_coverage(conn: psycopg.Connection, model: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT count(*) AS n, count(*) FILTER (WHERE embedding_model = %s AND embedding IS NOT NULL) AS e FROM chunks",
        (model,),
    ).fetchone()
    return row["e"], row["n"]


def semantic_rows(conn: psycopg.Connection, q: str, refs: bool, limit: int, model: str, vector: str) -> list[dict]:
    # The snippet still highlights any query words that happen to appear in the passage.
    sql = f"""{QUERY_CTE}
        SELECT {CHUNK_COLUMNS}, 1 - (c.embedding <=> %(v)s::vector) AS score, {HEADLINE}, {DOC_COLUMNS}
        FROM chunks c JOIN documents d ON d.id = c.document_id, query
        WHERE c.embedding IS NOT NULL AND c.embedding_model = %(model)s AND (%(refs)s OR c.section = 'body')
        ORDER BY c.embedding <=> %(v)s::vector, c.id
        LIMIT %(max)s
    """
    return conn.execute(sql, {"q": q, "refs": refs, "any": True, "v": vector, "model": model, "max": limit}).fetchall()


def to_hit(r: dict) -> dict:
    doc_keys = Document.model_fields.keys()
    return {
        "chunk_id": r["chunk_id"],
        "page_number": r["page_number"],
        "section": r["section"],
        "snippet": r["snippet"],
        "score": r["score"],
        "document": {k: r[k] for k in doc_keys},
    }


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=300),
    limit: int = Query(10, ge=1, le=50),
    include_references: bool = Query(False, description="also search bibliography sections"),
    match: str = Query("all", pattern="^(all|any)$", description="keyword mode only. all: every word must appear; any: at least one"),
    mode: str = Query("keyword", pattern="^(keyword|semantic|hybrid)$", description="keyword (default), semantic or hybrid"),
) -> dict:
    """Search the collection. Every hit carries its document metadata and page number.

    keyword:  Postgres full-text search (websearch_to_tsquery + ts_rank_cd).
    semantic: cosine similarity between multilingual-e5-small embeddings (pgvector).
    hybrid:   Reciprocal Rank Fusion of keyword ("any" words) and semantic top-50 lists.
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Query is empty.")
    warning = None
    with connect() as conn:
        if mode == "keyword":
            rows = keyword_rows(conn, q, include_references, match == "any", MAX_CANDIDATES)
            method = f"keyword-{match}"
        else:
            try:
                embedder = get_embedder()
            except ModelMissingError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            have, total = embedding_coverage(conn, embedder.name)
            if have == 0:
                raise HTTPException(status_code=503, detail="No chunk embeddings yet. Run: python -m app.embed")
            if have < total:
                warning = f"{total - have} of {total} passages have no embedding yet and are missing from semantic results. Run: python -m app.embed"
            vector = to_pgvector(embedder.embed_queries([q])[0])
            if mode == "semantic":
                rows = semantic_rows(conn, q, include_references, MAX_CANDIDATES, embedder.name, vector)
                method = "semantic"
            else:
                kw = keyword_rows(conn, q, include_references, True, RRF_DEPTH)
                sem = semantic_rows(conn, q, include_references, RRF_DEPTH, embedder.name, vector)
                by_id = {r["chunk_id"]: r for r in sem} | {r["chunk_id"]: r for r in kw}  # keyword snippet preferred
                fused = reciprocal_rank_fusion([r["chunk_id"] for r in kw], [r["chunk_id"] for r in sem])
                rows = [{**by_id[cid], "score": score} for cid, score in fused]
                method = "hybrid-rrf"
    rows = drop_overlapping_neighbours(rows)
    return {"query": q, "method": method, "total": len(rows), "hits": [to_hit(r) for r in rows[:limit]], "warning": warning}

"""HTTP API: keyword search over ingested chunks, plus the document list."""

from fastapi import FastAPI, Query
from pydantic import BaseModel

from .db import connect

app = FastAPI(title="Tamil Tank Irrigation Knowledge API", version="0.1.0")

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
    score: float
    document: Document


class SearchResponse(BaseModel):
    query: str
    method: str
    total: int
    hits: list[SearchHit]


DOC_COLUMNS = (
    "d.id, d.source_key, d.title, d.authors, d.year, d.language, d.source_org, d.source_url, "
    "d.doi, d.license, d.page_count, d.status, d.error"
)


@app.get("/api/health")
def health() -> dict:
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/documents", response_model=list[Document])
def list_documents() -> list[dict]:
    with connect() as conn:
        return conn.execute(f"SELECT {DOC_COLUMNS} FROM documents d ORDER BY d.id").fetchall()


# Upper bound on matching chunks considered per query before de-duplication.
# Fine for a corpus of tens of documents; revisit when the collection grows.
MAX_CANDIDATES = 500


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


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=300),
    limit: int = Query(10, ge=1, le=50),
    include_references: bool = Query(False, description="also search bibliography sections"),
    match: str = Query("all", pattern="^(all|any)$", description="all: every word must appear; any: at least one"),
) -> dict:
    """Keyword (BM25-like) search using Postgres full-text search.

    websearch_to_tsquery accepts Google-style input: quoted phrases, OR, -exclude.
    ts_rank_cd ranks by how often and how close together the query terms appear.
    match="any" turns the query into word1 | word2 | ... so long natural-language
    questions still return results (ranking then rewards chunks matching more words).
    """
    sql = f"""
        WITH parsed AS (SELECT websearch_to_tsquery('english', %(q)s) AS tsq),
        query AS (
            SELECT CASE WHEN %(any)s AND tsq::text <> ''
                        THEN replace(plainto_tsquery('english', %(q)s)::text, '&', '|')::tsquery
                        ELSE tsq END AS tsq
            FROM parsed
        )
        SELECT c.id AS chunk_id, c.page_number, c.chunk_index, c.section,
               ts_rank_cd(c.tsv, query.tsq) AS score,
               ts_headline('english', c.text, query.tsq,
                           'StartSel={HL_START}, StopSel={HL_STOP}, MaxWords=45, MinWords=20, MaxFragments=2'
                          ) AS snippet,
               {DOC_COLUMNS}
        FROM chunks c JOIN documents d ON d.id = c.document_id, query
        WHERE c.tsv @@ query.tsq AND (%(refs)s OR c.section = 'body')
        ORDER BY score DESC, c.id
        LIMIT %(max)s
    """
    with connect() as conn:
        rows = conn.execute(sql, {"q": q, "refs": include_references, "any": match == "any", "max": MAX_CANDIDATES}).fetchall()
    rows = drop_overlapping_neighbours(rows)
    doc_keys = Document.model_fields.keys()
    hits = [
        {
            "chunk_id": r["chunk_id"],
            "page_number": r["page_number"],
            "section": r["section"],
            "snippet": r["snippet"],
            "score": r["score"],
            "document": {k: r[k] for k in doc_keys},
        }
        for r in rows[:limit]
    ]
    return {"query": q, "method": f"keyword-{match}", "total": len(rows), "hits": hits}

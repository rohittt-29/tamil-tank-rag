"""Ingest the documents listed in data/manifest.json.

Usage (from backend/):
    python -m app.ingest              # ingest new or changed documents
    python -m app.ingest --force      # re-process everything

Safe to re-run: a document whose file hash has not changed is skipped, and a
changed document has its old chunks replaced inside one transaction.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import psycopg

from .config import REPO_ROOT, settings
from .db import connect, init_schema
from .textproc import chunk_document, extract_pages

MANIFEST = REPO_ROOT / "data" / "manifest.json"

METADATA_FIELDS = ("title", "authors", "year", "language", "source_org", "source_url", "doi", "license")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def upsert_document(conn: psycopg.Connection, entry: dict) -> dict:
    meta = {k: entry.get(k) for k in METADATA_FIELDS}
    meta["authors"] = meta["authors"] or []
    meta["language"] = meta["language"] or "en"
    return conn.execute(
        """
        INSERT INTO documents (source_key, file_path, title, authors, year, language,
                               source_org, source_url, doi, license)
        VALUES (%(source_key)s, %(file_path)s, %(title)s, %(authors)s, %(year)s, %(language)s,
                %(source_org)s, %(source_url)s, %(doi)s, %(license)s)
        ON CONFLICT (source_key) DO UPDATE SET
            file_path = EXCLUDED.file_path, title = EXCLUDED.title, authors = EXCLUDED.authors,
            year = EXCLUDED.year, language = EXCLUDED.language, source_org = EXCLUDED.source_org,
            source_url = EXCLUDED.source_url, doi = EXCLUDED.doi, license = EXCLUDED.license,
            updated_at = now()
        RETURNING id, sha256, status
        """,
        {"source_key": entry["source_key"], "file_path": entry["file"], **meta},
    ).fetchone()


def process(conn: psycopg.Connection, doc_id: int, pdf: Path, digest: str) -> int:
    pages = extract_pages(pdf)
    chunks = chunk_document(pages, settings.chunk_words, settings.chunk_overlap)
    if not chunks:
        raise ValueError("no extractable text (scanned PDF? OCR is not implemented yet)")
    with conn.transaction():
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, page_number, chunk_index, section, text) VALUES (%s, %s, %s, %s, %s)",
                [(doc_id, c.page_number, i, c.section, c.text) for i, c in enumerate(chunks)],
            )
        conn.execute(
            "UPDATE documents SET status = 'done', error = NULL, sha256 = %s, page_count = %s, "
            "updated_at = now() WHERE id = %s",
            (digest, len(pages), doc_id),
        )
    return len(chunks)


def ingest_entry(conn: psycopg.Connection, entry: dict, force: bool = False) -> str:
    pdf = REPO_ROOT / entry["file"]
    with conn.transaction():
        doc = upsert_document(conn, entry)
    if not pdf.exists():
        conn.execute(
            "UPDATE documents SET status = 'failed', error = %s WHERE id = %s",
            (f"file not found: {entry['file']}", doc["id"]),
        )
        conn.commit()
        return f"FAILED  {entry['source_key']}: file not found ({entry['file']})"

    digest = sha256_of(pdf)
    if not force and doc["status"] == "done" and doc["sha256"] == digest:
        return f"skip    {entry['source_key']}: unchanged"
    if entry.get("sha256") and entry["sha256"] != digest:
        msg = "file hash differs from manifest sha256"
        conn.execute("UPDATE documents SET status = 'failed', error = %s WHERE id = %s", (msg, doc["id"]))
        conn.commit()
        return f"FAILED  {entry['source_key']}: {msg}"

    conn.execute("UPDATE documents SET status = 'processing' WHERE id = %s", (doc["id"],))
    conn.commit()
    try:
        n = process(conn, doc["id"], pdf, digest)
        return f"ok      {entry['source_key']}: {n} chunks"
    except Exception as exc:  # record the error on the document instead of crashing the batch
        conn.rollback()
        conn.execute("UPDATE documents SET status = 'failed', error = %s WHERE id = %s", (str(exc), doc["id"]))
        conn.commit()
        return f"FAILED  {entry['source_key']}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-process unchanged documents")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))["documents"]
    with connect() as conn:
        init_schema(conn)
        results = [ingest_entry(conn, e, args.force) for e in entries]
    print("\n".join(results))
    return 1 if any(r.startswith("FAILED") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())

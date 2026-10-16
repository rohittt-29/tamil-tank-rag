"""Create embeddings for chunks that do not have one yet.

Usage (from backend/):
    python -m app.embed               # download the model once, then embed new chunks only
    python -m app.embed --force       # re-embed every chunk

Only chunks with no vector, or a vector from a different model, are embedded, so
re-running is cheap. Re-ingesting a document replaces its chunks, which clears
their vectors; run this command again afterwards.
"""

import argparse
import sys
import time

import numpy as np
import psycopg

from .db import connect, init_schema
from .embeddings import ModelMissingError, download_model, get_embedder, model_dir, model_source

BATCH = 32


def to_pgvector(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def embed_missing(conn: psycopg.Connection, embedder, force: bool = False, document_ids: list[int] | None = None) -> int:
    """Embed chunks lacking a vector from this model (all chunks with force). Returns how many were embedded."""
    conditions = [] if force else ["(embedding IS NULL OR embedding_model IS DISTINCT FROM %(model)s)"]
    if document_ids is not None:
        conditions.append("document_id = ANY(%(docs)s)")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT id, text FROM chunks {where} ORDER BY id", {"model": embedder.name, "docs": document_ids}
    ).fetchall()
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        vectors = embedder.embed_passages([r["text"] for r in batch])
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE chunks SET embedding = %s::vector, embedding_model = %s WHERE id = %s",
                [(to_pgvector(v), embedder.name, r["id"]) for r, v in zip(batch, vectors)],
            )
        conn.commit()  # each batch is kept even if a later batch fails
        print(f"  embedded {min(start + BATCH, len(rows))}/{len(rows)}", end="\r", flush=True)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-embed every chunk")
    args = parser.parse_args()

    if model_source() is None:
        print(f"Downloading the embedding model into {model_dir()} (about 490 MB, only once)...")
        try:
            source = download_model()
        except ModelMissingError as exc:
            print(exc)
            return 1
        print(f"  got {source['repo']} at revision {source['revision']}")
    try:
        embedder = get_embedder()
    except ModelMissingError as exc:
        print(exc)
        return 1

    with connect() as conn:
        init_schema(conn)
        start = time.perf_counter()
        n = embed_missing(conn, embedder, args.force)
        total = conn.execute("SELECT count(*) AS n, count(embedding) AS e FROM chunks").fetchone()
    print(f"\nEmbedded {n} chunks in {time.perf_counter() - start:.1f} s. "
          f"Chunks with an embedding: {total['e']} of {total['n']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

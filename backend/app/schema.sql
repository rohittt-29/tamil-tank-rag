-- Schema for the Tamil tank-irrigation knowledge repository.
-- Safe to run many times (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS documents (
    id            SERIAL PRIMARY KEY,
    source_key    TEXT UNIQUE NOT NULL,        -- stable id from data/manifest.json
    title         TEXT NOT NULL,
    authors       TEXT[] NOT NULL DEFAULT '{}',
    year          INT,
    language      TEXT NOT NULL DEFAULT 'en',  -- ISO 639-1: 'en', 'ta'
    source_org    TEXT,                        -- publisher / institution
    source_url    TEXT,                        -- where the original was obtained
    doi           TEXT,
    license       TEXT,                        -- e.g. 'CC BY 4.0'
    file_path     TEXT NOT NULL,               -- path of preserved original, relative to repo root
    sha256        TEXT,                        -- fingerprint of the original file
    page_count    INT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id            SERIAL PRIMARY KEY,
    document_id   INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number   INT NOT NULL,                -- 1-based page in the original PDF
    chunk_index   INT NOT NULL,                -- order within the document
    text          TEXT NOT NULL,
    -- Keyword-search index column, kept in sync by Postgres automatically.
    tsv           TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (document_id, chunk_index)
);

-- Added after milestone 1: 'body' or 'references' (bibliography is excluded from search by default).
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section TEXT NOT NULL DEFAULT 'body';

CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);

-- Milestone 2: semantic search. pgvector stores one 384-number vector per chunk.
-- embedding_model records which model made the vector, so a model change is detected.
-- No vector index: with < 1,000 chunks an exact scan takes milliseconds and gives exact results.
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(384);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT;

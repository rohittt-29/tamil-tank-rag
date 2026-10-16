# Decisions

| # | Date | Decision | Why | Alternatives |
|---|------|----------|-----|--------------|
| 1 | 2026-10-14 | Single Python/FastAPI backend, React+TS frontend | AI, OCR and NLP libraries are Python; one service is simpler | Node API + Python worker (more moving parts, no benefit yet) |
| 2 | 2026-10-14 | PostgreSQL full-text search as keyword baseline | Already need Postgres; built-in ranking and highlighting; no extra infra | Elasticsearch/OpenSearch (extra service), SQLite FTS5 |
| 3 | 2026-10-14 | Chunks never cross a page boundary | Every passage cites exactly one page | Section-aware chunking (revisit for RAG quality) |
| 4 | 2026-10-14 | Manifest file (`data/manifest.json`) is the source of truth for metadata | Reviewable in git, re-ingest is reproducible | Upload form in UI (later, if needed) |
| 5 | 2026-10-14 | Original PDFs kept in `data/raw/`, not committed to git | Keeps repo small; manifest stores URL/DOI + sha256 to re-obtain and verify | Commit PDFs (only if licence allows and size is small) |
| 6 | 2026-10-14 | `pgvector/pgvector:pg16` Docker image for local DB | Ready for semantic search milestone without changing DB | Separate vector DB (not justified) |

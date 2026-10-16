# Architecture (Milestone 1)

```
data/manifest.json + data/raw/*.pdf
        │  python -m app.ingest
        ▼
 extract pages (PyMuPDF) → clean (NFC, de-hyphenate) → chunk per page (180 words, 30 overlap)
        │
        ▼
 PostgreSQL: documents (metadata, licence, sha256, status) ──< chunks (page_number, text, tsv)
        │                                                    GIN index on tsv
        ▼
 FastAPI  GET /api/search  (websearch_to_tsquery + ts_rank_cd + ts_headline)
        │  /api proxied by Vite in dev
        ▼
 React + TS UI: query → passages with highlighted terms, document, page, licence, source link
```

One backend (Python) does both document processing and the API: the AI/NLP libraries we need
later (embeddings, OCR, Tamil NLP) live in Python, so a separate Node service would add nothing.

Planned additions, in order: pgvector embeddings column on `chunks` → semantic and hybrid search →
evaluation harness → cited RAG answers → Tamil/cross-language retrieval → OCR → entity extraction.

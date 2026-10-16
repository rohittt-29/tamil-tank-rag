# Architecture (Milestone 2)

```
data/manifest.json + data/raw/*.pdf
        │  python -m app.ingest
        ▼
 extract pages (PyMuPDF) → clean (NFC, de-hyphenate) → chunk per page (180 words, 30 overlap)
        │
        ▼
 PostgreSQL: documents (metadata, licence, sha256, status) ──< chunks (page_number, text, tsv, embedding)
        │                                                    GIN index on tsv; embedding = vector(384), pgvector
        │  python -m app.embed  (multilingual-e5-small via ONNX Runtime, only chunks without a vector)
        ▼
 FastAPI  GET /api/search?mode=
            keyword  : websearch_to_tsquery + ts_rank_cd
            semantic : embed "query: <q>" → ORDER BY embedding <=> query_vector (cosine)
            hybrid   : Reciprocal Rank Fusion of keyword-any top 50 + semantic top 50
          then drop adjacent overlapping chunks; ts_headline snippet; document + page on every hit
        │  /api proxied by Vite in dev
        ▼
 React + TS UI: query → passages with highlighted terms, document, page, licence, source link
```

One backend (Python) does both document processing and the API: the AI/NLP libraries we need
later (embeddings, OCR, Tamil NLP) live in Python, so a separate Node service would add nothing.

Evaluation: `python -m app.evaluate --method all` runs every method on `eval/queries.json` and checks they
used the same questions (sha256 of the file).

Planned additions, in order: spelling normalisation → cited RAG answers → Tamil/cross-language retrieval →
OCR → entity extraction / knowledge graph → deployment.

# Project State

_Last updated: 2026-10-15_

## Current phase
Milestone 1: end-to-end keyword search over real documents with source references.

## Done
- Postgres schema: `documents` (metadata, licence, sha256, status, error) and `chunks` (page-level text + full-text index).
- Ingestion CLI (`python -m app.ingest`): PDF text extraction (PyMuPDF), cleaning, page-bounded chunking,
  idempotent re-runs (skips unchanged files by sha256), failures recorded on the document row.
- Search API (FastAPI): Postgres full-text search, ranked passages with highlighted snippets and page numbers.
- React + TypeScript UI: search box, results with title/authors/year/page/licence/source link, collection list.
- Tests: 11 passing (as of 2026-10-15) (5 unit tests for cleaning/chunking, 2 end-to-end ingest→search tests using a synthetic fixture PDF).

## Verified on real data (2026-10-14)
First real source ingested: Mailam tank cascade paper (23 pages → 110 chunks, ~1.3 s). Example queries:
| Query | Passages | Top hit |
|---|---|---|
| tank cascade | 42 | p.1 (abstract) |
| desilting | 4 | p.18 ("Traditionally, they desilt tanks adopting Kudimaramathu…") |
| kudimaramathu | 2 | p.18 (body) and p.23 (reference list) |
| eri | 1 | p.2 ("…locally known as Eri or Kanmai (tanks)…") |
| neerkatti | 0 | term not in this document |
| water storage structure | 8 | weak matches: keyword search matches words, not meaning |

Screenshot: `docs/milestone1-search.png`.

## Fixed on 2026-10-15
- Repeated page headers/footers are stripped before chunking (lines repeating at the top/bottom of ≥50% of pages).
- Text after a "References" heading is stored with `section = 'references'` and excluded from search by default
  (`include_references=true` to include it). Mailam paper: 93 body + 14 reference chunks.
- Adjacent overlapping chunks no longer show up as duplicate results.
  "desilting": 4 results → 2 (removed one duplicate and one bibliography entry).
- Existing databases must be rebuilt once: `python -m app.ingest --force`.

## Collection (2026-10-15)
4 documents, 198 pages, 670 chunks (ingest of all four: ~2 s). See DATA_SOURCES.md.

## Observation worth an experiment (not yet a result)
Transliterated Tamil terms are spelled differently across sources. The DHAN report writes "Kudimaramath" 12 times and
"Kudimaramathu" once; a query for "kudimaramathu" finds only the one exact spelling there. Candidate experiment:
retrieval before vs after transliteration normalisation (research question for EXPERIMENTS.md).

## Evaluation (2026-10-15)
Draft 28-query test set and evaluation script (`python -m app.evaluate`). First keyword baselines recorded in
EXPERIMENTS.md (judgments still need Kalpesh's review). Added `match=any` search mode; UI still uses `all`.

## Still open
- Concept queries ("water storage structure") rank poorly — expected for keyword search; motivates semantic search.

## Next task
1. Push the code to GitHub (https://github.com/rohittt-29/tamil-tank-rag). Keep collecting sources (target 10+).
2. Kalpesh reviews the draft query set (`eval/queries.json`); baseline is in `docs/EXPERIMENTS.md`.
3. Milestone 2: embeddings + pgvector semantic search, compared to keyword search on that query set.

## Known limitations
- No OCR: scanned PDFs fail with "no extractable text".
- Full-text config is `english`; Tamil text is indexed but not stemmed/normalised properly yet.
- Chunking is by word windows (180 words, 30 overlap), not by section/sentence.

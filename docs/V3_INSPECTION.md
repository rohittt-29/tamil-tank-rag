# V3 Phase 1: inspection findings and proposed changes

_Inspected 2026-10-18 (before any change). Every number below was measured on the current code
and data (git commit 069be5f, 4 documents, 677 chunks), not copied from earlier reports._

## 1. What already exists

| Area | What the code does today | Where |
|---|---|---|
| Query cleaning | Only `q.strip()`, plus a 422 error for an empty query. No Unicode normalisation, no whitespace collapse, no spelling variants. | `backend/app/main.py` `search()` |
| Casing and punctuation (keyword) | PostgreSQL does this already: `websearch_to_tsquery('english', …)` lowercases, drops punctuation and stems ("desilting" → "desilt"). | `main.py` `QUERY_CTE` |
| Casing (semantic) | The query goes to the model as typed, with a `query: ` prefix. | `embeddings.py` |
| Document cleaning | Unicode NFC, soft-hyphen and control-character removal, hyphen re-joining, whitespace collapse. | `textproc.py` `clean_text` |
| Header/footer removal | Removes a line that appears in the top/bottom 5 lines of at least 50% of pages. Digits are ignored when comparing lines. | `textproc.py` `strip_repeated_edges` |
| Bibliography | Text after a "References" heading is tagged `references` and left out of search by default. | `textproc.py` `chunk_document` |
| Duplicate results | Two **neighbouring** chunks of the same document are never both shown. | `main.py` `drop_overlapping_neighbours` |
| Evaluation | 28 questions, page-level labels, P@5 / Recall@10 / MRR, sha256 of `eval/queries.json` saved with every result. | `evaluate.py`, `eval/queries.json` |

## 2. Problems found, with evidence

### A. Spelling variants really do cause misses (verified in the PDFs)

Counted in the body text of all 677 chunks:

| Group | Spellings found | Same meaning? (checked in context) |
|---|---|---|
| Kudimaramath | Kudimaramath (13, DHAN), Kudimaramathu (2, DHAN p91 + Mailam p18), Kudimaramatu (1, Mailam p2), Kudimaramat (1, DHAN) | Yes. Mailam p2: "‘Kudimaramatu’, a traditional practice of users’ voluntary contribution of labour for maintenance…" |
| Ayacutdar (tank-command farmer) | ayacutdars (10), ayacutdhars (22), ayacutdaras (2) | Yes. DHAN p32 uses "ayacutdhars" and "ayacutdaras" in the same discussion of fishing rights. |
| Tamil Nadu | "Tamil Nadu" (158), "Tamilnadu" (33, DHAN + Suresh) | Yes, same state. |

Effect today: query Q01 "kudimaramath" finds only the "Kudimaramath" pages. It misses M2, M18 and D91, which are
labelled relevant and use the other spellings. Keyword Recall@10 for Q01 is 0.57 (4 of 7 pages).
In the database, the exact term matches 8 body chunks, and all four spellings together match 11.

**Not merged on purpose:**
- eri / kanmai / kanmoi / kulam / oorani: these are different water bodies or regional names. For example, an oorani is a drinking-water pond.
- Neerkatti / Neerpaichi / Kombukatty: these are role names from different places, and the sources don't say the duties are identical.

Merging any of these could change meaning, so they are left to semantic search.

### B. A footer survived cleaning on 65 DHAN pages

The DHAN report has the footer "DHAN Foundation, Madurai" on 139 of its 143 pages, written in two forms:
- **with a full stop:** 74 pages;
- **without one:** 65 pages.

Each form alone is just below or just above the 50% rule. So the version with the full stop is removed, but the version without it is not.

The result:
- 65 chunks still contain the footer text;
- 8 chunks (pages 109–113 and 126–128, pages that are only figures) contain nothing but "DHAN Foundation, Madurai". They are also the only 8 exact-duplicate chunks in the database.

### C. The evaluation counts the same page twice in P@5

Search can return two non-neighbouring chunks from the same page. The labels are per page, so the same relevant page is counted twice in P@5.

| Run 2 (V2) method | Questions with a repeated page in the top 5 | P@5 as reported | P@5 if each page counts once |
|---|---|---|---|
| keyword-all | 5 | 0.193 | 0.179 |
| keyword-any | 2 | 0.250 | 0.250 |
| semantic | 5 | 0.371 | 0.357 |
| hybrid | 4 | 0.400 | 0.379 |

Recall@10 is not affected. MRR changes only for hybrid (0.714 → 0.716, because a repeated page before the first relevant hit no longer pushes it down). So the V2 P@5 numbers are slightly too high. The ranking order of the methods does not change.

_Update 2026-10-18: Stage 1 is implemented; results in EXPERIMENTS.md (Run 2 re-scored, Run 3a)._

### D. Possible label gaps (for you to review, not for me to change)

- Q17 "fishing rights in village tanks" fails for every method. DHAN p32 discusses fish tax and fishing rights of ayacutdhars, but p32 is not in Q17's labels. Please check whether p32 should be added.
- Q14 "Water Users Association effectiveness" also fails for every method. Its labelled pages are worth a second look.

## 3. Proposed changes (small, no schema change, no change to embeddings or retrieval architecture)

| # | File | Change | Why |
|---|---|---|---|
| 1 | `backend/app/normalize.py` (new) | `normalize_query()`: Unicode NFC, remove control characters, curly quotes to straight quotes (so "exact phrase" search still works), collapse spaces. Returns the original text too. Also holds the explicit list of verified variant groups from 2A, each with its evidence page. | One place for all rules, easy to unit-test |
| 2 | `backend/app/main.py` | Use the normalised text for all modes. In keyword search (and in the keyword half of hybrid), add the variants with PostgreSQL `ts_rewrite`. Example: `kudimaramath & tank` becomes `(kudimaramath \| kudimaramathu \| kudimaramatu \| kudimaramat) & tank`, so the rest of the query is untouched. Response gains `normalized_query` and `variants_used`; `query` stays exactly as typed. | Fixes 2A for keyword and hybrid. Semantic gets the same cleaned text but no variant rewriting. |
| 3 | `backend/app/textproc.py` | Compare header/footer lines ignoring case and trailing punctuation, so "Madurai" and "Madurai." count as one line. | Fixes 2B and removes the 8 junk chunks |
| 4 | `backend/app/evaluate.py` | Count each page once (its first rank) when scoring. Re-score the saved V2 runs with the same rule so V2 and V3 are compared fairly. | Fixes 2C |
| 5 | `backend/tests/test_normalize.py` (new), `test_textproc.py`, `test_semantic.py` | Tests for whitespace, NFC Tamil text, curly quotes, empty or only-punctuation queries, each variant group, "no variant for unrelated words", the footer case, and the page de-duplication in scoring. | Requirement |
| 6 | `frontend/src/types.ts`, `App.tsx` | Show a small line: "Also searched: kudimaramathu, kudimaramatu, kudimaramat". | So users can see what normalisation did |
| 7 | `docs/` | EXPERIMENTS (Run 3), DECISIONS, PROJECT_STATE | Record commands, results and limits |

**Not changed:** the database schema, the embedding model and its dimensions, chunk size, `eval/queries.json`, and existing data.

## 4. How V2 vs V3 will be measured

Same `eval/queries.json` (sha256 48210f6b83cc…), same 28 questions and labels. I'll measure each change separately, so we know what caused what:

1. **V2 baseline:** the saved Run 2 results, re-scored with the page-once rule.
2. **V3a:** query normalisation and variants only. No re-ingest needed. I can measure the keyword modes in the cloud; semantic and hybrid need your laptop, where the model is.
3. **V3b:** V3a plus the footer fix. This needs `python -m app.ingest --force` and `python -m app.embed` on your laptop. `--force` re-creates every chunk, so `app.embed` re-creates all 677 vectors (a few minutes on CPU). Nothing else is deleted.

If a number gets worse, I'll report it and look for the cause. I won't claim an improvement the numbers don't show.

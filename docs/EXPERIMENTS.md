# Experiments

## Evaluation set (`eval/queries.json`)
- 28 queries written from the 4 ingested documents: 11 **term** queries (short, use the source's own words)
  and 17 **paraphrase** queries (natural questions that often use different words from the source).
- Relevance is judged at **page level**: a result is relevant if its (document, page) is listed for the query.
  Page level is used because chunk boundaries change whenever chunking changes; pages do not.
- **Status: DRAFT.** Judgments were written by Claude after reading the pages on 2026-10-15. Kalpesh must review
  them (add missing pages, remove weak ones) before any number below is reported as a result.
- Limitation: no Tamil-language documents or queries yet, so multilingual retrieval cannot be evaluated.

## Metrics (all computed per query, then averaged)
- **Precision@5 (P@5)**: of the top 5 results, what fraction is relevant? "How much junk does the user see?"
  Example: 2 relevant out of 5 → 0.4.
- **Recall@10 (R@10)**: of all relevant pages, what fraction appears in the top 10? "How much did we miss?"
  Example: 3 relevant pages exist, 1 found → 0.33.
- **MRR (Mean Reciprocal Rank)**: 1 / rank of the first relevant result (1st → 1.0, 2nd → 0.5, 5th → 0.2,
  none in top 10 → 0). "How quickly does the user find something useful?"
- **Latency**: wall-clock time of the search function per query (median reported). Measured in the dev
  container (Postgres 16, 670 chunks); not comparable across machines.

Run: `cd backend && python -m app.evaluate --method keyword-all --save` (results go to `eval/results/`).

## Run 1 — keyword baselines (2026-10-15, DRAFT judgments, 4 documents / 670 chunks)

| Method | Queries | P@5 | Recall@10 | MRR | Queries with no relevant hit in top 10 |
|---|---|---|---|---|---|
| keyword-all (every word must match; current UI) | all 28 | 0.193 | 0.251 | 0.445 | 13 |
| | term 11 | 0.364 | 0.484 | 0.632 | 2 |
| | paraphrase 17 | 0.082 | 0.100 | 0.324 | 11 |
| keyword-any (any word may match) | all 28 | 0.250 | 0.474 | 0.537 | 3 |
| | term 11 | 0.273 | 0.439 | 0.627 | 2 |
| | paraphrase 17 | 0.235 | 0.496 | 0.479 | 1 |

Median latency: keyword-all 14.9 ms, keyword-any 109.6 ms.

Observations (from the per-query output in `eval/results/`):
- keyword-all fails on natural questions because every word (e.g. "responsible", "opening") must appear in one chunk;
  11 of 17 paraphrase queries find nothing relevant.
- keyword-any fixes most of that, but precision stays low: common words ("tank", "water") match almost every chunk.
- Both fail on Q14 ("Water Users Association effectiveness") and Q17 ("fishing rights in village tanks"), where the
  sources use other wording.
- Spelling variants hurt recall: Q01 "kudimaramath" misses pages spelled "Kudimaramatu"/"Kudimaramathu".

Next run: semantic (embedding) search and hybrid search on the same, reviewed query set.

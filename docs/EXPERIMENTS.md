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
  container (Postgres 16, 677 chunks); not comparable across machines.

Run: `cd backend && python -m app.evaluate --method keyword-all --save` (results go to `eval/results/`).

## Run 1 — keyword baselines (2026-10-15, DRAFT judgments, 4 documents / 677 chunks)

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


## Run 2 — keyword vs semantic vs hybrid (2026-10-17, DRAFT judgments, 4 documents / 677 chunks)

Measured on Kalpesh's laptop (Windows, CPU only) with `python -m app.evaluate --method all --save`.
All four result files carry the same `queries_sha256` (48210f6b83cc…) and the same 28 query ids, so
every method was scored on identical questions and relevance labels. The two keyword rows reproduce
Run 1 exactly, which is a check that nothing in the keyword path changed.

- **semantic**: multilingual-e5-small (intfloat/multilingual-e5-small, revision 614241f6), ONNX Runtime,
  "query: "/"passage: " prefixes, mean pooling, cosine similarity in pgvector (exact scan, no index).
- **hybrid**: Reciprocal Rank Fusion (k = 60) of the top 50 keyword-any and top 50 semantic chunks,
  then the same adjacent-chunk de-duplication as every other method.

| Method | Queries | P@5 | Recall@10 | MRR | No relevant hit in top 10 |
|---|---|---|---|---|---|
| keyword-all | all 28 | 0.193 | 0.251 | 0.445 | 13 |
| keyword-any | all 28 | 0.250 | 0.474 | 0.537 | 3 |
| semantic | all 28 | 0.371 | 0.553 | **0.720** | 3 |
| hybrid | all 28 | **0.400** | **0.564** | 0.714 | **1** |
| keyword-all | term 11 | **0.364** | 0.484 | 0.632 | 2 |
| keyword-any | term 11 | 0.273 | 0.439 | 0.627 | 2 |
| semantic | term 11 | **0.364** | **0.554** | 0.614 | 2 |
| hybrid | term 11 | 0.345 | 0.540 | **0.683** | **1** |
| keyword-all | paraphrase 17 | 0.082 | 0.100 | 0.324 | 11 |
| keyword-any | paraphrase 17 | 0.235 | 0.496 | 0.479 | 1 |
| semantic | paraphrase 17 | 0.376 | 0.552 | **0.789** | 1 |
| hybrid | paraphrase 17 | **0.435** | **0.580** | 0.734 | **0** |

Median latency on the laptop: keyword-all 40.0 ms, keyword-any 187.1 ms, semantic 229.0 ms, hybrid 109.1 ms
(semantic includes embedding the question on the CPU). Different machine from Run 1, so not comparable to
Run 1's latencies.

What the numbers say:
- On natural questions (paraphrase) both new methods are far ahead of strict keyword search: P@5 0.082 → 0.376
  (semantic) and 0.435 (hybrid). This was the gap Milestone 2 was meant to close.
- On short term queries, semantic search is **not** better at ranking: MRR 0.614 vs 0.632 for keyword-all.
  Q01 "kudimaramath" (RR 1.00 → 0.50) and Q03 "neerkatti" (Recall@10 1.00 → 0.50) are the clearest cases:
  a rare transliterated Tamil word is split into sub-word pieces by the model's tokenizer, so passages
  about tank maintenance in general look as similar as passages that contain the exact term. Keyword search
  matches the exact word.
- Hybrid recovers most of that (Q01 RR back to 1.00, Recall@10 0.57 → 0.71) and has the fewest queries
  with nothing relevant in the top 10 (1 of 28).
- Hybrid is worse than semantic on some queries. Q12 "Prosopis juliflora in tanks": semantic P@5 0.6 / RR 1.00,
  hybrid P@5 0.2 / RR 0.20. Keyword-any matches "tank" in almost every chunk, and RRF rewards chunks that appear
  in both lists, so moderately ranked "tank" chunks can push down semantic's correct hits. Candidate follow-ups:
  weight the two lists, or fuse keyword-all instead of keyword-any when it returns results.
- Q14 "Water Users Association effectiveness" and Q17 "fishing rights in village tanks" still fail for every
  method (hybrid Q14 Recall@10 0.25 is the only hit). Worth checking whether the judged pages really answer them.

Caveats: 28 queries is small, the judgments are still a draft by Claude, and no significance test was run,
so differences of a few hundredths (e.g. semantic 0.720 vs hybrid 0.714 MRR) should not be read as real.

Run 2 result files: `eval/results/{keyword-all,keyword-any,semantic,hybrid}-2026-10-17.json`.

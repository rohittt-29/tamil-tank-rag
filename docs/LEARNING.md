# Learning Notes

## Milestone 1 — how keyword search works here

**1. Why chunks?** Ek PDF 15–20 pages ka hota hai. Agar poora document ek result ho, user ko pata nahi chalega
answer kahan hai. So we cut each page into ~180-word pieces ("chunks"). Each chunk remembers its
`page_number`, so every result can say "page 7". Later, RAG will send these same chunks to the LLM as
evidence, so the chunk = our unit of citation.

**2. Why overlap?** If a sentence sits on the border of two chunks, it gets cut in half. Repeating the
last 30 words at the start of the next chunk means the sentence fully appears in at least one chunk.

**3. Cleaning.** PDFs break words across lines (`irriga-` / `tion`). We re-join them and collapse spaces.
We use Unicode **NFC** normalisation, not NFKC, because NFKC can change some characters — risky for Tamil.

**4. Full-text search in Postgres.**
- `to_tsvector('english', text)` turns text into normalised word stems:
  "tanks were desilted" → `'desilt' 'tank'` ("were" is a stop-word, dropped).
- That is stored in the `tsv` column and indexed with a **GIN index** (an inverted index: word → list of rows),
  so search does not scan every row.
- `websearch_to_tsquery` turns user input like `"tank cascade" -groundwater` into a query.
- `ts_rank_cd` scores by how many query words appear and how close together they are.
- `ts_headline` builds the snippet and marks matched words.
Limitation: it matches **words**, not **meaning**. "water storage structure" will not find "eri".
That gap is exactly what semantic (embedding) search fixes in Milestone 2 — and we will measure it.

**5. Idempotent ingestion.** Running `python -m app.ingest` twice must not create duplicates. We store
the file's **sha256** hash; if it is unchanged, skip. If changed, delete old chunks and insert new ones
inside one **transaction** (all or nothing). Errors go into `documents.error` instead of crashing.

**6. Frontend → backend.** React calls `/api/search`; Vite's dev proxy forwards it to FastAPI on port 8000.
FastAPI validates `q` and `limit` with type hints and returns JSON shaped by Pydantic models
(see `/docs` for the auto-generated API page).

**Viva questions to practise:** Why page-bounded chunks? What does a GIN index store? Why is keyword
search a *baseline*? How do you guarantee re-running ingestion is safe?

## Cleaning lessons from the first real PDF (2026-10-15)

**Headers/footers.** Every page of a journal PDF repeats lines like "Frontiers in Water", "frontiersin.org" and a
page number. They add noise words to every chunk. Rule we use: a line that appears in the top or bottom 5 lines of
at least half the pages is boilerplate (digits are ignored when comparing, so "01" and "02" count as the same).

**Reference lists.** A bibliography contains topic words ("Desilting of minor irrigation tanks…") but is not
evidence; later, an LLM citing it would be citing a *title*, not a finding. So chunks after the "References"
heading get `section = 'references'` and search skips them by default.

**Duplicate hits.** Overlap (Milestone 1, point 2) means one sentence can sit in two neighbouring chunks, so both
match. After ranking, we keep only the better one of any two adjacent chunks. This is a *display* fix; for
evaluation we must decide whether a "relevant passage" means a chunk or a text span. (Viva question!)

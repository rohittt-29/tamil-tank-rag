# Tamil Tank Irrigation Knowledge Search

Final-year Computer Engineering project:
**AI-Enabled Digital Documentation, Preservation and Intelligent Retrieval Framework for Tamil Traditional Agricultural and Water-Management Systems.**
Initial focus: traditional Tamil tank (eri) irrigation.

Current stage: **Milestone 2** — keyword, semantic (embeddings + pgvector) and hybrid search over real PDFs with provenance; every passage shows its document and page.
See `docs/PROJECT_STATE.md` for what works and what is next.

## Layout

```
backend/    Python + FastAPI: ingestion pipeline and search API
frontend/   React + TypeScript (Vite): search UI
data/       manifest.json (source metadata) and raw/ (original PDFs, not in git)
docs/       project state, architecture, decisions, data sources, handoff
```

## Setup

Beginner, step by step on Windows: see `docs/WINDOWS_SETUP.md`. Short version (PowerShell):

Prerequisites: Python 3.11+, Node 22.12+ (or 20.19+), and either Docker Desktop or a local PostgreSQL 16.

```powershell
# 1. Database
docker compose up -d                       # starts Postgres on localhost:5432 (user/pass/db: tank/tank/tankdb)

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                     # edit DATABASE_URL if your DB differs
python -m pytest -q                        # unit + end-to-end tests
python -m app.ingest                       # ingest everything in data/manifest.json
python -m app.embed                        # first run downloads the embedding model (~490 MB), then embeds new chunks
python -m app.evaluate --method all        # compare keyword / semantic / hybrid on eval/queries.json
uvicorn app.main:app --reload --port 8000  # API at http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                                # UI at http://localhost:5173
```

## Adding a document

1. Check the licence allows storing and processing it, then save the PDF in `data/raw/`.
2. Add an entry to `data/manifest.json` (title, authors, year, language, source, URL/DOI, licence).
3. Record it in `docs/DATA_SOURCES.md`.
4. Run `python -m app.ingest`, then `python -m app.embed`. Unchanged files are skipped; use `--force` to re-process.

## API

- `GET /api/search?q=...&limit=10&mode=keyword|semantic|hybrid` — keyword (default) supports `"exact phrase"`, `OR`, `-exclude` and `match=all|any`; semantic and hybrid need `python -m app.embed` first.
- `GET /api/documents` — collection with processing status and errors.
- `GET /api/health`

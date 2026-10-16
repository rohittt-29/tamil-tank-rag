# Run the project on Windows (step by step)

You need 3 things installed once. Check in PowerShell; if a command says "not recognized", install it.

| Check | Install from |
|---|---|
| `python --version` (3.11 or newer) | https://www.python.org/downloads/ (tick **"Add python.exe to PATH"**) |
| `node --version` (22.12 or newer; 20.19+ also works) | https://nodejs.org/ (LTS) |
| `docker --version` | https://www.docker.com/products/docker-desktop/ (then open Docker Desktop once) |

No Docker? Install PostgreSQL 16 from https://www.postgresql.org/download/windows/ instead, then in
"SQL Shell (psql)" run:
`CREATE USER tank WITH PASSWORD 'tank'; CREATE DATABASE tankdb OWNER tank;` and skip step 2.

## 1. Unzip
Right-click `Downloads\tamil-tank-rag.zip` → **Extract All** → choose `C:\Users\<you>\` (or any folder).
Open the extracted `tamil-tank-rag` folder in VS Code (File → Open Folder).

## 2. Start the database (terminal 1, in the project folder)
```powershell
docker compose up -d
```
Wait ~10 seconds the first time. `docker ps` should show a container running on port 5432.

## 3. Backend (same terminal)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```
If PowerShell says "running scripts is disabled", run this once, then activate again:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
```powershell
pip install -r requirements.txt
copy .env.example .env
python -m pytest -q              # expect: 7 passed
python -m app.ingest             # expect: ok  frontiers-2025-mailam-tank-cascade: 110 chunks
uvicorn app.main:app --reload --port 8000
```
Leave it running. Open http://localhost:8000/docs to try the API directly.

## 4. Frontend (terminal 2: VS Code → Terminal → New Terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 and search `desilting`.

## Next time
Terminal 1: `docker compose up -d`, `cd backend`, `.venv\Scripts\Activate.ps1`, `uvicorn app.main:app --reload --port 8000`.
Terminal 2: `cd frontend`, `npm run dev`.

## Common errors
- `connection refused ... 5432`: the database is not running → open Docker Desktop, run `docker compose up -d`.
- `port 5432 already in use`: another PostgreSQL is installed → stop it, or use it with the "No Docker" steps above.
- Search page shows "Could not load documents": the backend (terminal 1) is not running.
- `Cannot find native binding ... @rolldown/binding-win32-x64-msvc` on `npm run dev`: Node is too old
  (Vite 8 needs 22.12+). Install the current LTS Node, then in `frontend`:
  `Remove-Item -Recurse -Force node_modules` and `npm install` again.

# Master Data Profiler — FastAPI + React (MUI) Edition

Modern rewrite of the Streamlit-based Data Profiler. The Python core (profiling
engine, fuzzy matching, audit log, DB connectors) is **unchanged** — it's now
exposed as a REST API and consumed by a React + MUI single-page app.

```
┌────────────────────────────┐        ┌──────────────────────────┐
│   React + MUI (Vite)       │  REST  │   FastAPI                │
│   frontend/  port 5173     │ ─────▶ │   backend/  port 8765    │
└────────────────────────────┘        │   imports core/, models/ │
                                      │   from existing project  │
                                      └──────────────────────────┘
```

## Project layout

```
DataProfilingToolv7_old/
├── backend/                  # NEW — FastAPI service
│   ├── app/
│   │   ├── main.py           # entry: uvicorn backend.app.main:app
│   │   ├── deps.py           # session/dataframe dependencies
│   │   ├── schemas.py        # Pydantic request/response models
│   │   ├── session_store.py  # in-memory session registry
│   │   ├── routers/          # one router per feature area
│   │   └── services/         # loader + serializer helpers
│   └── requirements.txt
├── frontend/                 # NEW — React + MUI + Vite
│   ├── src/
│   │   ├── App.jsx           # tab shell
│   │   ├── theme.js          # MUI theme matching old palette
│   │   ├── api.js            # axios client + session header
│   │   ├── context/          # Auth + Dataset contexts
│   │   ├── components/       # Sidebar, TopTabs, StatCard, …
│   │   └── pages/            # Dashboard, LoadData, Profiling, …
│   ├── vite.config.js
│   └── package.json
├── core/        # UNCHANGED — DataProfilerEngine, db_connector, etc.
├── models/      # UNCHANGED — ColumnProfile, DataQualityReport
├── auth/        # UNCHANGED — login + users.json
├── utils/       # UNCHANGED — fuzzy matching, dtype mapper
├── app.py       # UNCHANGED — original Streamlit app still runnable
└── requirements.txt   # original Streamlit deps
```

## Quick start (development)

### 1. Backend (FastAPI)

From the project root:

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8765 --reload
```

Swagger UI: <http://localhost:8765/docs>

### 2. Frontend (React + MUI)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api/*` to the backend on
`:8765`, so no CORS configuration is needed locally.

### Demo credentials
`demo` / `admin@123` (stored hashed in `auth/users.json`).

Existing accounts (`admin`, `krishna`, `Manoj`, `vineeth`) keep their original
passwords from the Streamlit deployment.

## Feature parity with the Streamlit app

| Streamlit tab     | FastAPI endpoint(s)                              | React page             |
|-------------------|--------------------------------------------------|------------------------|
| Dashboard         | `GET /profile/dashboard`                          | `Dashboard.jsx`        |
| Load Data         | `POST /data/upload`, `GET /data/state`            | `LoadData.jsx`         |
| Rule Generator    | `POST /quality/generate-rules`                    | `RuleGenerator.jsx`    |
| Data Profiling    | `POST /profile/run`                               | `DataProfiling.jsx`    |
| Find Duplicates   | `POST /duplicates/{exact,fuzzy,remove-exact}`     | `FindDuplicates.jsx`   |
| Data Quality      | `POST /quality/{generate-rules,apply}`            | `DataQuality.jsx`      |
| Compare           | `GET /data/compare`, `POST /data/reset`           | `Compare.jsx`          |
| Multi-File        | `POST /multi-file/compare`                        | `MultiFile.jsx`        |
| Preview           | `GET /data/preview`                               | `Preview.jsx`          |
| Export            | `POST /data/export?format=csv\|xlsx\|parquet\|…` | `Export.jsx`           |
| Audit log         | `GET /audit/`                                     | (extension point)      |

## Why this is more scalable than the Streamlit version

* **Stateless HTTP**: every API request is independent — back the session store
  with Redis to scale horizontally.
* **Browser-rendered UI**: pages load instantly; no full-page reruns when you
  click a button.
* **Component reuse**: MUI primitives, MUI X DataGrid, Recharts.
* **API-first**: any client (Postman, curl, another React app, mobile) can
  consume the same endpoints.
* **CI-friendly**: backend and frontend can be tested, built, and deployed
  independently.

## Production build

```powershell
# Frontend
cd frontend
npm run build              # outputs to frontend/dist
# Serve dist/ behind nginx, or via FastAPI's StaticFiles.

# Backend
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8765 --workers 4
```

For multi-worker deployments, replace the in-memory `SessionStore` in
`backend/app/session_store.py` with a Redis-backed store. The existing API
surface stays the same.

## Configuration

* `auth/users.json` — credentials (auto-created with `admin` on first run).
* `data/audit_log.db` — SQLite audit log (created automatically).
* The original Streamlit app and the new FastAPI app coexist; they share the
  same `core/`, `auth/`, `utils/` packages.

## Roadmap

The current rewrite focuses on the most-used flows. Future passes:

* WebSocket progress events for long-running profiling/upload tasks.
* JWT-based auth instead of session-id headers.
* Drift detection UI (the `core/drift_detector.py` engine is already there).
* Database-source ingestion UI (the `core/db_connector.py` is wired up; only
  the React form needs to be added).
* Rule library persistence using `core/rule_library.py`.

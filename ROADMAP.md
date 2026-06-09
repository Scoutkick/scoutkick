# ScoutKick Improvement Roadmap

Based on statbotics patterns — 7 items ordered by impact vs effort.

---

## Status Legend

| Icon | Meaning |
|------|---------|
| ✅ | Implemented |
| ⏳ | In Progress |
| ️ | Planned |

---

## Phase 1 ✅ — Quick Wins (Done)

### 1️⃣ ✅ Remove auto-pipeline from startup + add `/v1/data/run` endpoint

**Problem**: Pipeline runs on every boot in `lifespan`. Render health checks kill the app before 7 seasons finish. API returns 404/empty until pipeline completes.

**Solution** (statbotics pattern: no startup pipeline, manual HTTP triggers):

- Remove pipeline logic from `backend/main.py` `lifespan`
- Make `lifespan` a no-op that checks if DB has data and logs a warning if empty
- Create `backend/src/api/data.py` with:
  - `POST /v1/data/run` → runs all seasons (2019→2025) via `BackgroundTasks`
  - `POST /v1/data/run/{season}` → runs a single season
  - `GET /v1/data/status` → alias for `/v1/pipeline`
- Move `pipeline_status` dict from `main.py` into `data.py`

**Files**: `backend/main.py`, `backend/src/api/data.py` (new), `backend/src/api/router.py`

**Deploy flow after change**:
```
1. App boots instantly → health check passes
2. API serves existing data from persistent disk (if any)
3. If empty DB: POST /v1/data/run → pipeline in background
4. Poll /v1/pipeline → "done" → data ready
```

---

### 2️⃣ ✅ Add `/v1/health` endpoint

**Problem**: No way to verify app+DB are healthy. Render health checks only check that the port is up, not that data is available.

**Solution** (statbotics pattern: multiple App Engine services, each independently health-checkable):

```python
@router.get("/v1/health")
def health():
    db_ok = _check_db_has_data()
    pipe = pipeline_status
    seasons_in_db = _get_seasons_in_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "db_has_data": db_ok,
        "seasons": seasons_in_db,
        "pipeline": pipe["state"],
        "pipeline_running": pipe["state"] == "running",
    }
```

Helper `_check_db_has_data()` queries `SELECT COUNT(*) FROM seasons` — returns True if any row exists.

**File**: `backend/main.py` (add route + helper)

---

### 3️⃣ ✅ Consistent response format

**Problem**: Scoutkick has 3 different response shapes:

| Endpoint | Format |
|----------|--------|
| `/v1/seasons` | **Bare array** `[{...}]` |
| `/v1/teams`, `/v1/events`, `/v1/matches`, etc. | `{"value":[], "count":N}` |
| `/v1/team/{id}`, `/v1/event/{ec}`, `/v1/match/{ec}/{mid}`, `/v1/predict` | Flat dict |

**Solution** (statbotics pattern: uniform response envelope):

- **Collection endpoints** → `{"value":[], "count":N}` (already correct for most)
- **Detail endpoints** → flat dict (already correct for most)
- **Fix exception**: `/v1/seasons` should wrap in `{"value":[], "count":N}`

**File**: `backend/src/api/season.py` (wrap return value)

---

## Phase 2 — Architecture (Effort: days)

### 4️⃣ Planned — Separate data service on Render

**Problem**: Pipeline runs in the same process as the API. Heavy computation (7 seasons, ~10 min) competes with request handling.

**Solution** (statbotics pattern: 3 services — `default`, `data`, `site`):

Add a second web service in `render.yaml`:

```yaml
services:
  - type: web
    name: scoutkick-api
    startCommand: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
    # ...existing config...
    disk:
      mountPath: /opt/render/project/cache
      sizeGB: 1

  - type: web
    name: scoutkick-data
    startCommand: uvicorn backend.data_main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHONPATH
        value: .
      - key: EPA_DB_PATH
        value: /opt/render/project/cache/epa_data.db
    disk:
      mountPath: /opt/render/project/cache
      sizeGB: 1
```

Both services share the same persistent disk → same SQLite database.

Create `backend/data_main.py` — a minimal FastAPI app with only the data router:

```python
# backend/data_main.py
from fastapi import FastAPI
from backend.src.api.data import router as data_router

app = FastAPI(title="scoutkick data service")
app.include_router(data_router)
```

**What this solves**: The API service boots instantly regardless of pipeline state. The data service handles the heavy computation. Both share the same DB on the persistent disk.

---

### 5️⃣ ✅ PostgreSQL external database (code ready, needs Render Postgres setup)

**Problem**: SQLite is tied to the instance filesystem. Even with a persistent disk, it's single-writer, fragile on deploy, and lost if the disk unmounts.

**Solution** (statbotics pattern: external CockroachDB Cloud → managed PostgreSQL):

Replace `SQLiteStorage` with a `PostgresStorage` that talks to Render Managed Postgres.

**Database URL** via `DATABASE_URL` env var (Render auto-injects this for managed Postgres).

**Schema** — same 4 tables (team_seasons, team_events, team_matches, seasons), translated to PostgreSQL:

```python
# backend/src/storage/postgres_storage.py
import psycopg2
import psycopg2.extras

class PostgresStorage:
    def __init__(self, db_url: str, season_id: str):
        self.conn = psycopg2.connect(db_url)
        # ...same interface as SQLiteStorage...
```

**SQL differences**:
- `?` → `%s` for parameters
- `INSERT ... ON CONFLICT ... DO UPDATE` → PostgreSQL uses same syntax (already compatible)
- `datetime('now')` → `NOW()`
- `PRAGMA journal_mode=WAL` → unnecessary (PostgreSQL handles concurrency natively)

**Factory in `deps.py`** — switch based on `DATABASE_URL` presence:

```python
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "sqlite")  # or "postgres"

def get_storage(season: str = "2025"):
    if STORAGE_BACKEND == "postgres":
        return PostgresStorage(DATABASE_URL, season)
    return SQLiteStorage(DB_PATH, season)
```

**Requirements to add**: `psycopg2-binary>=2.9`

**Env vars**:
| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `sqlite` | `"sqlite"` or `"postgres"` |
| `DATABASE_URL` | — | PostgreSQL connection string (Render auto-injects) |

---

## Phase 3 — Frontend-Ready (Effort: days-weeks)

### 6️⃣ Blob cache for computed EPA (JSON + compression)

**Problem**: Every API call reads from SQLite and deserializes numpy arrays. For a frontend, this is slow and exposes internal types.

**Solution** (statbotics pattern: GCS compressed JSON as primary data source):

After the pipeline finishes a season, write `teams_{season}.json.gz` to a blob store:

```python
# backend/src/services/blob_cache.py
import gzip, json, os

BLOB_DIR = os.environ.get("BLOB_DIR", "cache/blobs")

def write_teams_blob(season: str, teams: dict):
    payload = {str(k): {"total": v["mean"][0], "norm_epa": v["norm_epa"], ...}
               for k, v in teams.items()}
    path = os.path.join(BLOB_DIR, f"teams_{season}.json.gz")
    with gzip.open(path, "wt", encoding="ascii") as f:
        json.dump(payload, f)
```

**Frontend consumes**: GET `https://storage.googleapis.com/site_v1/teams_2025.json.gz` (or from Render disk). No API call needed.

**Backend site router**: `GET /v1/site/teams` returns from blob cache, pre-serialized, no numpy overhead.

**Where to store**:
- Local dev: `cache/blobs/`
- Render: persistent disk at `/opt/render/project/cache/blobs/`
- Future: S3/R2/CloudFlare R2

**Performance**: 738 teams × ~10 fields ≈ ~50KB uncompressed → ~5KB gzipped. Blazing fast.

---

### 7️⃣ Site-optimized API router (`/v1/site/`)

**Problem**: Current `/v1/` endpoints return numpy arrays, internal keys (`mean_json`, `var_json`), and raw EPA vectors. Frontends need clean JSON.

**Solution** (statbotics pattern: separate `/v3/site` router with pre-joined, pre-computed data):

```python
# backend/src/api/site.py
router = APIRouter(prefix="/v1/site", tags=["Site"])

@router.get("/teams")
def site_teams(season: str = "2025"):
    # Return from blob cache or pre-computed JSON
    ...

@router.get("/team/{team}")
def site_team(team: int, season: str = "2025"):
    # Join team + matches + events → single response
    ...

@router.get("/leaderboard")
def site_leaderboard(season: str = "2025"):
    # Top 100 teams by norm_epa, pre-computed
    ...
```

**What's different from `/v1/`**:
- No numpy arrays — all floats
- No internal keys (`mean_json`, `var_json`)
- Pre-joined data (team + matches + event type in one response)
- Can be served from blob cache (no DB hit)
- Sorted by common frontend metrics by default

---

## Summary

| # | Change | Effort | Impact | Priority |
|---|--------|--------|--------|----------|
| 1 | Remove auto-pipeline + `/v1/data/run` | 30 min | **Critical** — app boots, data persists | Must-have |
| 2 | `/v1/health` endpoint | 15 min | **High** — monitoring, debug | Must-have |
| 3 | Consistent response format | 30 min | Medium — API cleanliness | Should-have |
| 4 | Separate data service | 1-2 hr | High — pipeline isolation | Should-have |
| 5 | PostgreSQL external DB | 3-4 hr | **High** — data survival | Nice-to-have |
| 6 | Blob cache (JSON + gzip) | 2-3 hr | Medium — frontend speed | Nice-to-have |
| 7 | `/v1/site/` router | 2-3 hr | Medium — frontend readiness | Future |

**Recommended order**: 1 → 2 → 3 → 4 → 5 → (6 + 7 together)

Items 1-3 are the minimum to make the Render deployment stable. Items 4-5 make it robust. Items 6-7 prepare for a frontend.

---

## Files Changed Summary

| File | 1 | 2 | 3 | 5 |
|------|---|---|---|---|
| `backend/main.py` | ✅ | ✅ | | |
| `backend/src/api/data.py` (new) | ✅ | | | |
| `backend/src/api/season.py` | | | ✅ | |
| `tests/test_api.py` | | | ✅ | |
| `scoutkick-python/src/scoutkick_api/client.py` | | | ✅ | |
| `requirements.txt` | | | | ✅ |
| `backend/src/api/deps.py` | | | | ✅ |
| `backend/src/storage/__init__.py` | | | | ✅ |
| `backend/src/storage/postgres_storage.py` (new) | | | | ✅ |
| `backend/src/services/pipeline_service.py` | | | | ✅ |
| `render.yaml` | | | | ✅ |
| `ROADMAP.md` | | | | |

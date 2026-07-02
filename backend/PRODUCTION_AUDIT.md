# Production Audit — ScoutKick

Audit date: 2026-06-25
Goal: Find flaws that work in dev but cause catastrophic failures when deployed.

---

## 🔴 Critical (will cause outages or data loss in production)

### 1. Pickle deserialization = RCE

**Where:** `backend/src/data/ftcscout_api.py:47`

**Problem:** GraphQL responses are cached to disk with `pickle.dump`/`load`. Pickle is
not safe — a malicious `.p` file executes arbitrary code on load. If an attacker gains
any write access to `backend/cache/ftcscout/` (e.g. through a directory traversal, a
compromised dep, or a misconfigured shared host), they own the server.

**Fix:** Replace `pickle` with `json`. The data is already JSON-shaped (it comes from a
GraphQL API). Change `pickle.load` → `json.load`, `pickle.dump` → `json.dump`. Remove
the `.p` extension and use `.json`.

```python
# Before
with open(cache_path, "rb") as f:
    return pickle.load(f)

# After
with open(cache_path, "r") as f:
    return json.load(f)
```

---

### 2. `_in_memory_team_cache` — unbounded memory growth → OOM

**Where:** `backend/src/api/team.py:13`

**Problem:** `_in_memory_team_cache: Dict[int, Optional[Dict]]` is a module-level dict
that grows forever. Every unique team number ever looked up is stored. After 8329 teams
the dict holds 8329 entries. After multiple seasons, more. In a long-running production
server, this leaks memory until the process is killed by OOM killer.

**Fix:** Replace with `@lru_cache(maxsize=2048)` or a `TTLCache` from `cachetools`:

```python
from functools import lru_cache

@lru_cache(maxsize=2048)
def _fetch_team_info(team: int) -> Optional[Dict]:
    ...
```

Or with TTL:

```python
from cachetools import TTLCache

_team_cache: Dict[int, Optional[Dict]] = TTLCache(maxsize=4096, ttl=3600)
```

---

### 3. `list_teams` blocks the request thread making HTTP calls

**Where:** `backend/src/api/team.py:77`

**Problem:** For every team missing from the local `teams` table, the endpoint calls
`_fetch_team_info(team)` which does `requests.get("https://api.ftcscout.org/rest/v1/teams/{team}", timeout=10)`.
If FTC Scout is slow or down, the request handler blocks for up to 10 seconds per
missing team. With even a handful of missing teams, the uvicorn worker is pinned
indefinitely. Under concurrent traffic all workers block → 503.

**Fix:** Remove the live HTTP fallback from the request path. Return `None` for missing
names. Move backfill to a separate background job or the pipeline:

```python
info = infos.get(team)
# Remove the _fetch_team_info(team) call
results.append({
    "name": info.get("name") if info else None,
    ...
})
```

---

### 4. SQLite connection opened/closed on every query — lock storms under concurrency

**Where:** `backend/src/storage/sqlite_storage.py:28-41`

**Problem:** Every `_execute()` call opens `sqlite3.connect()`, sets WAL pragma, runs
the query, and closes. The pipeline's `ThreadPoolExecutor(max_workers=20)` calls
`save_team_info()` 8000+ times — 20 threads each opening their own connection, each
fighting over SQLite's single write lock. This causes `"database is locked"` errors
under load.

**Fix (option A — simplest):** Keep a persistent connection on the storage instance:

```python
class SQLiteStorage:
    def __init__(self, db_path, season_id):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_tables()
        self._check_schema_version()

    def _execute(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        ...
```

**Fix (option B — production):** Use a `psycopg2` connection pool / `pgbouncer` when
migrating to Postgres (already wired via `STORAGE_BACKEND=postgres`).

---

### 5. Health checks consume rate limit quota

**Where:** `backend/main.py:24, 130-140`

**Problem:** The `Limiter(default_limits=["200/minute", "10/second"])` applies to all
routes including `/v1/health`, `/v1/pipeline`, and `/`. Load balancers and monitoring
systems hitting these endpoints every 5 seconds (720 requests/minute per monitor) will
exhaust the 200/minute limit, causing 429 errors for real users.

**Fix:** Exempt health endpoints:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute", "10/second"])

@app.get("/v1/health")
@limiter.exempt
def health():
    ...
```

Or exempt them in middleware by path prefix.

---

### 6. Rate limiter breaks behind reverse proxy (Render/Cloudflare/Nginx)

**Where:** `backend/main.py:24`

**Problem:** `get_remote_address` uses `request.client.host` which is always the proxy
IP when behind a reverse proxy. Every user appears as the same IP, so rate limiting
applies globally — one user's burst can block everyone.

**Fix:** Use `X-Forwarded-For` header:

```python
from fastapi import Request

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "127.0.0.1"

limiter = Limiter(key_func=_get_client_ip, ...)
```

Also set `middleware=http` in slowapi to ensure middleware ordering is correct.

---

### 7. No `Content-Security-Policy` header

**Where:** `backend/main.py:86-93`

**Problem:** CSP is the most important security header. Without it, if the frontend
ever renders user-controlled content (team names, event names, etc.) unsafely, XSS
attacks succeed. The existing middleware adds `X-Frame-Options`, `X-XSS-Protection`,
and `Referrer-Policy` but omits CSP.

**Fix:** Add CSP to the security headers middleware:

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'"
)
```

Adjust for frontend assets if needed (e.g., `script-src 'self' 'unsafe-inline'` for
Vite dev server).

---

### 8. Schema migration can silently drop `team_matches`

**Where:** `backend/src/storage/sqlite_storage.py:186-188`

**Problem:** On startup, if `team_matches` table's SQL definition doesn't match the
expected pattern, the table is dropped:

```python
old_schema = conn.execute(
    "SELECT sql FROM sqlite_master WHERE tbl_name='team_matches' AND sql NOT LIKE '%event_code%match_id%'"
).fetchone()
if old_schema:
    conn.execute("DROP TABLE IF EXISTS team_matches")
```

One accidental deploy with a different schema version wipes all match data. No
backup, no confirmation.

**Fix:** Use a versioned migration system or at minimum add a safety check that
refuses to drop if any data exists:

```python
if old_schema:
    count = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
    if count > 0:
        raise RuntimeError(
            f"Refusing to drop team_matches with {count} rows. "
            "Delete the DB manually or write a proper migration."
        )
    conn.execute("DROP TABLE IF EXISTS team_matches")
```

---

## 🟠 High (degrades UX or causes partial failures under load)

### 9. `list_teams` loads ALL 8000+ teams into memory per request, filters in Python

**Where:** `backend/src/api/team.py:61-62`

**Problem:** `load_all_teams()` + `load_all_team_ranks()` + `load_all_teams_info()` load
every row from 3 tables, then filter by search/country/state in Python. For a
paginated endpoint returning 50 results, we pull 8000+ rows into dicts.

**Fix:** Move filters into SQL. Add optional `WHERE team LIKE ?`, `WHERE team_country = ?`,
`WHERE team_state = ?` to the query. Use `LIMIT ? OFFSET ?` in SQL too.

---

### 10. Clustering recomputed from scratch on every request

**Where:** `backend/src/api/cluster.py:26`

**Problem:** `compute_clusters()` runs `KMeans.fit()` on all teams every time someone
hits `/v1/clusters` or `/v1/team/{team}/playstyle`. K-means on 8000 teams takes
seconds. One spammer can DoS the server.

**Fix:** Cache the result keyed by (season, n_clusters):

```python
from functools import lru_cache

@lru_cache(maxsize=32)
def compute_clusters_cached(season: str, n_clusters: int) -> dict:
    ...
```

Invalidate the cache when the pipeline runs (bump a version key).

---

### 11. `get_noteworthy_matches` loads 168k+ rows into memory

**Where:** `backend/src/api/match.py:60`

**Problem:** `load_all_matches()` returns every row in `team_matches` for the season
(~42k matches × 4 teams = 168k rows). Then three full-dataset sorts in Python.

**Fix:** Push aggregation to SQL: `GROUP BY (event_code, match_id)` in SQL with
`MAX(ABS(epa_post - epa_pre))` for swings, `MIN(ABS(win_prob - 0.5))` for closest.
Or at minimum, cap the rows early with `LIMIT {limit * 10}`.

---

### 12. `list_matches` without team filter silently caps at 500 teams

**Where:** `backend/src/api/match.py:33`

**Problem:** `list(all_teams)[:500]` means teams 501+ are invisible via this
endpoint. No error or warning.

**Fix:** Either remove the cap (use SQL pagination) or document it and add a
`?team` query param requirement.

---

### 13. `/v1/site/teams/all` dumps all 8000+ teams in a single response

**Where:** `backend/src/api/site.py:28-36`

**Problem:** Returns all teams (~500KB JSON) in one response for autocomplete.
Every page load fetches this.

**Fix:** Add pagination (limit/offset) and debounce search on the frontend. Or use
a trie/prefix search on the backend.

---

### 14. `get_team_years` creates 7 storage instances per request

**Where:** `backend/src/api/team.py:172`

**Problem:** Loops through seasons, calling `create_storage(y["season"])` each time.
Each call runs `_ensure_tables()` + `_check_schema_version()`. For 7 seasons that's
14 unnecessary schema checks.

**Fix:** Create one storage instance and override `season_id` in the query:

```python
storage = create_storage("dummy")
for y in years:
    storage.season_id = y["season"]
    params = storage.load_team(team)
```

Or just query `team_seasons` directly with `WHERE team = ? ORDER BY season`.

---

## 🟡 Medium (worth fixing, no immediate danger)

### 15. FTC Scout cache: no file locking, race on concurrent writes

**Where:** `backend/src/data/ftcscout_api.py:44-57`

**Problem:** Multiple threads (from pipeline's ThreadPoolExecutor or concurrent
requests) can read/write the same cache file simultaneously. No locking. Could
produce corrupted cache.

**Fix:** Use a file lock:

```python
import fcntl

with open(cache_path, "wb") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    pickle.dump(data, f)
```

Or accept the risk (cache corruption is rare and non-fatal — it just refetches).

---

### 16. `save_team_info` called one-at-a-time, 8000+ connections

**Where:** `backend/src/storage/base_storage.py:416-418`, `sqlite_storage.py:58-109`

**Problem:** `save_team_info_bulk` loops calling `save_team_info` individually.
Each call opens/closes a SQLite connection. Same for `save_events_metadata_bulk`,
`save_all_teams_bulk`, `save_team_ranks_bulk`, `save_team_matches_bulk` in base
storage.

**Fix:** Each method should be overridden in `SQLiteStorage` to use `_execute_batch`,
just like `save_team_matches_bulk` already does in the override.

---

### 17. No `Vary: Origin` header with credentialed CORS

**Where:** `backend/main.py:63-69`

**Problem:** `allow_credentials=True` + no `Vary: Origin` can cause cache poisoning.
CDNs/browsers may serve cached responses from one origin to another when credentials
are involved.

**Fix:** Add `Vary: Origin` in the CORS middleware or security headers middleware:

```python
response.headers["Vary"] = "Origin"
```

---

### 18. `_cache_team_metadata` loads all teams just to find nothing to do

**Where:** `backend/src/services/pipeline_service.py:404`

**Problem:** After the pipeline, `_cache_team_metadata(all_teams)` calls
`load_all_teams_info()` which queries 8000+ rows, then returns immediately when all
are cached (which they should be since names come from GraphQL now).

**Fix:** Check if there are any missing teams by comparing team list size vs cached
count (cheap `SELECT COUNT(*)`), or just remove the redundant call since team names
are already cached in `_fetch_matches`.

---

### 19. `WAL pragma` set on every query — unnecessary round-trip

**Where:** `backend/src/storage/sqlite_storage.py:31, 47`

**Problem:** Setting `PRAGMA journal_mode=WAL` every time a connection opens is
wasteful — it only needs to be set once per connection lifetime. This is a problem
because every `_execute` opens a new connection.

**Fix:** Fix #4 (persistent connection) and move the pragma to `__init__`.

---

### 20. Two `TeamInfo` classes defined — second silently wins

**Where:** `backend/src/api/schemas.py:240-249` and `254-261`

**Problem:** `TeamInfo` is defined twice. The second definition (with `team`, `name`,
`school_name`, `city`, `state`, `country`, `rookie_year`) overwrites the first (which
had `sponsors` and `website`). The FTCScout proxy endpoint uses the first, but Pydantic
resolves to the second.

**Fix:** Rename one, or merge both into a single class.

---

## Summary

| Priority | Count | Fix effort |
|----------|-------|------------|
| 🔴 Critical | 8 | 1-2 days |
| 🟠 High | 6 | 1-2 days |
| 🟡 Medium | 6 | <1 day |

**Quick wins (easy fixes that prevent the worst outcomes):**
1. Replace `pickle` with JSON (30 min)
2. Replace `_in_memory_team_cache` with `lru_cache` (15 min)
3. Remove live HTTP fallback from `list_teams` (30 min)
4. Exempt health endpoints from rate limit (15 min)
5. Add `X-Forwarded-For` support to rate limiter (15 min)

**Biggest architectural change (most impactful):**
- Persistent SQLite connection / connection pooling (solves #4, #14, #16, #19)

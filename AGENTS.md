# ScoutKick — agent guide

## Repo layout

ScoutKick is a monorepo with two independent projects connected by a REST API:

- **`backend/`** — Python FastAPI server (EPA ratings for FTC)
- **`scoutkick-python/`** — PyPI package (`pip install scoutkick-api`) — zero-dependency client

No CI workflows exist yet (`.github/workflows/` is empty).

---

## Backend (Python)

### Commands

```powershell
$env:PYTHONPATH="."
python backend/main.py                        # Start dev server on :8000
python -m pytest backend/tests/ -v            # Run all ~197 tests
python -m pytest backend/tests/test_api.py -v # API tests only
python backend/run_all_seasons.py             # Run pipeline for all cached seasons
```

### Non-obvious facts

- **`PYTHONPATH=.` is required** for both running and testing. Import paths reference `backend.src.…`.
- Tests use `unittest`, **not** `pytest`. API tests (`test_api.py`) spawn a real uvicorn process and hit it via `urllib` — they need the server to already have cached DB data.
- Integration tests (`test_integration.py`) use in-memory SQLite with fake match data — no external API calls.
- Cache lives in `backend/cache/` (gitignored). Contains `epa_data.db` and `ftcscout/*.p`.
- Linting: `ruff` (line-length=100, double quotes). Type checking: `pyright` (basic mode).
- Supported seasons: `2019` through `2025` (hardcoded in `run_all_seasons.py:16`).

### Env vars

| Var | Default | Notes |
|-----|---------|-------|
| `EPA_DB_PATH` | `backend/cache/epa_data.db` | Override for production (Render: `/opt/render/project/cache/epa_data.db`) |
| `FTCSCOUT_CACHE_DIR` | `backend/cache/ftcscout` | GraphQL response cache |
| `STORAGE_BACKEND` | `sqlite` | Set to `postgres` to use `DATABASE_URL` |
| `PYTHONPATH` | — | **Must be `.`** for all commands |

### First run

The server starts with an empty DB. `POST /v1/data/run?season=2025` fetches FTC Scout data and computes EPA. On Render, persistent disk preserves the cache across deploys.

---

## Python Client (`scoutkick-python/`)

PyPI package `scoutkick-api` — zero-dependency client using only `urllib` + `json`.

### Build & publish

```powershell
cd scoutkick-python
pip install build
python -m build                          # Produces .tar.gz + .whl in dist/
python -m twine upload dist/*            # Requires PyPI API token
```

### Architecture

- `src/scoutkick_api/client.py` — single-file `ScoutKick` class wrapping all API endpoints.
- All methods return raw `dict` or `PaginatedResponse(value, count)` dataclass.
- `ScoutKickError` raised on HTTP errors or connection failures.
- Default base URL: `https://scoutkick.onrender.com`. Override with `ScoutKick(base_url="http://127.0.0.1:8000")` for local dev.

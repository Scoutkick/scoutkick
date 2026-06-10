# ScoutKick

Expected Points Added (EPA) rating system for FIRST Tech Challenge (FTC), ported from [Statbotics](https://statbotics.io).

Pulls match data from `api.ftcscout.org/graphql`, computes EPA ratings via an EWMA learning loop, and serves them through a FastAPI REST API.

**Live deployment**: [`https://scoutkick.onrender.com`](https://scoutkick.onrender.com) (docs at `/docs`)

---

## Quick Start

```bash
$env:PYTHONPATH="."
python backend/main.py          # Start API server (http://127.0.0.1:8000)
```

First run triggers the pipeline to fetch & process matches. Cached data stored in `cache/epa_data.db`.

To populate the database:
```bash
curl -X POST "http://127.0.0.1:8000/v1/data/run?season=2025"
curl http://127.0.0.1:8000/v1/data/status   # Check progress
```

---

## Python Client

Zero-dependency client (pure `urllib` + `json`):

```bash
pip install git+https://github.com/Cicchy/scoutkick.git#subdirectory=scoutkick-python
```

```python
from scoutkick_api import ScoutKick

sk = ScoutKick()  # defaults to https://scoutkick.onrender.com
# or locally:  ScoutKick(base_url="http://127.0.0.1:8000")

sk.get_team(26914)
sk.predict(red=[26914, 32736], blue=[23400, 24599])
sk.get_teams(season="2025", limit=10)
sk.compare(teams=[26914, 32736])
```

---

## API

All list endpoints return `{"value": [...], "count": N}`. Single-resource endpoints return the object directly.

### Pipeline

| Endpoint | Description |
|----------|-------------|
| `POST /v1/data/run?season=2025` | Trigger EPA pipeline (background task) |
| `GET /v1/data/status` | Pipeline state: `running`, `done`, `pending` |

### Seasons

| Endpoint | Description |
|----------|-------------|
| `GET /v1/seasons` | List cached seasons |
| `GET /v1/season/{season}` | Season metadata (score_mean, score_sd, num_matches, num_teams) |

### Teams

| Endpoint | Description |
|----------|-------------|
| `GET /v1/teams?season=2025` | Paginated team list, sorted by any metric |
| `GET /v1/team/{team}?season=2025` | Team season stats + `team_matches` array (EPA evolution) |
| `GET /v1/team/{team}/events?season=2025` | Per-event EPA stats |
| `GET /v1/team/{team}/matches?season=2025` | Per-match EPA history |

### Events

| Endpoint | Description |
|----------|-------------|
| `GET /v1/events?season=2025` | All events with aggregate EPA stats |
| `GET /v1/event/{code}?season=2025` | Event detail with team list |
| `GET /v1/event/{code}/matches?season=2025` | Event match list |

### Matches

| Endpoint | Description |
|----------|-------------|
| `GET /v1/matches?season=2025` | Global match list (filterable by team, event, elim) |
| `GET /v1/match/{event}/{match}?season=2025` | Single match detail |

### Predict

| Endpoint | Description |
|----------|-------------|
| `GET /v1/predict?red=26914,32736&blue=23400,24599` | Predict match outcome + scores |
| `GET /v1/compare?teams=26914,32736,23400` | Side-by-side team comparison |

---

## Architecture

```
scoutkick/
├── backend/
│   ├── main.py                        # FastAPI entry point
│   ├── deploy/
│   │   └── render.yaml                # Render deployment config
│   ├── src/
│   │   ├── core/
│   │   │   ├── math.py                # SkewNormal, unit_sigmoid
│   │   │   └── constants.py           # Tunable EPA parameters
│   │   ├── data/
│   │   │   ├── cleaner.py             # Season-specific ETL (CleanerRegistry)
│   │   │   ├── ftcscout_api.py        # GraphQL fetcher
│   │   │   └── read_ftcscout.py       # Cache layer
│   │   ├── services/
│   │   │   ├── epa_service.py         # EPAEngine (prediction + update)
│   │   │   ├── pipeline_service.py    # EPAPipeline orchestrator
│   │   │   ├── calibrate.py           # score_sd calibration
│   │   │   ├── init_epa.py            # Initial rating logic
│   │   │   ├── complementarity.py     # Team synergy analysis
│   │   │   ├── trajectory.py          # Rating trajectory projection
│   │   │   └── clustering.py          # Team clustering
│   │   ├── storage/
│   │   │   ├── __init__.py            # get_db_path(), create_storage() factory
│   │   │   ├── base_storage.py        # Abstract base (Template Method)
│   │   │   ├── sqlite_storage.py      # SQLite implementation
│   │   │   └── postgres_storage.py    # PostgreSQL implementation
│   │   └── api/
│   │       ├── router.py, deps.py
│   │       ├── season.py, team.py, event.py, match.py
│   │       ├── predict.py, data.py, cluster.py
│   ├── tests/
│   │   ├── test_engine.py             # Unit tests (~82)
│   │   ├── test_integration.py        # Integration tests (20)
│   │   ├── test_api.py                # API endpoint tests (20)
│   │   ├── test_init_epa.py           # Init EPA unit tests
│   │   ├── test_calibrate.py          # Calibration tests
│   │   └── ...
│   ├── cache/                         # Runtime data (gitignored)
│   ├── pyproject.toml
│   └── requirements.txt
├── scoutkick-python/                  # pip-installable client package
│   └── src/scoutkick_api/client.py
├── CLAUDE.md
├── README.md
├── LICENSE
└── .todos.md
```

---

## How It Works

1. **Fetch** — Pulls match data from `api.ftcscout.org/graphql` using per-season GraphQL fragments. Cached in `cache/ftcscout/*.p`.
2. **Clean** — `BaseCleaner` subclasses map alliance scores to a fixed 32-dim EPA vector. 7 seasons supported (2019–2025).
3. **Learn** — EWMA loop. Each team is a `SkewNormal` distribution. Prediction error split equally across 2 alliance members, updates mean/variance/skewness.
4. **Calibrate** — Computes `score_sd` and component-mean baselines from the match dataset.
5. **Serve** — Results stored in SQLite (or PostgreSQL), served via FastAPI.

### Key parameters

| Parameter | Value |
|-----------|-------|
| Learning rate | `alpha = 1 / (1 + n * 0.1)` |
| Error attribution | Split equally across 2 teammates |
| Elimination weight | 0.33 |
| Initial mean (total) | 20.0 |
| Initial variance | 100.0 |
| Norm mean (for display) | 1500 |

### Vector (2025)

| Index | Component |
|-------|-----------|
| 0 | Total EPA (`preFoulTotal`) |
| 1 | Auto EPA |
| 2 | Teleop EPA |
| 3 | Endgame EPA |
| 4–6 | Ranking Points (binary, RP1–RP3) |
| 7 | Auto Classified |
| 8 | Teleop Classified |
| 9 | Teleop Depot |

Seasons 2019–2023 use 4 dims, 2024 uses 10, 2025 uses 10 active dims in a 32-slot vector.

---

## Tests

```bash
$env:PYTHONPATH="."
python -m pytest backend/tests/ -v           # All ~197 tests
python -m pytest backend/tests/ -v -k "api"  # API tests only
```

---

## Deploy

Deployed via [`render.yaml`](backend/deploy/render.yaml) on Render. A `git push` to `master` auto-deploys. Persistent disk at `/opt/render/project/cache/` stores both `epa_data.db` and `ftcscout/` API cache.

---

## Data Source

All match data sourced from [FTC Scout](https://ftcscout.org) via their public GraphQL API (`api.ftcscout.org/graphql`).

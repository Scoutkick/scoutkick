# ScoutKick

![ScoutKick](logo.png)

[![PyPI](https://img.shields.io/pypi/v/scoutkick-api)](https://pypi.org/project/scoutkick-api/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](https://choosealicense.com/licenses/mit/)
[![Render](https://img.shields.io/badge/deploy-Render-46e3b7)](https://scoutkick.onrender.com)

Expected Points Added (EPA) rating system for FIRST Tech Challenge (FTC), ported from [Statbotics](https://statbotics.io). Pulls match data from `api.ftcscout.org/graphql`, computes EPA ratings via an EWMA learning loop, and serves them through a FastAPI REST API.

- **Live API**: [`scoutkick.onrender.com`](https://scoutkick.onrender.com) (docs at `/docs`)
- **Python client**: `pip install scoutkick-api`

---

## Installation

### API server

```bash
$env:PYTHONPATH="."
pip install -r backend/requirements.txt
python backend/main.py
```

The server starts on `http://127.0.0.1:8000`. First run has an empty database — populate it with:

```bash
curl -X POST "http://127.0.0.1:8000/v1/data/run?season=2025"
curl http://127.0.0.1:8000/v1/data/status
```

### Python client

```bash
pip install scoutkick-api
```

```python
from scoutkick_api import ScoutKick

sk = ScoutKick()  # defaults to https://scoutkick.onrender.com
# for local dev: ScoutKick(base_url="http://127.0.0.1:8000")

sk.get_team(26914)
sk.predict(red=[26914, 32736], blue=[23400, 24599])
sk.get_teams(season="2025", limit=10)
sk.compare(teams=[26914, 32736])
```

### From source

```bash
pip install git+https://github.com/Cicchy/scoutkick.git#subdirectory=scoutkick-python
```

---

## Usage

### All client methods

| Method | Description |
|--------|-------------|
| `get_seasons()` | List cached seasons |
| `get_season(season)` | Season metadata |
| `get_teams(...)` | Paginated team list (sort, search, filter) |
| `get_team(team, season)` | Full EPA breakdown + match history |
| `get_team_events(...)` | Per-event EPA stats |
| `get_team_matches(...)` | Per-match EPA history |
| `get_team_info(team)` | Team name/location from FTC Scout |
| `get_team_playstyle(team)` | Playstyle cluster classification |
| `get_team_trajectory(team)` | EPA growth trajectory |
| `get_events(...)` | All events with aggregate EPA stats |
| `get_event(code, season)` | Event detail with team list |
| `get_event_matches(...)` | Event match list |
| `get_matches(...)` | Global match list (filterable) |
| `get_match(event, match)` | Single match detail |
| `predict(red, blue)` | Predict match outcome |
| `compare(teams)` | Side-by-side team comparison |
| `get_clusters(...)` | Playstyle clusters for all teams |
| `get_complementarity(t1, t2)` | Playstyle complementarity score |
| `get_alliance_partners(team)` | Best alliance partners |
| `get_trajectory_clusters(...)` | Growth trajectory clusters |
| `run_pipeline(season)` | Trigger EPA pipeline |
| `get_pipeline_status()` | Pipeline state |

### API endpoints

All list endpoints return `{"value": [...], "count": N}`. Single-resource endpoints return the object directly.

| Endpoint | Description |
|----------|-------------|
| `POST /v1/data/run?season=2025` | Trigger EPA pipeline |
| `GET /v1/data/status` | Pipeline state |
| `GET /v1/seasons` | List cached seasons |
| `GET /v1/season/{season}` | Season metadata |
| `GET /v1/teams?season=2025` | Paginated team list |
| `GET /v1/team/{team}?season=2025` | Team EPA + match history |
| `GET /v1/team/{team}/events?season=2025` | Per-event EPA stats |
| `GET /v1/team/{team}/matches?season=2025` | Per-match EPA history |
| `GET /v1/events?season=2025` | All events with EPA stats |
| `GET /v1/event/{code}?season=2025` | Event detail with team list |
| `GET /v1/event/{code}/matches?season=2025` | Event match list |
| `GET /v1/matches?season=2025` | Global match list |
| `GET /v1/match/{event}/{match}?season=2025` | Single match detail |
| `GET /v1/predict?red=...&blue=...` | Predict match outcome |
| `GET /v1/compare?teams=...` | Side-by-side team comparison |

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

### EPA vector (2025)

| Index | Component |
|-------|-----------|
| 0 | Total EPA (`preFoulTotal`) |
| 1 | Auto EPA |
| 2 | Teleop EPA |
| 3 | Endgame EPA |
| 4–6 | Ranking Points (RP1–RP3) |
| 7 | Auto Classified |
| 8 | Teleop Classified |
| 9 | Teleop Depot |

Seasons 2019–2023 use 4 dims, 2024 uses 10, 2025 uses 10 active dims in a 32-slot vector.

---

## Architecture

```
scoutkick/
├── backend/                    # FastAPI server
│   ├── main.py                 # Entry point
│   ├── deploy/render.yaml      # Render deployment config
│   ├── src/
│   │   ├── core/               # Math, constants
│   │   ├── data/               # FTC Scout fetcher, cleaner, cache
│   │   ├── services/           # EPA engine, pipeline, clustering
│   │   ├── storage/            # SQLite / Postgres abstraction
│   │   └── api/                # Route handlers (REST)
│   ├── tests/                  # ~197 tests (unittest)
│   ├── cache/                  # Runtime data (gitignored)
│   └── requirements.txt
├── scoutkick-python/           # PyPI package
│   └── src/scoutkick_api/      # Zero-dependency client
├── AGENTS.md                   # Agent guide
└── README.md
```

---

## Tests

```bash
$env:PYTHONPATH="."
python -m pytest backend/tests/ -v           # All ~197 tests
python -m pytest backend/tests/ -v -k "api"  # API tests only
```

---

## Deploy

Deployed via [`render.yaml`](backend/deploy/render.yaml) on Render. `git push` to `master` auto-deploys. Persistent disk at `/opt/render/project/cache/` stores both `epa_data.db` and `ftcscout/` API cache.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change. Make sure to update tests as appropriate.

---

## Support

- Open an [issue](https://github.com/Cicchy/scoutkick/issues) for bugs or feature requests
- Join the FTC Discord server to discuss

---

## License

[MIT](LICENSE)

---

## Project status

Active development. Seasons 2019–2025 are supported. The API is live at `scoutkick.onrender.com`. Data sourced from [FTC Scout](https://ftcscout.org) via their public GraphQL API.

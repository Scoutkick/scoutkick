# ScoutKick API Client

Zero-dependency Python client for the [ScoutKick](https://scoutkick.onrender.com) EPA rating system for FIRST Tech Challenge.

ScoutKick computes **Expected Points Added (EPA)** — a skill rating that measures how many points a team contributes to their alliance beyond what an average team would. Modeled after [Statbotics](https://statbotics.io) for FRC, ScoutKick brings the same kind of analysis to FTC.

**No external dependencies.** Uses only `urllib`, `json`, and `dataclasses` from the Python standard library.

---

## Installation

```bash
pip install scoutkick-api
```

Requires Python **3.9+**.

---

## Quick Start

```python
from scoutkick_api import ScoutKick

sk = ScoutKick()  # defaults to https://scoutkick.onrender.com

# Get a team's EPA breakdown
team = sk.get_team(26914)
print(team["total"], team["norm_epa"])

# Predict a match outcome
result = sk.predict(red=[26914, 32736], blue=[23400, 24599])
print(f"Red win prob: {result['red_win_prob']:.1%}")

# Compare teams side by side
compare = sk.compare(teams=[26914, 32736, 24599])
for t in compare["teams"]:
    print(f"Team {t['team']}: total={t['total']:.1f}")

# Top 10 teams by EPA
teams = sk.get_teams(season="2025", limit=10)
for t in teams.value:
    print(f"#{t['team']}: {t['norm_epa']:.3f}")
```

---

## Client API Reference

All methods return raw `dict` responses from the API, except paginated endpoints which return a `PaginatedResponse` named tuple.

### Constructor

```python
ScoutKick(base_url="https://scoutkick.onrender.com", timeout=30)
```

| Param | Default | Description |
|-------|---------|-------------|
| `base_url` | `"https://scoutkick.onrender.com"` | API root URL. Use `"http://127.0.0.1:8000"` for local dev. |
| `timeout` | `30` | Request timeout in seconds. |

### Health

```python
sk.health() -> dict
```

Returns server health status including season availability and pipeline state.

### Seasons

```python
sk.get_seasons() -> PaginatedResponse
```

List all seasons that have pipeline data stored.

```python
sk.get_season(season: str) -> dict
```

| Param | Description |
|-------|-------------|
| `season` | Season year, e.g. `"2025"`. |

Returns metadata: `score_mean`, `score_sd`, `num_matches`, `num_teams`, `updated_at`.

### Teams

```python
sk.get_teams(
    season: str = "2025",
    metric: str = "norm_epa",
    ascending: bool = False,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
) -> PaginatedResponse
```

| Param | Default | Description |
|-------|---------|-------------|
| `season` | `"2025"` | Season year. |
| `metric` | `"norm_epa"` | Sort field: `norm_epa`, `total`, `auto`, `teleop`, `endgame`, `team`, `matches`. |
| `ascending` | `False` | Sort ascending. |
| `limit` | `50` | Items per page (max 1000). |
| `offset` | `0` | Pagination offset. |
| `search` | `None` | Team number prefix filter. |

```python
sk.get_team(team: int, season: str = "2025") -> dict
```

Returns full EPA breakdown: `total`, `auto`, `teleop`, `endgame`, `mean`, `var`, `skew`, `norm_epa`, plus all matches with pre/post EPA and win probability.

```python
sk.get_team_events(
    team: int,
    season: str = "2025",
    event_type: str | None = None,
    metric: str = "epa_mean",
    ascending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedResponse
```

| Param | Default | Description |
|-------|---------|-------------|
| `event_type` | `None` | Filter by event type (e.g. `"Championship"`). |
| `metric` | `"epa_mean"` | Sort field: `epa_mean`, `epa_max`, `epa_start`, `count`. |

```python
sk.get_team_matches(
    team: int,
    season: str = "2025",
    event: str | None = None,
    elim: bool | None = None,
    metric: str = "match_id",
    ascending: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedResponse
```

| Param | Default | Description |
|-------|---------|-------------|
| `event` | `None` | Filter by event code. |
| `elim` | `None` | `True` for elimination matches, `False` for quals, `None` for all. |

```python
sk.get_team_info(team: int) -> dict
```

Team metadata from FTC Scout: `name`, `school_name`, `city`, `country`, `rookie_year`, `website`.

```python
sk.get_team_playstyle(team: int, season: str = "2025", n_clusters: int = 8) -> dict
```

```python
sk.get_team_trajectory(team: int, season: str = "2025") -> dict
```

### Events

```python
sk.get_events(
    season: str = "2025",
    event_type: str | None = None,
    metric: str = "epa_max",
    ascending: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedResponse
```

```python
sk.get_event(event_code: str, season: str = "2025") -> dict
```

All teams at an event sorted by `epa_start` descending.

```python
sk.get_event_matches(
    event_code: str,
    season: str = "2025",
    elim: bool | None = None,
    metric: str = "match_id",
    ascending: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> PaginatedResponse
```

```python
sk.get_events_info(season: str = "2025", event_type: str | None = None) -> PaginatedResponse
```

Events with FTC Scout metadata merged with ScoutKick EPA data.

```python
sk.get_event_info(event_code: str, season: str = "2025") -> dict
```

### Matches

```python
sk.get_matches(
    season: str = "2025",
    event: str | None = None,
    elim: bool | None = None,
    team: int | None = None,
    metric: str = "processed_at",
    ascending: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> PaginatedResponse
```

```python
sk.get_match(event_code: str, match_id: str, season: str = "2025") -> dict
```

### Predict & Compare

```python
sk.predict(red: list[int], blue: list[int], season: str = "2025") -> dict
```

Predict match outcome. Each list must contain exactly **2 team numbers**.

Returns per-team EPA components, `red_win_prob`, `blue_win_prob`, and predicted scores.

```python
sk.compare(teams: list[int], season: str = "2025") -> dict
```

Compare 2+ teams side by side. Returns component breakdown (`total`, `auto`, `teleop`, `endgame`, `variance`, `skew`, `matches`) for each.

### Clusters & Complementarity

```python
sk.get_clusters(season: str = "2025", n_clusters: int = 8) -> dict
```

Playstyle clusters (K-means on EPA vector similarity).

```python
sk.get_complementarity(team1: int, team2: int, season: str = "2025") -> dict
```

How well two teams' playstyles mesh.

```python
sk.get_alliance_partners(team: int, season: str = "2025", top_n: int = 10) -> dict
```

Best alliance partners for a team ranked by complementarity.

```python
sk.get_trajectory_clusters(season: str = "2025", n_clusters: int = 4) -> dict
```

Growth trajectory clusters — groups teams by how their EPA evolved across the season.

### Site (Frontend Bundle Endpoints)

These endpoints bundle multiple data sources into a single payload, optimized for frontend use.

```python
sk.get_site_teams_all() -> list[dict]
```

Lightweight list of all teams (number + name) for search autocomplete.

```python
sk.get_site_events_all(season: str = "2025") -> list[dict]
```

Lightweight list of events (code, name, dates) for search/filter UI.

```python
sk.get_site_team(team: int, season: str = "2025") -> dict
```

Bundled team page: info + EPA summary + ranks + match history + season meta + event name map.

```python
sk.get_site_event(event_code: str, season: str = "2025") -> dict
```

Bundled event page: metadata + standings + qual/elim matches + season meta.

```python
sk.get_site_match(event_code: str, match_id: str, season: str = "2025") -> dict
```

Bundled match page: per-team EPA pre/post/win_prob + event name + alliance totals + season meta.

---

## REST API Reference

The ScoutKick REST API is available directly at `https://scoutkick.onrender.com`. All endpoints are prefixed with `/v1/`. OpenAPI docs are available at `/docs`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root: version, docs URL, pipeline status. |
| GET | `/v1/health` | Server health + season availability. |
| GET | `/v1/pipeline` | Current pipeline state. |
| GET | `/v1/data/status` | Pipeline status (read-only). |
| GET | `/v1/seasons` | List all seasons with data. |
| GET | `/v1/season/{season}` | Season metadata. |
| GET | `/v1/teams` | List teams with EPA. |
| GET | `/v1/team/{team}` | Single team EPA breakdown. |
| GET | `/v1/team/{team}/years` | Team EPA across all seasons. |
| GET | `/v1/team/{team}/events` | Events a team participated in. |
| GET | `/v1/team/{team}/event/{event_code}` | Team at a specific event. |
| GET | `/v1/team/{team}/matches` | Team's matches with EPA deltas. |
| GET | `/v1/team/{team}/info` | Team metadata (FTC Scout). |
| GET | `/v1/team/{team}/playstyle` | Playstyle cluster. |
| GET | `/v1/team/{team}/trajectory` | EPA growth trajectory. |
| GET | `/v1/events` | List events with EPA stats. |
| GET | `/v1/events/info` | Events with FTC Scout metadata. |
| GET | `/v1/event/{event_code}` | Event standings. |
| GET | `/v1/event/{event_code}/info` | Event metadata + EPA. |
| GET | `/v1/event/{event_code}/matches` | Event match list. |
| GET | `/v1/event/{event_code}/predictions` | All match predictions for an event. |
| GET | `/v1/matches` | List matches with EPA. |
| GET | `/v1/match/{event_code}/{match_id}` | Single match detail. |
| GET | `/v1/predict` | Predict match outcome. |
| GET | `/v1/compare` | Compare teams. |
| GET | `/v1/clusters` | Playstyle clusters. |
| GET | `/v1/complementarity` | Team complementarity. |
| GET | `/v1/complementarity/{team}/partners` | Best partners. |
| GET | `/v1/trajectory/clusters` | Growth trajectory clusters. |
| GET | `/v1/districts` | FTC districts. |
| GET | `/v1/site/teams/all` | Team autocomplete data. |
| GET | `/v1/site/events/all` | Event autocomplete data. |
| GET | `/v1/site/team/{team}` | Bundled team page. |
| GET | `/v1/site/event/{event_code}` | Bundled event page. |
| GET | `/v1/site/match/{event_code}/{match_id}` | Bundled match page. |
| GET | `/v1/site/upcoming_matches` | Recent matches. |
| GET | `/v1/teams/{season}/distributions` | EPA distribution stats. |

### Common Query Parameters

| Param | Type | Description |
|-------|------|-------------|
| `season` | `str` | Season year (default `"2025"`). Supported: 2019–2025. |
| `limit` | `int` | Items per page. |
| `offset` | `int` | Pagination offset. |
| `metric` | `str` | Sort field. |
| `ascending` | `bool` | Sort direction. |

---

## Response Schemas

### `PaginatedResponse`

Returned by all list endpoints.

| Field | Type | Description |
|-------|------|-------------|
| `value` | `list` | The page of items. |
| `count` | `int` | Total items across all pages. |

### Team fields

| Field | Description |
|-------|-------------|
| `team` | Team number. |
| `total` | Overall EPA rating. |
| `auto` | Autonomous EPA component. |
| `teleop` | Teleop EPA component. |
| `endgame` | Endgame EPA component. |
| `norm_epa` | Normalized EPA (z-score). |
| `matches` | Match count. |

### Match fields

| Field | Description |
|-------|-------------|
| `event_code` | Event identifier. |
| `match_id` | Match identifier (e.g. `"qm1"`). |
| `team` | Team number. |
| `epa_pre` | EPA before the match. |
| `epa_post` | EPA after the match. |
| `win_prob` | Calculated win probability (0–1). |
| `is_elim` | Whether this is an elimination match. |
| `processed_at` | Processing timestamp. |

### Prediction fields

| Field | Description |
|-------|-------------|
| `red_teams` / `blue_teams` | Per-team EPA components. |
| `red_win_prob` / `blue_win_prob` | Win probabilities. |
| `predicted_red` / `predicted_blue` | Predicted score components (`auto`, `teleop`, `endgame`, `total`). |

---

## Error Handling

All errors raise `ScoutKickError`:

```python
from scoutkick_api import ScoutKick, ScoutKickError

sk = ScoutKick()
try:
    team = sk.get_team(999999)
except ScoutKickError as e:
    print(e)  # "HTTP 404: Team '999999' not found"
```

Two error types are both mapped to `ScoutKickError`:

- **HTTP errors** (4xx/5xx): Message includes the status code and FastAPI error detail.
- **Connection failures**: DNS, network, or timeout issues.

---

## Pagination

All list endpoints return a `PaginatedResponse(value, count)`. Use `limit` and `offset` to page through results:

```python
page = sk.get_teams(season="2025", limit=100, offset=0)
print(f"Showing {len(page.value)} of {page.count} teams")
```

The `count` field reflects the **total** number of items available, not just the current page.

---

## Local Development

```python
sk = ScoutKick(base_url="http://127.0.0.1:8000")
```

Start the ScoutKick backend locally (requires the backend repo):

```bash
cd backend
$env:PYTHONPATH="."
python main.py
```

See the [backend documentation](https://github.com/Cicchy/scoutkick) for setup instructions.

---

## Supported Seasons

2019, 2020, 2021, 2022, 2023, 2024, 2025

---

## How EPA Works

For a detailed explanation of the EPA model — derivation from Elo, multi-dimensional team state, match prediction, attribution, EWMA updates, normalization, playstyle clustering, and complementarity — see the [root README](https://github.com/Cicchy/scoutkick#the-epa-model).

---

## Links

- **Homepage**: https://scoutkick.onrender.com
- **API Docs**: https://scoutkick.onrender.com/docs (auto-generated Swagger UI)
- **Source**: https://github.com/Cicchy/scoutkick
- **PyPI**: https://pypi.org/project/scoutkick-api/

---

## License

MIT

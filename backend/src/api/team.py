from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from backend.src.api.deps import get_storage
from backend.src.api.schemas import TeamDetail, TeamMatch, TeamSummary, TeamYearSummary, TeamEventDetail, PaginatedResponse
from backend.src.api.utils import sort_and_page
from backend.src.core.constants import CURR_YEAR
from backend.src.storage import create_storage

router = APIRouter(tags=["Team"])


@router.get("/v1/teams", response_model=PaginatedResponse)
def list_teams(
    season: str = Query(CURR_YEAR, description="Season year"),
    metric: str = Query("norm_epa", description="Sort metric: norm_epa, total, auto, teleop, endgame"),
    ascending: bool = Query(False),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Filter by team number prefix"),
    country: Optional[str] = Query(None, description="Filter by country code"),
    state: Optional[str] = Query(None, description="Filter by state/province"),
):
    """List all teams in a season, sorted by a metric. Supports pagination, search, and location filters."""
    storage = get_storage(season)
    teams = storage.load_all_teams()

    results = []
    for team, params in teams.items():
        if search is not None and search not in str(team):
            continue
        if country is not None and (params.get("team_country") or "").lower() != country.lower():
            continue
        if state is not None and (params.get("team_state") or "").lower() != state.lower():
            continue
        results.append({
            "team": team,
            "total": float(params["mean"][0]),
            "auto": float(params["mean"][1]),
            "teleop": float(params["mean"][2]),
            "endgame": float(params["mean"][3]),
            "norm_epa": params["norm_epa"],
            "matches": params["count"],
        })

    return sort_and_page(results, {
        "norm_epa": lambda x: x["norm_epa"] if x["norm_epa"] is not None else 0,
        "total": lambda x: x["total"],
        "auto": lambda x: x["auto"],
        "teleop": lambda x: x["teleop"],
        "endgame": lambda x: x["endgame"],
        "team": lambda x: x["team"],
        "matches": lambda x: x["matches"],
    }, metric, ascending, offset, limit, default_metric="norm_epa")


@router.get("/v1/team/{team}", response_model=TeamDetail)
def get_team(team: int, season: str = Query(CURR_YEAR)):
    """Get full EPA breakdown for a single team, including match history."""
    storage = get_storage(season)
    params = storage.load_team(team)
    if params is None:
        raise HTTPException(status_code=404, detail=f"Team {team} not found in season {season}")

    matches = storage.load_team_matches(team)
    team_matches = []
    for m in matches:
        team_matches.append({
            "event_code": m["event_code"],
            "match_id": m["match_id"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
            "is_elim": bool(m["is_elim"]),
            "processed_at": m["processed_at"],
        })

    return {
        "team": team,
        "season": season,
        "total": float(params["mean"][0]),
        "auto": float(params["mean"][1]),
        "teleop": float(params["mean"][2]),
        "endgame": float(params["mean"][3]),
        "mean": params["mean"].tolist(),
        "var": params["var"].tolist(),
        "skew": params["skew"],
        "n": params["n"],
        "count": params["count"],
        "norm_epa": params["norm_epa"],
        "team_matches": team_matches,
    }


@router.get("/v1/team/{team}/years", response_model=List[TeamYearSummary])
def get_team_years(team: int):
    """Get EPA data for a team across all seasons."""
    storage = create_storage(CURR_YEAR, "")
    years = storage.load_team_cross_season(team)
    if not years:
        raise HTTPException(status_code=404, detail=f"No data found for team {team}")

    result = []
    for y in years:
        s = create_storage(y["season"], "")
        params = s.load_team(team)
        ranks = s.load_all_team_ranks().get(team, {})
        mean = params["mean"] if params is not None else y["mean"]
        result.append({
            "season": y["season"],
            "total": float(mean[0]),
            "auto": float(mean[1]),
            "teleop": float(mean[2]),
            "endgame": float(mean[3]),
            "mean": mean.tolist() if hasattr(mean, 'tolist') else mean,
            "var": y["var"].tolist() if hasattr(y["var"], 'tolist') else y["var"],
            "skew": y["skew"],
            "n": y["n"],
            "count": y["count"],
            "norm_epa": y["norm_epa"],
            "rank": ranks.get("rank"),
            "country_rank": ranks.get("country_rank"),
            "state_rank": ranks.get("state_rank"),
        })
    return result


@router.get("/v1/team/{team}/event/{event_code}", response_model=TeamEventDetail)
def get_team_event(team: int, event_code: str, season: str = Query(CURR_YEAR)):
    """Get EPA data for a single team at a specific event."""
    storage = get_storage(season)
    events = storage.load_team_events_with_metadata(team)
    event = next((e for e in events if e["event_code"] == event_code), None)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Team {team} not found at event {event_code} in season {season}")
    if event.get("mean") is not None:
        event["mean"] = event["mean"].tolist()
    if event.get("var") is not None:
        event["var"] = event["var"].tolist()
    return event


@router.get("/v1/team/{team}/events", response_model=PaginatedResponse)
def get_team_events(
    team: int,
    season: str = Query(CURR_YEAR),
    event_type: Optional[str] = Query(None, description="Filter by event type (Qualifier, Championship, etc.)"),
    metric: str = Query("epa_mean", description="Sort metric: epa_mean, epa_max, epa_start, count"),
    ascending: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get all events a team participated in, with per-event EPA stats and event metadata."""
    storage = get_storage(season)
    events = storage.load_team_events_with_metadata(team)

    if event_type is not None:
        events = [e for e in events if e.get("event_type") == event_type]

    for e in events:
        if e.get("mean") is not None:
            e["mean"] = e["mean"].tolist()
        if e.get("var") is not None:
            e["var"] = e["var"].tolist()

    return sort_and_page(events, {
        "epa_mean": lambda x: x.get("epa_mean") or 0,
        "epa_max": lambda x: x.get("epa_max") or 0,
        "epa_start": lambda x: x.get("epa_start") or 0,
        "count": lambda x: x.get("count") or 0,
    }, metric, ascending, offset, limit, default_metric="epa_mean")


@router.get("/v1/team/{team}/matches", response_model=PaginatedResponse)
def get_team_matches(
    team: int,
    season: str = Query(CURR_YEAR),
    event: Optional[str] = Query(None),
    elim: Optional[bool] = Query(None),
    metric: str = Query("match_id", description="Sort metric: match_id, epa_pre, epa_post, win_prob"),
    ascending: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get all matches for a team with pre/post EPA and win probability."""
    storage = get_storage(season)
    matches = storage.load_team_matches(team)
    if event is not None:
        matches = [m for m in matches if m["event_code"] == event]
    if elim is not None:
        matches = [m for m in matches if m["is_elim"] == int(elim)]

    for m in matches:
        m["is_elim"] = bool(m["is_elim"])

    return sort_and_page(matches, {
        "match_id": lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"],
        "epa_pre": lambda x: x["epa_pre"] or 0,
        "epa_post": lambda x: x["epa_post"] or 0,
        "win_prob": lambda x: x["win_prob"] or 0,
    }, metric, ascending, offset, limit, default_metric="match_id")

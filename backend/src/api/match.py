from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from backend.src.api.deps import get_storage
from backend.src.api.schemas import MatchDetail, MatchSummary, PaginatedResponse
from backend.src.api.utils import sort_and_page
from backend.src.core.constants import CURR_YEAR

router = APIRouter(tags=["Match"])


@router.get("/v1/matches", response_model=PaginatedResponse)
def list_matches(
    season: str = Query(CURR_YEAR),
    event: Optional[str] = Query(None),
    elim: Optional[bool] = Query(None),
    team: Optional[int] = Query(None),
    metric: str = Query("processed_at", description="Sort metric: processed_at, match_id, epa_pre, epa_post, win_prob"),
    ascending: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List matches with pre/post EPA and win probability. Filterable by event, elim status, or team."""
    storage = get_storage(season)
    all_events = storage.load_team_events()
    all_teams = {e["team"] for e in all_events}

    if team is not None:
        if team not in all_teams:
            raise HTTPException(status_code=404, detail=f"Team {team} not found in season {season}")
        match_list = storage.load_team_matches(team)
    else:
        match_list = []
        for t in list(all_teams)[:50]:
            match_list.extend(storage.load_team_matches(t))

    if event is not None:
        match_list = [m for m in match_list if m["event_code"] == event]
    if elim is not None:
        match_list = [m for m in match_list if m["is_elim"] == int(elim)]

    for m in match_list:
        m["is_elim"] = bool(m["is_elim"])

    return sort_and_page(match_list, {
        "processed_at": lambda x: x["processed_at"] if "processed_at" in x else "",
        "match_id": lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"],
        "epa_pre": lambda x: x["epa_pre"] or 0,
        "epa_post": lambda x: x["epa_post"] or 0,
        "win_prob": lambda x: x["win_prob"] or 0,
    }, metric, ascending, offset, limit, default_metric="processed_at")


@router.get("/v1/noteworthy")
def get_noteworthy_matches(
    season: str = Query(CURR_YEAR, description="Season year"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return noteworthy matches: biggest EPA swings, biggest upsets, closest matches."""
    storage = get_storage(season)
    all_matches = storage.load_all_matches()
    if not all_matches:
        raise HTTPException(status_code=404, detail=f"No matches found for season {season}")

    # Group by (event_code, match_id) to get per-match aggregates
    match_groups: dict = {}
    for m in all_matches:
        key = (m["event_code"], m["match_id"])
        if key not in match_groups:
            match_groups[key] = {
                "event_code": m["event_code"],
                "match_id": m["match_id"],
                "is_elim": bool(m["is_elim"]),
                "teams": [],
            }
        match_groups[key]["teams"].append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "epa_delta": (m["epa_post"] or 0) - (m["epa_pre"] or 0),
            "win_prob": m["win_prob"],
        })

    matches_list = list(match_groups.values())

    # Biggest positive EPA swings
    by_delta = sorted(
        matches_list,
        key=lambda m: max(abs(t["epa_delta"]) for t in m["teams"]),
        reverse=True,
    )[:limit]

    # Biggest upsets (lowest win prob but won)
    upsets = []
    for m in matches_list:
        for t in m["teams"]:
            if t["win_prob"] is not None and t["win_prob"] < 0.3:
                upsets.append({**m, "upset_team": t["team"], "win_prob": t["win_prob"]})
    upsets = sorted(upsets, key=lambda x: x["win_prob"])[:limit]

    # Closest matches (win prob near 0.5)
    closest = sorted(
        matches_list,
        key=lambda m: min(abs((t["win_prob"] or 0.5) - 0.5) for t in m["teams"]),
    )[:limit]

    return {
        "season": season,
        "biggest_epa_swings": by_delta,
        "biggest_upsets": upsets,
        "closest_matches": closest,
    }


@router.get("/v1/match/{event_code}/{match_id}", response_model=MatchDetail)
def get_match(
    event_code: str,
    match_id: str,
    season: str = Query(CURR_YEAR),
):
    """Get detailed EPA data for all teams in a specific match."""
    storage = get_storage(season)
    all_matches = storage.load_event_matches(event_code)

    if not all_matches:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found")

    teams = []
    for m in all_matches:
        if m["match_id"] == match_id:
            teams.append({
                "team": m["team"],
                "epa_pre": m["epa_pre"],
                "epa_post": m["epa_post"],
                "win_prob": m["win_prob"],
                "is_elim": bool(m["is_elim"]),
            })

    if not teams:
        raise HTTPException(status_code=404, detail=f"Match {match_id} at {event_code} not found")

    return {
        "event_code": event_code,
        "match_id": match_id,
        "season": season,
        "is_elim": any(t.get("is_elim", False) for t in teams),
        "teams": teams,
    }

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from backend.src.api.deps import get_storage
from backend.src.api.schemas import EventDetail, EventPredictionsResponse, PaginatedResponse
from backend.src.api.utils import sort_and_page
from backend.src.core.constants import CURR_YEAR

router = APIRouter(tags=["Event"])


@router.get("/v1/events", response_model=PaginatedResponse)
def list_events(
    season: str = Query(CURR_YEAR),
    event_type: Optional[str] = Query(None, description="Filter by event type (Qualifier, Championship, etc.)"),
    region: Optional[str] = Query(None, description="Filter by region code"),
    country: Optional[str] = Query(None, description="Filter by country (from event location)"),
    state: Optional[str] = Query(None, description="Filter by state/province (from event location)"),
    search: Optional[str] = Query(None, description="Filter by event name or code substring"),
    metric: str = Query("epa_max", description="Sort metric: epa_max, epa_mean, teams, event_code"),
    ascending: bool = Query(False),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """List all events in a season with aggregate EPA stats per event."""
    storage = get_storage(season)
    events_data = storage.load_team_events()
    events_meta = {m["event_code"]: m for m in storage.load_all_events_metadata()}

    event_map = {}
    for e in events_data:
        meta = events_meta.get(e["event_code"], {})
        if event_type is not None and e.get("event_type") != event_type:
            continue
        if region is not None and (meta.get("region_code") or "").lower() != region.lower():
            continue
        if country is not None:
            loc = meta.get("location") or {}
            if (loc.get("country") or "").lower() != country.lower():
                continue
        if state is not None:
            loc = meta.get("location") or {}
            if (loc.get("state") or "").lower() != state.lower():
                continue
        if search is not None:
            name = (meta.get("name") or "").lower()
            code = e["event_code"].lower()
            q = search.lower()
            if q not in name and q not in code:
                continue
        ec = e["event_code"]
        if ec not in event_map:
            meta = events_meta.get(ec, {})
            loc = meta.get("location")
            event_map[ec] = {
                "event_code": ec,
                "event_type": e.get("event_type"),
                "name": meta.get("name"),
                "start": meta.get("start"),
                "end": meta.get("end"),
                "location": {
                    "venue": loc.get("venue") if loc else None,
                    "city": loc.get("city") if loc else None,
                    "state": loc.get("state") if loc else None,
                    "country": loc.get("country") if loc else None,
                } if loc else None,
                "region_code": meta.get("region_code"),
                "team_count": 0,
                "epa_max": float("-inf"),
                "epa_mean_sum": 0.0,
                "epa_mean_count": 0,
            }
        em = event_map[ec]
        em["team_count"] += 1
        if e.get("epa_max") is not None:
            em["epa_max"] = max(em["epa_max"], e["epa_max"])
        if e.get("epa_mean") is not None:
            em["epa_mean_sum"] += e["epa_mean"]
            em["epa_mean_count"] += 1

    results = []
    for ec, info in event_map.items():
        results.append({
            "event_code": ec,
            "event_type": info["event_type"],
            "name": info["name"],
            "start": info["start"],
            "end": info["end"],
            "location": info["location"],
            "region_code": info["region_code"],
            "team_count": info["team_count"],
            "epa_max": info["epa_max"] if info["epa_max"] != float("-inf") else None,
            "epa_mean": info["epa_mean_sum"] / info["epa_mean_count"] if info["epa_mean_count"] > 0 else None,
        })

    return sort_and_page(results, {
        "epa_max": lambda x: x["epa_max"] or 0,
        "epa_mean": lambda x: x["epa_mean"] or 0,
        "teams": lambda x: x["team_count"],
        "event_code": lambda x: x["event_code"],
    }, metric, ascending, offset, limit, default_metric="epa_max")


@router.get("/v1/event/{event_code}", response_model=EventDetail)
def get_event(event_code: str, season: str = Query(CURR_YEAR)):
    """Get all teams and their EPA stats for a specific event."""
    storage = get_storage(season)
    all_events = storage.load_team_events()
    event_teams = [e for e in all_events if e["event_code"] == event_code]

    if not event_teams:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found in season {season}")

    teams = []
    for e in event_teams:
        teams.append({
            "team": e["team"],
            "epa_start": e.get("epa_start"),
            "epa_max": e.get("epa_max"),
            "epa_mean": e.get("epa_mean"),
            "epa_pre_elim": e.get("epa_pre_elim"),
            "count": e.get("count"),
            "norm_epa": e.get("norm_epa"),
        })
    teams.sort(key=lambda x: x["epa_start"] or 0, reverse=True)

    return {
        "event_code": event_code,
        "event_type": event_teams[0].get("event_type"),
        "season": season,
        "team_count": len(teams),
        "teams": teams,
    }


@router.get("/v1/event/{event_code}/matches", response_model=PaginatedResponse)
def get_event_matches(
    event_code: str,
    season: str = Query(CURR_YEAR),
    elim: Optional[bool] = Query(None),
    metric: str = Query("match_id", description="Sort metric: match_id"),
    ascending: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get all matches for an event with per-team EPA deltas."""
    storage = get_storage(season)
    all_matches = storage.load_event_matches(event_code)

    if not all_matches:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found in season {season}")

    match_map = {}
    for m in all_matches:
        key = (m["event_code"], m["match_id"])
        if key not in match_map:
            match_map[key] = {
                "event_code": m["event_code"],
                "match_id": m["match_id"],
                "is_elim": bool(m["is_elim"]),
                "teams": [],
            }
        match_map[key]["teams"].append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
        })

    results = list(match_map.values())
    if elim is not None:
        results = [r for r in results if r["is_elim"] == elim]

    return sort_and_page(results, {
        "match_id": lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"],
    }, metric, ascending, offset, limit, default_metric="match_id")


@router.get("/v1/event/{event_code}/predictions", response_model=EventPredictionsResponse)
def get_event_predictions(
    event_code: str,
    season: str = Query(CURR_YEAR),
):
    """Get match-by-match predictions for an event, with alliances and win probabilities."""
    storage = get_storage(season)
    all_matches = storage.load_event_matches(event_code)

    if not all_matches:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found in season {season}")

    match_groups: dict = {}
    for m in all_matches:
        key = m["match_id"]
        if key not in match_groups:
            match_groups[key] = {
                "match_id": key,
                "is_elim": bool(m["is_elim"]),
                "teams": [],
            }
        match_groups[key]["teams"].append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
        })

    results = []
    for mid, match in match_groups.items():
        wp_groups: dict = {}
        for t in match["teams"]:
            wp = round(t.get("win_prob") or 0.5, 6)
            wp_groups.setdefault(wp, []).append(t["team"])

        if len(wp_groups) >= 2:
            sorted_wps = sorted(wp_groups.keys(), reverse=True)
            red = wp_groups[sorted_wps[0]]
            blue = wp_groups[sorted_wps[1]]
            rwp = float(sorted_wps[0])
        else:
            half = len(match["teams"]) // 2
            red = [t["team"] for t in match["teams"][:half]]
            blue = [t["team"] for t in match["teams"][half:]]
            rwp = 0.5

        red_sum = sum(t.get("epa_pre") or 0 for t in match["teams"] if t["team"] in red)
        blue_sum = sum(t.get("epa_pre") or 0 for t in match["teams"] if t["team"] in blue)

        results.append({
            "match_id": mid,
            "is_elim": match["is_elim"],
            "red_teams": red,
            "blue_teams": blue,
            "red_win_prob": round(rwp, 4),
            "blue_win_prob": round(1 - rwp, 4),
            "red_epa_total": round(red_sum, 2) if red_sum else None,
            "blue_epa_total": round(blue_sum, 2) if blue_sum else None,
        })

    results.sort(key=lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"])

    return {
        "event_code": event_code,
        "season": season,
        "match_count": len(results),
        "predictions": results,
    }

from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
import requests

from backend.src.core.constants import CURR_YEAR
from backend.src.api.deps import get_storage

router = APIRouter(tags=["FTCScout"])

FTCSCOUT_REST_URL = "https://api.ftcscout.org"


@router.get("/v1/events/info")
def list_events_info(
    season: str = Query(CURR_YEAR),
    event_type: Optional[str] = Query(None),
):
    """List all events with FTC Scout metadata and ScoutKick EPA data."""
    storage = get_storage(season)
    meta_events = storage.load_all_events_metadata()
    meta_map = {e["event_code"]: e for e in meta_events}

    all_events = storage.load_team_events()
    event_map = {}
    for e in all_events:
        if event_type is not None and e.get("event_type") != event_type:
            continue
        ec = e["event_code"]
        if ec not in event_map:
            event_map[ec] = {
                "event_code": ec,
                "event_type": e.get("event_type"),
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

    all_codes = set(list(meta_map.keys()) + list(event_map.keys()))
    results = []
    for code in all_codes:
        meta = meta_map.get(code, {})
        epa = event_map.get(code, {})
        results.append({
            "event_code": code,
            "name": meta.get("name"),
            "event_type": meta.get("event_type") or epa.get("event_type"),
            "start": meta.get("start"),
            "end": meta.get("end"),
            "location": meta.get("location"),
            "regionCode": meta.get("region_code"),
            "team_count": epa.get("team_count", 0),
            "epa_max": epa.get("epa_max") if epa.get("epa_max") != float("-inf") else None,
            "epa_mean": epa.get("epa_mean_sum", 0) / epa.get("epa_mean_count", 1) if epa.get("epa_mean_count", 0) > 0 else None,
        })

    results.sort(key=lambda x: x["start"] or "", reverse=True)
    return {"value": results, "count": len(results)}


@router.get("/v1/event/{event_code}/info")
def get_event_info(
    event_code: str,
    season: str = Query(CURR_YEAR),
):
    """Get extended event metadata (name, dates, location) from local cache, merged with EPA data."""
    storage = get_storage(season)
    meta = storage.load_event_metadata(event_code)

    all_events = storage.load_team_events()
    event_teams = [e for e in all_events if e["event_code"] == event_code]

    epa_max = None
    epa_mean_sum = 0.0
    epa_mean_count = 0
    for e in event_teams:
        if e.get("epa_max") is not None:
            epa_max = max(epa_max or 0, e["epa_max"])
        if e.get("epa_mean") is not None:
            epa_mean_sum += e["epa_mean"]
            epa_mean_count += 1

    result = {
        "event_code": event_code,
        "season": season,
        "name": meta.get("name") if meta else None,
        "event_type": meta.get("event_type") if meta else (event_teams[0].get("event_type") if event_teams else None),
        "start": meta.get("start") if meta else None,
        "end": meta.get("end") if meta else None,
        "location": meta.get("location") if meta else None,
        "regionCode": meta.get("region_code") if meta else None,
        "leagueCode": meta.get("league_code") if meta else None,
        "team_count": len(event_teams),
        "epa_max": epa_max,
        "epa_mean": epa_mean_sum / epa_mean_count if epa_mean_count > 0 else None,
    }

    if meta is None and not event_teams:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found in season {season}")

    return result


@router.get("/v1/team/{team}/info")
def get_team_info(team: int):
    """Get team metadata (name, location, website) from FTCScout REST API."""
    try:
        resp = requests.get(f"{FTCSCOUT_REST_URL}/rest/v1/teams/{team}", timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail=f"Team {team} not found")
        data = resp.json()
        return {
            "team": data.get("number"),
            "name": data.get("name"),
            "school_name": data.get("schoolName"),
            "sponsors": data.get("sponsors", []),
            "country": data.get("country"),
            "state": data.get("state"),
            "city": data.get("city"),
            "rookie_year": data.get("rookieYear"),
            "website": data.get("website"),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch team info from FTCScout")

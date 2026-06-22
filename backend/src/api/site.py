from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Query, HTTPException

from backend.src.api.deps import get_storage
from backend.src.api.schemas import (
    SiteTeamPage, SiteEventPage, SiteMatchPage,
    SiteTeamLight, SiteEventLight, SeasonMeta,
    TeamInfo, TeamSeasonSummary, EventMatch, EventMatchTeam,
    UpcomingMatch,
)
from backend.src.core.constants import CURR_YEAR

router = APIRouter(tags=["Site"])


def _load_season_meta(storage) -> Optional[dict]:
    meta = storage.load_season_meta()
    if meta is None:
        return None
    result = dict(meta)
    if result.get("component_means") is not None:
        result["component_means"] = result["component_means"].tolist()
    return result


@router.get("/v1/site/teams/all", response_model=List[SiteTeamLight])
def site_teams_all():
    """Lightweight list of all teams with name (for search autocomplete)."""
    storage = get_storage(CURR_YEAR)
    infos = storage.load_all_teams_info()
    return [
        {"team": t, "name": info.get("name")}
        for t, info in sorted(infos.items())
    ]


@router.get("/v1/site/events/all", response_model=List[SiteEventLight])
def site_events_all(season: str = Query(CURR_YEAR)):
    """Lightweight list of all events with name and dates (for search + filters)."""
    storage = get_storage(season)
    metas = storage.load_all_events_metadata()
    return [
        {
            "event_code": m["event_code"],
            "name": m.get("name"),
            "start": m.get("start"),
            "end": m.get("end"),
        }
        for m in metas
    ]


@router.get("/v1/site/team/{team}", response_model=SiteTeamPage)
def site_team_page(
    team: int,
    season: str = Query(CURR_YEAR),
):
    """Bundled team page: metadata + EPA + ranks + match history + season meta."""
    storage = get_storage(season)

    params = storage.load_team(team)
    if params is None:
        raise HTTPException(status_code=404, detail=f"Team {team} not found in season {season}")

    info = storage.load_team_info(team) or {}
    matches = storage.load_team_matches(team)
    season_meta = _load_season_meta(storage)

    all_events = storage.load_all_events_metadata()
    event_names: Dict[str, str] = {
        e["event_code"]: e.get("name") or e["event_code"]
        for e in all_events
    }

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

    ranks = storage.load_all_team_ranks().get(team, {})

    return {
        "team_info": {
            "team": team,
            "name": info.get("name"),
            "school_name": info.get("school_name"),
            "city": info.get("city"),
            "state": info.get("state"),
            "country": info.get("country"),
            "rookie_year": info.get("rookie_year"),
        },
        "season": {
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
            "rank": ranks.get("rank"),
            "country_rank": ranks.get("country_rank"),
            "state_rank": ranks.get("state_rank"),
            "district_rank": ranks.get("district_rank"),
            "country_team_count": ranks.get("country_team_count"),
            "state_team_count": ranks.get("state_team_count"),
            "district_team_count": ranks.get("district_team_count"),
        },
        "matches": team_matches,
        "season_meta": season_meta or {},
        "event_names": event_names,
    }


@router.get("/v1/site/event/{event_code}", response_model=SiteEventPage)
def site_event_page(
    event_code: str,
    season: str = Query(CURR_YEAR),
):
    """Bundled event page: metadata + standings + qual/elim matches + season meta."""
    storage = get_storage(season)

    meta = storage.load_event_metadata(event_code)
    all_events = storage.load_team_events()
    event_teams_data = [e for e in all_events if e["event_code"] == event_code]

    if not event_teams_data and meta is None:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found in season {season}")

    all_matches = storage.load_event_matches(event_code)
    ranks = storage.load_all_team_ranks()
    teams_info = storage.load_all_teams_info()
    season_meta = _load_season_meta(storage)

    match_map: Dict[str, dict] = {}
    for m in all_matches:
        key = m["match_id"]
        if key not in match_map:
            match_map[key] = {
                "event_code": event_code,
                "match_id": key,
                "is_elim": bool(m["is_elim"]),
                "teams": [],
            }
        match_map[key]["teams"].append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
        })

    qual_matches = [v for v in match_map.values() if not v["is_elim"]]
    elim_matches = [v for v in match_map.values() if v["is_elim"]]
    qual_matches.sort(key=lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"])
    elim_matches.sort(key=lambda x: int(x["match_id"]) if x["match_id"].isdigit() else x["match_id"])

    standings = []
    for e in event_teams_data:
        t = e["team"]
        tr = ranks.get(t, {})
        info = teams_info.get(t, {})
        standings.append({
            "team": t,
            "name": info.get("name"),
            "norm_epa": tr.get("norm_epa") or e.get("norm_epa"),
            "rank": tr.get("rank"),
            "epa_start": e.get("epa_start"),
            "epa_max": e.get("epa_max"),
            "epa_mean": e.get("epa_mean"),
            "epa_pre_elim": e.get("epa_pre_elim"),
            "count": e.get("count"),
        })
    standings.sort(key=lambda x: x["epa_start"] or 0, reverse=True)

    loc = meta.get("location") if meta else None
    return {
        "event_code": event_code,
        "name": meta.get("name") if meta else None,
        "season": season,
        "event_type": meta.get("event_type") if meta else (event_teams_data[0].get("event_type") if event_teams_data else None),
        "start": meta.get("start") if meta else None,
        "end": meta.get("end") if meta else None,
        "location": loc,
        "standings": standings,
        "qual_matches": qual_matches,
        "elim_matches": elim_matches,
        "season_meta": season_meta or {},
    }


@router.get("/v1/site/upcoming_matches")
def site_upcoming_matches(season: str = Query(CURR_YEAR)):
    """Return the most recently processed matches (live upcoming schedule not yet available)."""
    storage = get_storage(season)
    all_matches = storage.load_all_matches()

    all_matches.sort(key=lambda m: m.get("processed_at", ""), reverse=True)
    recent = all_matches[:50]

    event_names = {e["event_code"]: e.get("name") for e in storage.load_all_events_metadata()}

    match_groups: dict = {}
    for m in recent:
        key = (m["event_code"], m["match_id"])
        if key not in match_groups:
            match_groups[key] = {
                "event_code": m["event_code"],
                "match_id": m["match_id"],
                "is_elim": bool(m["is_elim"]),
                "teams": [],
                "event_name": event_names.get(m["event_code"]),
            }
        match_groups[key]["teams"].append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
        })

    return {
        "season": season,
        "matches": list(match_groups.values()),
        "count": len(match_groups),
    }


@router.get("/v1/site/match/{event_code}/{match_id}", response_model=SiteMatchPage)
def site_match_page(
    event_code: str,
    match_id: str,
    season: str = Query(CURR_YEAR),
):
    """Bundled match page: per-team EPA + event name + season meta."""
    storage = get_storage(season)

    all_matches = storage.load_event_matches(event_code)
    if not all_matches:
        raise HTTPException(status_code=404, detail=f"Event {event_code} not found")

    match_rows = [m for m in all_matches if m["match_id"] == match_id]
    if not match_rows:
        raise HTTPException(status_code=404, detail=f"Match {match_id} at {event_code} not found")

    teams = []
    for m in match_rows:
        teams.append({
            "team": m["team"],
            "epa_pre": m["epa_pre"],
            "epa_post": m["epa_post"],
            "win_prob": m["win_prob"],
        })

    meta = storage.load_event_metadata(event_code)
    season_meta = _load_season_meta(storage)
    is_elim = any(bool(m["is_elim"]) for m in match_rows)

    # Split teams into alliances using win_prob grouping
    red_teams: List[int] = []
    blue_teams: List[int] = []
    wp_groups: Dict[float, List[int]] = {}
    for t in teams:
        wp = round(t.get("win_prob") or 0.5, 6)
        wp_groups.setdefault(wp, []).append(t["team"])
    if len(wp_groups) == 2:
        sorted_wps = sorted(wp_groups.keys(), reverse=True)
        red_teams = wp_groups[sorted_wps[0]]
        blue_teams = wp_groups[sorted_wps[1]]
    elif len(wp_groups) == 1:
        red_teams = wp_groups[next(iter(wp_groups))]
        blue_teams = []
    else:
        red_teams = [t["team"] for t in teams[:len(teams)//2]]
        blue_teams = [t["team"] for t in teams[len(teams)//2:]]

    red_total = None
    blue_total = None
    red_win_prob = None
    red_pre_values = [t["epa_pre"] for t in teams if t["team"] in red_teams and t["epa_pre"] is not None]
    blue_pre_values = [t["epa_pre"] for t in teams if t["team"] in blue_teams and t["epa_pre"] is not None]
    if red_pre_values and blue_pre_values:
        red_total = sum(red_pre_values)
        blue_total = sum(blue_pre_values)
        diff = (red_total - blue_total) / (season_meta.get("score_sd") or 20) if season_meta else 0
        red_win_prob = round(1 / (1 + 10 ** (-5 / 8 * diff)), 4)

    return {
        "event_code": event_code,
        "event_name": meta.get("name") if meta else None,
        "match_id": match_id,
        "season": season,
        "is_elim": is_elim,
        "teams": teams,
        "red_teams": red_teams,
        "blue_teams": blue_teams,
        "red_total": round(red_total, 2) if red_total is not None else None,
        "blue_total": round(blue_total, 2) if blue_total is not None else None,
        "red_win_prob": red_win_prob,
        "season_meta": season_meta or {},
    }

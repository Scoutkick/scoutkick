from typing import Any, Dict, List, Optional

from backend.src.data.ftcscout_api import get_ftcscout
from backend.src.data.cleaner import BaseCleaner


def _month_ranges(season: str) -> List[tuple]:
    """Inclusive month ranges. End dates extended by 1 day for GraphQL's exclusive upper bound."""
    s = int(season)
    return [
        (f"{s}-09-01", f"{s}-10-01"),
        (f"{s}-10-01", f"{s}-11-01"),
        (f"{s}-11-01", f"{s}-12-01"),
        (f"{s}-12-01", f"{s + 1}-01-01"),
        (f"{s + 1}-01-01", f"{s + 1}-02-01"),
        (f"{s + 1}-02-01", f"{s + 1}-03-01"),
        (f"{s + 1}-03-01", f"{s + 1}-04-01"),
        (f"{s + 1}-04-01", f"{s + 1}-05-01"),
        (f"{s + 1}-05-01", f"{s + 1}-06-01"),
        (f"{s + 1}-06-01", f"{s + 1}-07-01"),
        (f"{s + 1}-07-01", f"{s + 1}-08-01"),
        (f"{s + 1}-08-01", f"{s + 1}-09-01"),
    ]


def _paginated_query(season: str, fields: str, start: str, end: str) -> str:
    return f"""
    query {{
      eventsSearch(season: {season}, start: "{start}", end: "{end}", limit: 500) {{
        {fields}
      }}
    }}
    """


def _split_alliance_teams(match: dict) -> tuple:
    red, blue = [], []
    for t in match.get("teams") or []:
        if not t:
            continue
        tn = t.get("teamNumber")
        alliance = t.get("alliance")
        if alliance == "Red":
            red.append(tn)
        elif alliance == "Blue":
            blue.append(tn)
    return red, blue


def _extract_alliance_scores(match: dict) -> tuple:
    scores_obj = match.get("scores") or {}
    red_scores = (scores_obj.get("red") or {}).copy()
    blue_scores = (scores_obj.get("blue") or {}).copy()

    # Remote events (2020/2021) use flat alliance-based scores
    if (not red_scores or not blue_scores) and "alliance" in scores_obj:
        raw = dict(scores_obj)
        alliance_name = raw.pop("alliance", None)
        if alliance_name == "Red":
            red_scores = raw
        elif alliance_name == "Blue":
            blue_scores = raw

    return red_scores, blue_scores


def parse_matches(data: dict) -> List[Dict[str, Any]]:
    if not data or "eventsSearch" not in data:
        return []

    all_matches = []
    for event in data["eventsSearch"]:
        event_code = event["code"]
        event_type = event.get("type")
        for m in event.get("matches") or []:
            if not m.get("hasBeenPlayed"):
                continue

            red_teams, blue_teams = _split_alliance_teams(m)
            red_scores, blue_scores = _extract_alliance_scores(m)

            # Skip solo/remote matches where only one alliance has data
            if not red_teams or not blue_teams or not red_scores or not blue_scores:
                continue

            all_matches.append({
                "match_id": m["id"],
                "event": event_code,
                "event_type": event_type,
                "tournament_level": m.get("tournamentLevel"),
                "red_teams": red_teams,
                "blue_teams": blue_teams,
                "red_scores": red_scores,
                "blue_scores": blue_scores,
            })

    return all_matches


def _fetch_events_for_range(season: str, fields: str, start: str, end: str, cache: bool) -> List[Dict]:
    q = _paginated_query(season, fields, start, end)
    data = get_ftcscout(q, variables=None, cache=cache)
    if not data:
        return []
    return data.get("eventsSearch") or []


def get_matches(cleaner: BaseCleaner, cache: bool = True) -> List[Dict[str, Any]]:
    fragment = cleaner.get_graphql_fragment()
    fields = f"""
        code
        type
        matches {{
          id
          hasBeenPlayed
          tournamentLevel
          teams {{
            teamNumber
            alliance
            station
          }}
          scores {{
            {fragment}
          }}
        }}
    """
    combined = []
    seen: set = set()
    for start, end in _month_ranges(cleaner.SEASON_ID):
        events = _fetch_events_for_range(cleaner.SEASON_ID, fields, start, end, cache)
        for e in events:
            ec = e["code"]
            if ec not in seen:
                seen.add(ec)
                combined.append(e)
    return parse_matches({"eventsSearch": combined})


def get_events_metadata(season: str, cache: bool = True) -> List[Dict[str, Any]]:
    q = f"""
    query {{
      eventsSearch(season: {season}, limit: 2000) {{
        code
        name
        type
        start
        end
        location {{
          venue
          city
          state
          country
        }}
        regionCode
        leagueCode
      }}
    }}
    """
    data = get_ftcscout(q, variables=None, cache=cache)
    if not data:
        return []
    raw_events = data.get("eventsSearch") or []
    results = []
    for e in raw_events:
        loc = e.get("location") or {}
        results.append({
            "event_code": e["code"],
            "name": e.get("name"),
            "event_type": e.get("type"),
            "start": e.get("start"),
            "end": e.get("end"),
            "location": {
                "venue": loc.get("venue"),
                "city": loc.get("city"),
                "state": loc.get("state"),
                "country": loc.get("country"),
            } if loc else None,
            "region_code": e.get("regionCode"),
            "league_code": e.get("leagueCode"),
        })
    return results

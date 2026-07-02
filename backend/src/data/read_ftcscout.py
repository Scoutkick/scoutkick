from typing import Any, Dict, List

from backend.src.data.ftcscout_api import get_ftcscout
from backend.src.data.cleaner import BaseCleaner


def _month_ranges(season: str) -> List[tuple]:
    """Overlapping month ranges with 7-day overlap so multi-day events
    crossing month boundaries (e.g. FTC Championship Apr 29 - May 2)
    are caught by at least one range. Overlaps are deduplicated by
    event code in get_matches()."""
    s = int(season)
    OVERLAP = 7
    return [
        (f"{s}-09-01", f"{s}-10-{1+OVERLAP:02d}"),
        (f"{s}-10-01", f"{s}-11-{1+OVERLAP:02d}"),
        (f"{s}-11-01", f"{s}-12-{1+OVERLAP:02d}"),
        (f"{s}-12-01", f"{s + 1}-01-{1+OVERLAP:02d}"),
        (f"{s + 1}-01-01", f"{s + 1}-02-{1+OVERLAP:02d}"),
        (f"{s + 1}-02-01", f"{s + 1}-03-{1+OVERLAP:02d}"),
        (f"{s + 1}-03-01", f"{s + 1}-04-{1+OVERLAP:02d}"),
        (f"{s + 1}-04-01", f"{s + 1}-05-{1+OVERLAP:02d}"),
        (f"{s + 1}-05-01", f"{s + 1}-06-{1+OVERLAP:02d}"),
        (f"{s + 1}-06-01", f"{s + 1}-07-{1+OVERLAP:02d}"),
        (f"{s + 1}-07-01", f"{s + 1}-08-{1+OVERLAP:02d}"),
        (f"{s + 1}-08-01", f"{s + 1}-09-{1+OVERLAP:02d}"),
    ]


def _paginated_query(season: str, fields: str, start: str, end: str) -> str:
    return f"""
    query {{
      eventsSearch(season: {season}, start: "{start}", end: "{end}", limit: 500) {{
        {fields}
      }}
    }}
    """


def _station_sort_key(t: dict) -> int:
    station = t.get("station", "")
    return 0 if station == "One" else 1


def _split_alliance_teams(match: dict) -> tuple:
    red, blue = [], []
    for t in match.get("teams") or []:
        if not t:
            continue
        tn = t.get("teamNumber")
        alliance = t.get("alliance")
        if alliance == "Red":
            red.append(t)
        elif alliance == "Blue":
            blue.append(t)
    red.sort(key=_station_sort_key)
    blue.sort(key=_station_sort_key)
    return [t.get("teamNumber") for t in red], [t.get("teamNumber") for t in blue]


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


def parse_matches(data: dict) -> tuple:
    """Returns (matches_list, team_metadata_dict)."""
    if not data or "eventsSearch" not in data:
        return [], {}

    all_matches = []
    all_teams: Dict[int, Dict] = {}
    for event in data["eventsSearch"]:
        event_code = event["code"]
        event_type = event.get("type")
        for m in event.get("matches") or []:
            if not m.get("hasBeenPlayed"):
                continue

            # Extract team metadata from the nested team object
            for t in m.get("teams") or []:
                if not t:
                    continue
                tn = t.get("teamNumber")
                if tn and tn not in all_teams:
                    team_obj = t.get("team") or {}
                    loc = team_obj.get("location") or {}
                    all_teams[tn] = {
                        "name": team_obj.get("name"),
                        "school_name": team_obj.get("schoolName"),
                        "city": loc.get("city"),
                        "state": loc.get("state"),
                        "country": loc.get("country"),
                    }

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
                "start_date": m.get("scheduledStart"),
                "red_teams": red_teams,
                "blue_teams": blue_teams,
                "red_scores": red_scores,
                "blue_scores": blue_scores,
            })

    return all_matches, all_teams


def _fetch_events_for_range(season: str, fields: str, start: str, end: str, cache: bool) -> List[Dict]:
    q = _paginated_query(season, fields, start, end)
    data = get_ftcscout(q, variables=None, cache=cache)
    if not data:
        return []
    return data.get("eventsSearch") or []


def get_matches(cleaner: BaseCleaner, cache: bool = True) -> tuple:
    fragment = cleaner.get_graphql_fragment()
    fields = f"""
        code
        type
        matches {{
          id
          hasBeenPlayed
          tournamentLevel
          scheduledStart
          teams {{
            teamNumber
            alliance
            station
            team {{
              name
              schoolName
              location {{
                city
                state
                country
              }}
            }}
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

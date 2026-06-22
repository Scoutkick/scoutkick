import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

import numpy as np
import requests

from backend.src.core.config import get_season_config
from backend.src.data.read_ftcscout import get_matches, get_events_metadata
from backend.src.data.cleaner import BaseCleaner
from backend.src.services.epa_service import EPAEngine
from backend.src.services.calibrate import calibrate_score_sd, calibrate_component_means
from backend.src.services.init_epa import get_init_epa, compute_norm_epa
from backend.src.storage import create_storage

FTCSCOUT_REST_URL = "https://api.ftcscout.org"

logger = logging.getLogger(__name__)


class EPAPipeline:
    def __init__(self, season_id: str, db_path: str = "backend/cache/epa_data.db",
                 calibrate: bool = True):
        self.season_id = season_id
        self.config = get_season_config(season_id)
        self.cleaner = BaseCleaner.get_cleaner(season_id)
        self.engine = EPAEngine(config=self.config)
        self.storage = create_storage(season_id, db_path)
        self.do_calibrate = calibrate

    def _unique_teams(self, matches: List[Dict]) -> Set[int]:
        teams: Set[int] = set()
        for m in matches:
            teams.update(m.get("red_teams", []))
            teams.update(m.get("blue_teams", []))
        return teams

    def _init_teams(self, teams: Set[int], component_means: np.ndarray,
                    score_sd: float, score_mean: float):
        prior_seasons = self.storage.get_prior_seasons(self.season_id, look_back=4)
        prior_data: Dict[int, Dict[int, Optional[float]]] = {}
        for season in prior_seasons:
            season_teams = self.storage.load_season_teams(season)
            for team, params in season_teams.items():
                prior_data.setdefault(team, {})[int(season)] = params.get("norm_epa")

        initialized = 0
        rookies = 0
        for team in sorted(teams):
            if team in self.engine.epas:
                continue

            past: List[Optional[float]] = []
            for s in prior_seasons:
                s_int = int(s)
                if team in prior_data and s_int in prior_data[team]:
                    past.append(prior_data[team][s_int])
                else:
                    past.append(None)

            prior_1 = past[0] if len(past) > 0 else None
            prior_2 = past[1] if len(past) > 1 else None

            sn = get_init_epa(
                self.config, component_means, score_sd, score_mean,
                prior_norm_epa_1=prior_1, prior_norm_epa_2=prior_2,
            )
            self.engine.set_team_state(team, sn.mean, sn.var, sn.skew, sn.n, 0)
            if prior_1 is not None:
                initialized += 1
            else:
                rookies += 1

        logger.info("Initialized %d returning + %d rookie teams from %d total.",
                    initialized, rookies, len(teams))

    def _load_existing_teams(self):
        existing = self.storage.load_all_teams()
        if existing:
            logger.info("Loaded %d teams from storage (resuming).", len(existing))
            for team, params in existing.items():
                self.engine.set_team_state(
                    team, params["mean"], params["var"],
                    params["skew"], params["n"], params["count"],
                )
        return existing

    def _fetch_matches(self) -> List[Dict]:
        logger.info("Fetching matches from FTCscout...")
        matches = get_matches(self.cleaner)
        logger.info("Found %d matches.", len(matches))
        return matches

    def _filter_new_matches(self, matches: List[Dict]) -> List[Dict]:
        processed_keys = self.storage.get_processed_match_keys()
        new_matches = [m for m in matches if (m["event"], str(m["match_id"])) not in processed_keys]
        if len(new_matches) < len(matches):
            logger.info("Skipping %d already-processed matches (%d new).",
                        len(matches) - len(new_matches), len(new_matches))
        return new_matches

    def _calibrate(self, matches: List[Dict]) -> tuple:
        if not self.do_calibrate:
            component_means = np.zeros(len(self.config.dimensions))
            component_means[0] = self.config.default_mean_total * 2
            return component_means, component_means[0], self.engine.score_sd

        score_sd = calibrate_score_sd(self.cleaner, self.season_id, matches=matches)
        self.engine.score_sd = score_sd
        component_means = calibrate_component_means(self.cleaner, self.season_id, matches=matches)
        score_mean = float(component_means[0]) if len(component_means) > 0 else 0.0
        logger.info("Calibrated: score_sd=%.2f, score_mean=%.2f", score_sd, score_mean)
        return component_means, score_mean, score_sd

    def _group_and_sort_matches(self, matches: List[Dict]) -> Dict[str, List[Dict]]:
        events: Dict[str, List[Dict]] = defaultdict(list)
        for m in matches:
            events[m["event"]].append(m)
        for ec in events:
            events[ec].sort(key=lambda x: str(x["match_id"]))
        return events

    def _init_event_trackers(self, events: Dict[str, List[Dict]]):
        trackers: Dict[int, Dict[str, Dict]] = defaultdict(dict)
        for event_code, event_matches in events.items():
            for m in event_matches:
                for team in m["red_teams"] + m["blue_teams"]:
                    if event_code not in trackers[team]:
                        current_epa = self.engine.get_team(team).mean[0]
                        trackers[team][event_code] = {
                            "epa_start": current_epa,
                            "epa_max": current_epa,
                            "epa_sum": 0.0,
                            "match_count": 0,
                        }
        return trackers

    def _process_single_match(self, m: Dict, trackers: Dict) -> List[Dict]:
        match_id = str(m["match_id"])
        red_teams = m["red_teams"]
        blue_teams = m["blue_teams"]

        pre_epas: Dict[int, float] = {}
        pre_means: Dict[int, str] = {}
        for team in red_teams + blue_teams:
            sn = self.engine.get_team(team)
            pre_epas[team] = float(sn.mean[0])
            pre_means[team] = json.dumps(sn.mean.tolist())

        red_raw = self.cleaner.aggregate(m["red_scores"])
        blue_raw = self.cleaner.aggregate(m["blue_scores"])
        red_actual = self.cleaner.clean(red_raw)
        blue_actual = self.cleaner.clean(blue_raw)
        red_weights = self.cleaner.get_attribution_weights(m["red_scores"], red_teams)
        blue_weights = self.cleaner.get_attribution_weights(m["blue_scores"], blue_teams)
        win_prob, red_pred, blue_pred = self.engine.predict_match(red_teams, blue_teams)
        attributions = self.engine.attribute_match(
            red_teams, blue_teams,
            red_actual, blue_actual,
            red_pred, blue_pred,
            red_weights=red_weights,
            blue_weights=blue_weights,
        )

        tl = m.get("tournament_level")
        is_elim = tl in ("Semis", "Finals")

        for team_num, attrib in attributions.items():
            self.engine.update_team(team_num, attrib, is_elim=is_elim)

        records = []
        for team in red_teams + blue_teams:
            epa_post = float(self.engine.get_team(team).mean[0])
            records.append({
                "team": team,
                "event_code": m["event"],
                "match_id": match_id,
                "epa_pre": pre_epas[team],
                "epa_post": epa_post,
                "mean_json_pre": pre_means[team],
                "win_prob": win_prob if team in red_teams else 1 - win_prob,
                "is_elim": is_elim,
            })
            trk = trackers[team][m["event"]]
            trk["epa_max"] = max(trk["epa_max"], epa_post)
            trk["epa_sum"] += (pre_epas[team] + epa_post) / 2
            trk["match_count"] += 1

        return records

    def _build_event_records(self, events: Dict[str, List[Dict]], trackers: Dict) -> List[Dict]:
        records = []
        for event_code, event_matches in events.items():
            event_type = event_matches[0].get("event_type") if event_matches else None
            for team, trk in trackers.items():
                if event_code not in trk:
                    continue
                t = trk[event_code]
                sn = self.engine.get_team(team)
                epa_mean = t["epa_sum"] / t["match_count"] if t["match_count"] > 0 else None
                records.append({
                    "team": team,
                    "event_code": event_code,
                    "event_type": event_type,
                    "epa_start": t["epa_start"],
                    "epa_max": t["epa_max"],
                    "epa_mean": epa_mean,
                    "mean": sn.mean,
                    "var": sn.var,
                    "skew": sn.skew,
                    "n": sn.n,
                    "count": self.engine.counts.get(team, 0),
                })
        return records

    def _cache_team_metadata(self, teams: Set[int]):
        cached = self.storage.load_all_teams_info()
        missing = [t for t in teams if t not in cached]
        if not missing:
            logger.info("All %d teams already have cached metadata.", len(teams))
            return

        fetched = 0
        for team in missing:
            try:
                resp = requests.get(
                    f"{FTCSCOUT_REST_URL}/rest/v1/teams/{team}", timeout=10
                )
                if resp.status_code != 200:
                    logger.warning("  Team %d: FTCScout returned %d", team, resp.status_code)
                    continue
                data = resp.json()
                self.storage.save_team_info({
                    "team": data.get("number", team),
                    "name": data.get("name"),
                    "school_name": data.get("schoolName"),
                    "city": data.get("city"),
                    "state": data.get("state"),
                    "country": data.get("country"),
                    "rookie_year": data.get("rookieYear"),
                })
                fetched += 1
            except Exception as e:
                logger.warning("  Failed to fetch info for team %d: %s", team, e)
        logger.info("Cached metadata for %d/%d new teams.", fetched, len(missing))

    def _compute_and_save_ranks(self, norm_epas: Dict[int, float]):
        teams_info = self.storage.load_all_teams_info()

        team_entries = []
        for team, norm_epa in norm_epas.items():
            info = teams_info.get(team, {})
            team_entries.append({
                "team": team,
                "norm_epa": norm_epa or 0,
                "country": (info.get("country") or "").strip(),
                "state": (info.get("state") or "").strip(),
            })
        team_entries.sort(key=lambda x: x["norm_epa"], reverse=True)

        total_count = len(team_entries)

        country_buckets: Dict[str, list] = defaultdict(list)
        state_buckets: Dict[str, list] = defaultdict(list)
        for entry in team_entries:
            if entry["country"]:
                country_buckets[entry["country"]].append(entry)
            if entry["state"]:
                state_buckets[entry["state"]].append(entry)

        # Sort each bucket by norm_epa desc and assign rank
        for bucket in country_buckets.values():
            bucket.sort(key=lambda x: x["norm_epa"], reverse=True)
        for bucket in state_buckets.values():
            bucket.sort(key=lambda x: x["norm_epa"], reverse=True)

        rank_records = []
        for rank, entry in enumerate(team_entries, 1):
            country = entry["country"]
            state = entry["state"]

            c_rank = None
            c_count = None
            if country and country in country_buckets:
                c_list = country_buckets[country]
                c_rank = next(i for i, e in enumerate(c_list, 1) if e["team"] == entry["team"])
                c_count = len(c_list)

            s_rank = None
            s_count = None
            if state and state in state_buckets:
                s_list = state_buckets[state]
                s_rank = next(i for i, e in enumerate(s_list, 1) if e["team"] == entry["team"])
                s_count = len(s_list)

            rank_records.append({
                "team": entry["team"],
                "rank": rank,
                "country_rank": c_rank,
                "state_rank": s_rank,
                "district_rank": None,
                "country_team_count": c_count,
                "state_team_count": s_count,
                "district_team_count": None,
                "team_country": country or None,
                "team_state": state or None,
                "team_district": None,
            })

        self.storage.save_team_ranks_bulk(rank_records)
        logger.info("Computed and saved ranks for %d teams.", len(rank_records))

    def run(self):
        logger.info("--- Starting EPA Pipeline for %s ---", self.season_id)

        matches = self._fetch_matches()
        if not matches:
            logger.warning("No matches found. Exiting.")
            return None

        new_matches = self._filter_new_matches(matches)
        if not new_matches:
            logger.info("No new matches to process.")
            self._load_existing_teams()
            return self.engine

        matches = new_matches
        component_means, score_mean, score_sd = self._calibrate(matches)

        self._load_existing_teams()
        all_teams = self._unique_teams(matches)
        self._init_teams(all_teams, component_means, score_sd, score_mean)

        events = self._group_and_sort_matches(matches)
        trackers = self._init_event_trackers(events)

        total = sum(len(v) for v in events.values())
        done = 0
        all_match_records: List[Dict] = []

        for event_code in sorted(events.keys()):
            event_matches = events[event_code]
            event_type = event_matches[0].get("event_type") if event_matches else None
            logger.info("  Event %s (%s): %d matches", event_code, event_type, len(event_matches))

            for m in event_matches:
                records = self._process_single_match(m, trackers)
                all_match_records.extend(records)
                done += 1
                if done % 50 == 0:
                    logger.info("  Processed %d/%d matches...", done, total)

        if all_match_records:
            self.storage.save_team_matches_bulk(all_match_records)
            logger.info("Batch-saved %d match records.", len(all_match_records))

        event_records = self._build_event_records(events, trackers)
        self.storage.save_team_events_bulk(event_records)
        logger.info("Batch-saved %d event records.", len(event_records))

        events_meta = get_events_metadata(self.season_id)
        if events_meta:
            self.storage.save_events_metadata_bulk(events_meta)
            logger.info("Saved metadata for %d events.", len(events_meta))

        score_mean_used = float(component_means[0]) if len(component_means) > 0 else 0.0
        self.storage.save_season_meta(
            score_mean=score_mean_used,
            score_sd=self.engine.score_sd,
            component_means=component_means,
            num_matches=total,
            num_teams=len(self.engine.epas),
        )

        norm_epas = compute_norm_epa(self.engine.epas)
        team_records = [
            {
                "team": team,
                "mean": sn.mean,
                "var": sn.var,
                "skew": sn.skew,
                "n": sn.n,
                "count": self.engine.counts.get(team, 0),
                "norm_epa": norm_epas.get(team),
            }
            for team, sn in self.engine.epas.items()
        ]
        self.storage.save_all_teams_bulk(team_records)
        logger.info("Batch-saved %d team records with norm_epa.", len(team_records))

        self._cache_team_metadata(all_teams)
        self._compute_and_save_ranks(norm_epas)

        logger.info("--- Pipeline Complete. Trained %d teams across %d events (%d matches). ---",
                    len(self.engine.epas), len(events), total)
        return self.engine


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        pipeline = EPAPipeline("2025")
        engine = pipeline.run()
        if engine:
            sample_team = list(engine.epas.keys())[0]
            print(f"Sample Team {sample_team} Mean Total: {engine.get_team(sample_team).mean[0]:.2f}")
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)

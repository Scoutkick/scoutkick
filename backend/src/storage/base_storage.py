import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set

import numpy as np


class BaseStorage(ABC):
    PLACEHOLDER = "?"
    NOW_FUNC = "datetime('now')"

    def __init__(self, season_id: str):
        self.season_id = season_id

    def _p(self, sql: str) -> str:
        return sql

    @abstractmethod
    def _execute(self, sql: str, params: tuple = ()) -> List[dict]:
        ...

    @abstractmethod
    def _ensure_tables(self):
        ...

    def _row_to_team(self, row: dict) -> Dict:
        return {
            "mean": np.array(json.loads(row["mean_json"])),
            "var": np.array(json.loads(row["var_json"])),
            "skew": row["skew"],
            "n": row["n"],
            "count": row["count"],
            "norm_epa": row["norm_epa"],
        }

    def _row_to_event(self, row: dict) -> Dict:
        r = dict(row)
        if r["mean_json"]:
            r["mean"] = np.array(json.loads(r["mean_json"]))
        else:
            r["mean"] = None
        if r["var_json"]:
            r["var"] = np.array(json.loads(r["var_json"]))
        else:
            r["var"] = None
        r.pop("mean_json", None)
        r.pop("var_json", None)
        return r

    @staticmethod
    def get_prior_seasons(current_season: str, look_back: int = 4) -> List[str]:
        try:
            curr = int(current_season)
        except ValueError:
            return []
        return [str(curr - i) for i in range(1, look_back + 1)]

    # ── team_seasons ──

    def save_team(self, team: int, mean: np.ndarray, var: np.ndarray,
                  skew: float, n: float, count: int, norm_epa: Optional[float] = None):
        self._execute(f"""
            INSERT INTO team_seasons (team, season, mean_json, var_json,
                                      skew, n, count, norm_epa, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {self.NOW_FUNC})
            ON CONFLICT(team, season) DO UPDATE SET
                mean_json  = excluded.mean_json,
                var_json   = excluded.var_json,
                skew       = excluded.skew,
                n          = excluded.n,
                count      = excluded.count,
                norm_epa   = excluded.norm_epa,
                updated_at = {self.NOW_FUNC}
        """, (
            team, self.season_id,
            json.dumps(mean.tolist()),
            json.dumps(var.tolist()),
            skew, n, count, norm_epa,
        ))

    def load_team(self, team: int) -> Optional[Dict]:
        rows = self._execute(
            "SELECT * FROM team_seasons WHERE team = ? AND season = ?",
            (team, self.season_id),
        )
        if not rows:
            return None
        return self._row_to_team(rows[0])

    def load_all_teams(self) -> Dict[int, Dict]:
        rows = self._execute(
            "SELECT * FROM team_seasons WHERE season = ?",
            (self.season_id,),
        )
        return {r["team"]: self._row_to_team(r) for r in rows}

    def load_season_teams(self, season_id: str) -> Dict[int, Dict]:
        rows = self._execute(
            "SELECT * FROM team_seasons WHERE season = ?",
            (season_id,),
        )
        return {r["team"]: self._row_to_team(r) for r in rows}

    def load_team_cross_season(self, team: int) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM team_seasons WHERE team = ? ORDER BY season",
            (team,),
        )
        return [self._row_to_team(r) for r in rows]

    def save_all_teams(self, epas: Dict[int, "SkewNormal"], counts: Dict[int, int],
                       norm_epas: Optional[Dict[int, float]] = None):
        if norm_epas is None:
            norm_epas = {}
        for team, sn in epas.items():
            self.save_team(
                team, sn.mean, sn.var, sn.skew, sn.n,
                counts.get(team, 0), norm_epas.get(team),
            )

    def delete_season(self):
        self._execute("DELETE FROM team_seasons WHERE season = ?", (self.season_id,))
        self._execute("DELETE FROM team_events WHERE season = ?", (self.season_id,))
        self._execute("DELETE FROM team_matches WHERE season = ?", (self.season_id,))
        self._execute("DELETE FROM seasons WHERE season = ?", (self.season_id,))

    # ── team_events ──

    def save_team_event(self, team: int, event_code: str,
                        epa_start: Optional[float] = None,
                        epa_max: Optional[float] = None,
                        epa_pre_elim: Optional[float] = None,
                        epa_mean: Optional[float] = None,
                        mean: Optional[np.ndarray] = None,
                        var: Optional[np.ndarray] = None,
                        skew: Optional[float] = None,
                        n: Optional[float] = None,
                        count: Optional[int] = None,
                        norm_epa: Optional[float] = None,
                        event_type: Optional[str] = None):
        self._execute(f"""
            INSERT INTO team_events (team, season, event_code, event_type,
                epa_start, epa_max, epa_pre_elim, epa_mean,
                mean_json, var_json, skew, n, count, norm_epa, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {self.NOW_FUNC})
            ON CONFLICT(team, season, event_code) DO UPDATE SET
                event_type = COALESCE(excluded.event_type, team_events.event_type),
                epa_start  = COALESCE(excluded.epa_start, team_events.epa_start),
                epa_max    = COALESCE(excluded.epa_max, team_events.epa_max),
                epa_pre_elim = COALESCE(excluded.epa_pre_elim, team_events.epa_pre_elim),
                epa_mean   = COALESCE(excluded.epa_mean, team_events.epa_mean),
                mean_json  = COALESCE(excluded.mean_json, team_events.mean_json),
                var_json   = COALESCE(excluded.var_json, team_events.var_json),
                skew       = COALESCE(excluded.skew, team_events.skew),
                n          = COALESCE(excluded.n, team_events.n),
                count      = COALESCE(excluded.count, team_events.count),
                norm_epa   = COALESCE(excluded.norm_epa, team_events.norm_epa),
                updated_at = {self.NOW_FUNC}
        """, (
            team, self.season_id, event_code, event_type,
            epa_start, epa_max, epa_pre_elim, epa_mean,
            json.dumps(mean.tolist()) if mean is not None else None,
            json.dumps(var.tolist()) if var is not None else None,
            skew, n, count, norm_epa,
        ))

    def load_team_events(self) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM team_events WHERE season = ? ORDER BY team, event_code",
            (self.season_id,),
        )
        return [self._row_to_event(r) for r in rows]

    def load_team_event(self, team: int, event_code: str) -> Optional[Dict]:
        rows = self._execute(
            "SELECT * FROM team_events WHERE team = ? AND season = ? AND event_code = ?",
            (team, self.season_id, event_code),
        )
        if not rows:
            return None
        return self._row_to_event(rows[0])

    # ── team_matches ──

    def save_team_match(self, team: int, event_code: str, match_id: str,
                        epa_pre: Optional[float] = None,
                        epa_post: Optional[float] = None,
                        mean_json_pre: Optional[str] = None,
                        win_prob: Optional[float] = None,
                        is_elim: bool = False):
        self._execute(f"""
            INSERT INTO team_matches (team, season, event_code, match_id,
                epa_pre, epa_post, mean_json_pre, win_prob, is_elim, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {self.NOW_FUNC})
            ON CONFLICT(team, season, event_code, match_id) DO UPDATE SET
                epa_post     = excluded.epa_post,
                mean_json_pre = excluded.mean_json_pre,
                win_prob     = excluded.win_prob,
                is_elim      = excluded.is_elim,
                processed_at = {self.NOW_FUNC}
        """, (
            team, self.season_id, event_code, match_id,
            epa_pre, epa_post, mean_json_pre, win_prob, int(is_elim),
        ))

    def get_processed_match_keys(self) -> Set[tuple]:
        rows = self._execute(
            "SELECT DISTINCT event_code, match_id FROM team_matches WHERE season = ?",
            (self.season_id,),
        )
        return {(r["event_code"], r["match_id"]) for r in rows}

    def load_team_matches(self, team: int) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM team_matches WHERE team = ? AND season = ? ORDER BY processed_at",
            (team, self.season_id),
        )
        return [dict(r) for r in rows]

    # ── seasons ──

    def save_season_meta(self, score_mean: float, score_sd: float,
                         component_means: np.ndarray,
                         num_matches: int, num_teams: int):
        self._execute(f"""
            INSERT INTO seasons (season, score_mean, score_sd,
                component_means_json, num_matches, num_teams, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, {self.NOW_FUNC})
            ON CONFLICT(season) DO UPDATE SET
                score_mean           = excluded.score_mean,
                score_sd             = excluded.score_sd,
                component_means_json = excluded.component_means_json,
                num_matches          = excluded.num_matches,
                num_teams            = excluded.num_teams,
                updated_at           = {self.NOW_FUNC}
        """, (
            self.season_id,
            score_mean, score_sd,
            json.dumps(component_means.tolist()),
            num_matches, num_teams,
        ))

    def load_season_meta(self) -> Optional[Dict]:
        rows = self._execute(
            "SELECT * FROM seasons WHERE season = ?",
            (self.season_id,),
        )
        if not rows:
            return None
        r = dict(rows[0])
        if r["component_means_json"]:
            r["component_means"] = np.array(json.loads(r["component_means_json"]))
        else:
            r["component_means"] = None
        r.pop("component_means_json", None)
        return r

    def load_all_seasons_meta(self) -> List[Dict]:
        rows = self._execute("SELECT * FROM seasons ORDER BY season")
        result = []
        for row in rows:
            r = dict(row)
            if r["component_means_json"]:
                r["component_means"] = np.array(json.loads(r["component_means_json"]))
            else:
                r["component_means"] = None
            r.pop("component_means_json", None)
            result.append(r)
        return result

import json
from typing import Dict, List, Optional

import numpy as np
import psycopg2
import psycopg2.extras

from backend.src.storage.base_storage import BaseStorage


class PostgresStorage(BaseStorage):
    PLACEHOLDER = "%s"
    NOW_FUNC = "NOW()"

    def __init__(self, db_url: str, season_id: str):
        super().__init__(season_id)
        self.db_url = db_url
        self._ensure_tables()

    def _p(self, sql: str) -> str:
        return sql.replace("?", "%s").replace("datetime('now')", "NOW()")

    def _execute(self, sql: str, params: tuple = ()) -> List[dict]:
        sql = self._p(sql)
        conn = psycopg2.connect(self.db_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                if cur.description:
                    rows = cur.fetchall()
                    conn.commit()
                    return [dict(r) for r in rows]
                conn.commit()
                return []
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self):
        self._execute("""
            CREATE TABLE IF NOT EXISTS team_seasons (
                team      INTEGER NOT NULL,
                season    TEXT    NOT NULL,
                mean_json TEXT    NOT NULL,
                var_json  TEXT    NOT NULL,
                skew      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                n         DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                count     INTEGER NOT NULL DEFAULT 0,
                norm_epa  DOUBLE PRECISION DEFAULT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (team, season)
            );

            CREATE TABLE IF NOT EXISTS team_events (
                team       INTEGER NOT NULL,
                season     TEXT    NOT NULL,
                event_code TEXT    NOT NULL,
                event_type TEXT    DEFAULT NULL,
                epa_start  DOUBLE PRECISION DEFAULT NULL,
                epa_max    DOUBLE PRECISION DEFAULT NULL,
                epa_pre_elim DOUBLE PRECISION DEFAULT NULL,
                epa_mean   DOUBLE PRECISION DEFAULT NULL,
                mean_json  TEXT    DEFAULT NULL,
                var_json   TEXT    DEFAULT NULL,
                skew       DOUBLE PRECISION DEFAULT NULL,
                n          DOUBLE PRECISION DEFAULT NULL,
                count      INTEGER DEFAULT NULL,
                norm_epa   DOUBLE PRECISION DEFAULT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (team, season, event_code)
            );

            CREATE TABLE IF NOT EXISTS team_matches (
                team         INTEGER NOT NULL,
                season       TEXT    NOT NULL,
                event_code   TEXT    NOT NULL,
                match_id     TEXT    NOT NULL,
                epa_pre      DOUBLE PRECISION DEFAULT NULL,
                epa_post     DOUBLE PRECISION DEFAULT NULL,
                mean_json_pre TEXT   DEFAULT NULL,
                win_prob     DOUBLE PRECISION DEFAULT NULL,
                is_elim      INTEGER NOT NULL DEFAULT 0,
                processed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (team, season, event_code, match_id)
            );

            CREATE TABLE IF NOT EXISTS seasons (
                season            TEXT    PRIMARY KEY NOT NULL,
                score_mean        DOUBLE PRECISION DEFAULT NULL,
                score_sd          DOUBLE PRECISION DEFAULT NULL,
                component_means_json TEXT DEFAULT NULL,
                num_matches       INTEGER DEFAULT 0,
                num_teams         INTEGER DEFAULT 0,
                updated_at        TIMESTAMP NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS events (
                event_code    TEXT    NOT NULL,
                season        TEXT    NOT NULL,
                name          TEXT    DEFAULT NULL,
                event_type    TEXT    DEFAULT NULL,
                start         TEXT    DEFAULT NULL,
                end           TEXT    DEFAULT NULL,
                location_json TEXT    DEFAULT NULL,
                region_code   TEXT    DEFAULT NULL,
                league_code   TEXT    DEFAULT NULL,
                updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (event_code, season)
            );

            CREATE TABLE IF NOT EXISTS teams (
                team       INTEGER PRIMARY KEY NOT NULL,
                name       TEXT    DEFAULT NULL,
                school_name TEXT   DEFAULT NULL,
                city       TEXT    DEFAULT NULL,
                state      TEXT    DEFAULT NULL,
                country    TEXT    DEFAULT NULL,
                rookie_year INTEGER DEFAULT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

    def _execute_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        rows = self._execute(query, params)
        return rows[0] if rows else None

    def load_team(self, team: int) -> Optional[Dict]:
        row = self._execute_one(
            "SELECT * FROM team_seasons WHERE team = ? AND season = ?",
            (team, self.season_id),
        )
        if row is None:
            return None
        return self._row_to_team(row)

    def load_team_event(self, team: int, event_code: str) -> Optional[Dict]:
        rows = self._execute(
            "SELECT * FROM team_events WHERE team = ? AND season = ? AND event_code = ?",
            (team, self.season_id, event_code),
        )
        if not rows:
            return None
        return self._row_to_event(rows[0])

    def load_season_meta(self) -> Optional[Dict]:
        rows = self._execute(
            "SELECT * FROM seasons WHERE season = ?",
            (self.season_id,),
        )
        if not rows:
            return None
        r = dict(rows[0])
        if r["component_means_json"]:
            r["component_means"] = np.array(
                json.loads(r["component_means_json"])
            )
        else:
            r["component_means"] = None
        r.pop("component_means_json", None)
        return r

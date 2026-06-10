import sqlite3
from pathlib import Path
from typing import Dict, List

from backend.src.storage.base_storage import BaseStorage


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str, season_id: str):
        super().__init__(season_id)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _execute(self, sql: str, params: tuple = ()) -> List[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            cur = conn.execute(sql, params)
            if cur.description:
                rows = cur.fetchall()
                conn.commit()
                return [dict(r) for r in rows]
            conn.commit()
            return []
        finally:
            conn.close()

    def _ensure_tables(self):
        conn = sqlite3.connect(str(self.db_path))
        old_schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='team_matches' AND sql NOT LIKE '%event_code%match_id%'"
        ).fetchone()
        if old_schema:
            conn.execute("DROP TABLE IF EXISTS team_matches")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS team_seasons (
                team      INTEGER NOT NULL,
                season    TEXT    NOT NULL,
                mean_json TEXT    NOT NULL,
                var_json  TEXT    NOT NULL,
                skew      REAL    NOT NULL DEFAULT 0.0,
                n         REAL    NOT NULL DEFAULT 1.0,
                count     INTEGER NOT NULL DEFAULT 0,
                norm_epa  REAL    DEFAULT NULL,
                updated_at TEXT   NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (team, season)
            );

            CREATE TABLE IF NOT EXISTS team_events (
                team       INTEGER NOT NULL,
                season     TEXT    NOT NULL,
                event_code TEXT    NOT NULL,
                event_type TEXT    DEFAULT NULL,
                epa_start  REAL    DEFAULT NULL,
                epa_max    REAL    DEFAULT NULL,
                epa_pre_elim REAL  DEFAULT NULL,
                epa_mean   REAL    DEFAULT NULL,
                mean_json  TEXT    DEFAULT NULL,
                var_json   TEXT    DEFAULT NULL,
                skew       REAL    DEFAULT NULL,
                n          REAL    DEFAULT NULL,
                count      INTEGER DEFAULT NULL,
                norm_epa   REAL    DEFAULT NULL,
                updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (team, season, event_code)
            );

            CREATE TABLE IF NOT EXISTS team_matches (
                team         INTEGER NOT NULL,
                season       TEXT    NOT NULL,
                event_code   TEXT    NOT NULL,
                match_id     TEXT    NOT NULL,
                epa_pre      REAL    DEFAULT NULL,
                epa_post     REAL    DEFAULT NULL,
                mean_json_pre TEXT   DEFAULT NULL,
                win_prob     REAL    DEFAULT NULL,
                is_elim      INTEGER NOT NULL DEFAULT 0,
                processed_at TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (team, season, event_code, match_id)
            );

            CREATE TABLE IF NOT EXISTS seasons (
                season            TEXT    PRIMARY KEY NOT NULL,
                score_mean        REAL    DEFAULT NULL,
                score_sd          REAL    DEFAULT NULL,
                component_means_json TEXT DEFAULT NULL,
                num_matches       INTEGER DEFAULT 0,
                num_teams         INTEGER DEFAULT 0,
                updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

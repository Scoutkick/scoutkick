import sqlite3
from pathlib import Path
from typing import List

from backend.src.storage.base_storage import BaseStorage


SCHEMA_VERSION = 2


class SQLiteStorage(BaseStorage):
    def __init__(self, db_path: str, season_id: str):
        super().__init__(season_id)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_tables()
        self._check_schema_version()

    def close(self):
        self._conn.close()

    def _check_schema_version(self):
        rows = self._execute("SELECT version FROM _schema_version")
        db_version = rows[0]["version"] if rows else 0
        if db_version != SCHEMA_VERSION:
            raise RuntimeError(
                f"DB schema v{db_version} != expected v{SCHEMA_VERSION}. "
                f"Delete or migrate {self.db_path}."
            )

    def _execute(self, sql: str, params: tuple = ()) -> List[dict]:
        cur = self._conn.execute(sql, params)
        if cur.description:
            rows = cur.fetchall()
            self._conn.commit()
            return [dict(r) for r in rows]
        self._conn.commit()
        return []

    def _execute_batch(self, sql: str, params_list: list) -> None:
        if not params_list:
            return
        try:
            self._conn.execute("BEGIN")
            self._conn.executemany(sql, params_list)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def save_team_matches_bulk(self, records: list):
        sql = """
            INSERT INTO team_matches (team, season, event_code, match_id,
                epa_pre, epa_post, mean_json_pre, win_prob, is_elim, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(team, season, event_code, match_id) DO UPDATE SET
                epa_post     = excluded.epa_post,
                mean_json_pre = excluded.mean_json_pre,
                win_prob     = excluded.win_prob,
                is_elim      = excluded.is_elim,
                processed_at = datetime('now')
        """
        params_list = [
            (r["team"], self.season_id, r["event_code"], r["match_id"],
             r.get("epa_pre"), r.get("epa_post"), r.get("mean_json_pre"),
             r.get("win_prob"), int(r.get("is_elim", False)))
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def save_team_events_bulk(self, records: list):
        sql = """
            INSERT INTO team_events (team, season, event_code, event_type,
                epa_start, epa_max, epa_pre_elim, epa_mean,
                mean_json, var_json, skew, n, count, norm_epa, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                updated_at = datetime('now')
        """
        import json
        params_list = [
            (r["team"], self.season_id, r["event_code"], r.get("event_type"),
             r.get("epa_start"), r.get("epa_max"), r.get("epa_pre_elim"), r.get("epa_mean"),
             json.dumps(r["mean"].tolist()) if r.get("mean") is not None else None,
             json.dumps(r["var"].tolist()) if r.get("var") is not None else None,
             r.get("skew"), r.get("n"), r.get("count"), r.get("norm_epa"))
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def save_events_metadata_bulk(self, records: list):
        sql = """
            INSERT INTO events (event_code, season, name, event_type, start, end,
                                location_json, region_code, league_code, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(event_code, season) DO UPDATE SET
                name         = COALESCE(excluded.name, events.name),
                event_type   = COALESCE(excluded.event_type, events.event_type),
                start        = COALESCE(excluded.start, events.start),
                end          = COALESCE(excluded.end, events.end),
                location_json = COALESCE(excluded.location_json, events.location_json),
                region_code  = COALESCE(excluded.region_code, events.region_code),
                league_code  = COALESCE(excluded.league_code, events.league_code),
                updated_at   = datetime('now')
        """
        import json
        params_list = [
            (r["event_code"], self.season_id, r.get("name"), r.get("event_type"),
             r.get("start"), r.get("end"),
             json.dumps(r["location"]) if r.get("location") else None,
             r.get("region_code"), r.get("league_code"))
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def save_team_info_bulk(self, records: list):
        sql = """
            INSERT INTO teams (team, name, school_name, city, state, country,
                               rookie_year, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(team) DO UPDATE SET
                name        = COALESCE(excluded.name, teams.name),
                school_name = COALESCE(excluded.school_name, teams.school_name),
                city        = COALESCE(excluded.city, teams.city),
                state       = COALESCE(excluded.state, teams.state),
                country     = COALESCE(excluded.country, teams.country),
                rookie_year = COALESCE(excluded.rookie_year, teams.rookie_year),
                updated_at  = datetime('now')
        """
        params_list = [
            (r["team"], r.get("name"), r.get("school_name"),
             r.get("city"), r.get("state"), r.get("country"),
             r.get("rookie_year"))
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def save_team_ranks_bulk(self, records: list):
        sql = """
            UPDATE team_seasons SET
                rank = ?, country_rank = ?, state_rank = ?, district_rank = ?,
                country_team_count = ?, state_team_count = ?, district_team_count = ?,
                team_country = ?, team_state = ?, team_district = ?
            WHERE team = ? AND season = ?
        """
        params_list = [
            (r["rank"], r.get("country_rank"), r.get("state_rank"),
             r.get("district_rank"), r.get("country_team_count"),
             r.get("state_team_count"), r.get("district_team_count"),
             r.get("team_country"), r.get("team_state"), r.get("team_district"),
             r["team"], self.season_id)
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def load_team_events_with_metadata(self, team: int) -> list:
        import json
        rows = self._execute("""
            SELECT te.*, e.name, e.start, e.end, e.location_json, e.region_code, e.league_code
            FROM team_events te
            LEFT JOIN events e ON te.event_code = e.event_code AND te.season = e.season
            WHERE te.team = ? AND te.season = ?
            ORDER BY te.event_code
        """, (team, self.season_id))
        result = []
        for r in rows:
            ev = self._row_to_event(r)
            ev["name"] = r.get("name")
            ev["start"] = r.get("start")
            ev["end"] = r.get("end")
            loc = r.get("location_json")
            ev["location"] = json.loads(loc) if loc else None
            result.append(ev)
        return result

    def save_all_teams_bulk(self, records: list):
        sql = """
            INSERT INTO team_seasons (team, season, mean_json, var_json,
                                      skew, n, count, norm_epa, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(team, season) DO UPDATE SET
                mean_json  = excluded.mean_json,
                var_json   = excluded.var_json,
                skew       = excluded.skew,
                n          = excluded.n,
                count      = excluded.count,
                norm_epa   = excluded.norm_epa,
                updated_at = datetime('now')
        """
        import json
        params_list = [
            (r["team"], self.season_id,
             json.dumps(r["mean"].tolist()),
             json.dumps(r["var"].tolist()),
             r["skew"], r["n"], r["count"], r.get("norm_epa"))
            for r in records
        ]
        for i in range(0, len(params_list), 500):
            self._execute_batch(sql, params_list[i:i + 500])

    def _ensure_tables(self):
        old_schema = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='team_matches' AND sql NOT LIKE '%event_code%match_id%'"
        ).fetchone()
        if old_schema:
            count = self._conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
            if count > 0:
                raise RuntimeError(
                    f"Refusing to drop team_matches with {count} rows. "
                    "Delete the DB manually or write a proper migration."
                )
            self._conn.execute("DROP TABLE IF EXISTS team_matches")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS _schema_version (
                version INTEGER NOT NULL
            );

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
                updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
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
                updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # Migrate v1 → v2: add rank columns to team_seasons
        rank_cols = [
            ("rank", "INTEGER"),
            ("country_rank", "INTEGER"),
            ("state_rank", "INTEGER"),
            ("district_rank", "INTEGER"),
            ("country_team_count", "INTEGER"),
            ("state_team_count", "INTEGER"),
            ("district_team_count", "INTEGER"),
            ("team_country", "TEXT"),
            ("team_state", "TEXT"),
            ("team_district", "TEXT"),
        ]
        for col_name, col_type in rank_cols:
            try:
                self._conn.execute(f"ALTER TABLE team_seasons ADD COLUMN {col_name} {col_type} DEFAULT NULL")
            except sqlite3.OperationalError:
                pass

        self._conn.execute(
            "INSERT INTO _schema_version (version) VALUES (?) "
            "ON CONFLICT(rowid) DO UPDATE SET version = excluded.version",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

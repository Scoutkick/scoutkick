import os
from pathlib import Path

from backend.src.storage.base_storage import BaseStorage
from backend.src.storage.sqlite_storage import SQLiteStorage


def get_db_path() -> str:
    return os.environ.get("EPA_DB_PATH") or str(
        Path.cwd() / "backend" / "cache" / "epa_data.db",
    )


def create_storage(season_id: str, db_path: str = "") -> BaseStorage:
    backend = os.environ.get("STORAGE_BACKEND", "sqlite")
    if backend == "postgres":
        from backend.src.storage.postgres_storage import PostgresStorage
        db_url = os.environ.get("DATABASE_URL", "")
        return PostgresStorage(db_url, season_id)
    if not db_path:
        db_path = get_db_path()
    return SQLiteStorage(db_path, season_id)

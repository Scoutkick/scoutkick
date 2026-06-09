import os
from typing import Union

from backend.src.storage.sqlite_storage import SQLiteStorage

StorageBackend = Union["SQLiteStorage", "PostgresStorage"]


def create_storage(season_id: str, db_path: str = "") -> StorageBackend:
    backend = os.environ.get("STORAGE_BACKEND", "sqlite")
    if backend == "postgres":
        from backend.src.storage.postgres_storage import PostgresStorage
        db_url = os.environ.get("DATABASE_URL", "")
        return PostgresStorage(db_url, season_id)
    if not db_path:
        db_path = os.environ.get("EPA_DB_PATH") or os.path.join(
            os.getcwd(), "cache", "epa_data.db",
        )
    return SQLiteStorage(db_path, season_id)

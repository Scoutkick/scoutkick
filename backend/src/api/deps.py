import os
from backend.src.storage.sqlite_storage import SQLiteStorage

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "cache", "epa_data.db",
)
DB_PATH = os.environ.get("EPA_DB_PATH") or _DEFAULT_DB_PATH


def get_storage(season: str = "2025") -> SQLiteStorage:
    return SQLiteStorage(DB_PATH, season)

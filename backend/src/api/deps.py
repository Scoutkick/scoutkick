import os

from backend.src.storage import create_storage

DB_PATH = os.environ.get("EPA_DB_PATH") or os.path.join(
    os.getcwd(), "cache", "epa_data.db",
)


def get_storage(season: str = "2025"):
    return create_storage(season, DB_PATH)

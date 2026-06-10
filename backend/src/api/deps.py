from backend.src.storage import create_storage, get_db_path

DB_PATH = get_db_path()


def get_storage(season: str = "2025"):
    return create_storage(season, DB_PATH)

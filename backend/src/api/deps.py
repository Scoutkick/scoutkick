from backend.src.core.constants import CURR_YEAR
from backend.src.storage import create_storage, get_db_path

DB_PATH = get_db_path()


def get_storage(season: str = CURR_YEAR):
    return create_storage(season, DB_PATH)

import logging

from fastapi import FastAPI

from backend.src.api.data import router as data_router, pipeline_status
from backend.src.api.deps import get_db_path
from backend.src.storage import create_storage

logger = logging.getLogger(__name__)

app = FastAPI(title="scoutkick data service", version="0.1.0")


@app.on_event("startup")
def startup():
    db_path = get_db_path()
    has_data = False
    try:
        storage = create_storage("2025", db_path)
        has_data = len(storage.load_all_seasons_meta()) > 0
    except Exception:
        pass
    if not has_data:
        logger.warning("DB is empty (%s). POST /v1/data/run to populate.", db_path)
    else:
        logger.info("DB has existing data — serving. (%s)", db_path)


app.include_router(data_router)


@app.get("/")
def root():
    return {
        "name": "scoutkick-data",
        "version": "0.1.0",
        "pipeline": pipeline_status,
    }

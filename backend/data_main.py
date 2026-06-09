import os

from fastapi import FastAPI

from backend.src.api.data import router as data_router, pipeline_status

app = FastAPI(title="scoutkick data service", version="0.1.0")


@app.on_event("startup")
def startup():
    db_path = os.environ.get("EPA_DB_PATH") or os.path.join(
        os.getcwd(), "cache", "epa_data.db",
    )
    has_data = False
    try:
        from backend.src.storage import create_storage
        storage = create_storage("2025", db_path)
        has_data = len(storage.load_all_seasons_meta()) > 0
    except Exception:
        pass
    if not has_data:
        print(f"[data] WARNING: DB is empty ({db_path}). POST /v1/data/run to populate.")
    else:
        print(f"[data] DB has existing data — serving. ({db_path})")


app.include_router(data_router)


@app.get("/")
def root():
    return {
        "name": "scoutkick-data",
        "version": "0.1.0",
        "pipeline": pipeline_status,
    }

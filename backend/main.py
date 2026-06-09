import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.src.api.router import api_router
from backend.src.services.pipeline_service import EPAPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    season = os.environ.get("EPA_SEASON", "2025")
    db_path = os.environ.get("EPA_DB_PATH", "cache/epa_data.db")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_pipeline, season, db_path)
    yield


def _run_pipeline(season: str, db_path: str):
    import sys
    print(f"[startup] Running pipeline for season {season} (db={db_path})...")
    try:
        pipeline = EPAPipeline(season, db_path=db_path)
        engine = pipeline.run()
        if engine:
            teams = list(engine.epas.keys())
            print(f"[startup] Pipeline complete: {len(teams)} teams trained")
        else:
            print("[startup] Pipeline returned no data (no matches found?)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[startup] Pipeline failed: {e}", file=sys.stderr)


app = FastAPI(title="scoutkick EPA API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
def root():
    return {"name": "scoutkick", "version": "0.1.0", "docs": "/docs"}

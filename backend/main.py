import asyncio
import os
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.src.api.router import api_router
from backend.src.core.config import SEASON_CONFIGS
from backend.src.services.pipeline_service import EPAPipeline


pipeline_status: dict = {"state": "pending", "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    seasons_env = os.environ.get("EPA_SEASONS")
    if seasons_env:
        seasons = [s.strip() for s in seasons_env.split(",") if s.strip()]
    else:
        seasons = sorted(SEASON_CONFIGS.keys())
    db_path = os.environ.get("EPA_DB_PATH", "cache/epa_data.db")
    print(f"[startup] Pipeline will process seasons: {seasons}")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_pipelines, seasons, db_path)
    yield


def _run_pipelines(seasons: list[str], db_path: str):
    global pipeline_status
    results = {}
    for season in seasons:
        pipeline_status["current_season"] = season
        pipeline_status["state"] = "running"
        print(f"\n{'='*60}")
        print(f"[startup] Running pipeline for season {season} (db={db_path})...")
        print(f"{'='*60}")
        try:
            pipeline = EPAPipeline(season, db_path=db_path)
            engine = pipeline.run()
            if engine:
                teams = list(engine.epas.keys())
                print(f"[startup] Season {season} complete: {len(teams)} teams trained")
                results[season] = {"teams": len(teams), "error": None}
            else:
                print(f"[startup] Season {season}: no matches found")
                results[season] = {"teams": 0, "error": "no matches"}
        except Exception as e:
            traceback.print_exc()
            print(f"[startup] Season {season} failed: {e}", file=sys.stderr)
            results[season] = {"teams": 0, "error": str(e)}
    pipeline_status["state"] = "done"
    pipeline_status["results"] = results
    total = sum(r["teams"] for r in results.values())
    print(f"\n{'='*60}")
    print(f"[startup] All pipelines complete. Total teams trained: {total}")
    print(f"{'='*60}")


app = FastAPI(title="scoutkick EPA API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "name": "scoutkick",
        "version": "0.1.0",
        "docs": "/docs",
        "pipeline": pipeline_status,
    }


@app.get("/v1/pipeline")
def get_pipeline_status():
    return pipeline_status

import logging
import threading
import traceback
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.src.core.config import SEASON_CONFIGS
from backend.src.services.pipeline_service import EPAPipeline
from backend.src.api.deps import DB_PATH

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Data"])

pipeline_status: dict = {"state": "pending", "error": None}
_pipeline_lock = threading.Lock()


def _run_pipelines(seasons: list[str], db_path: str):
    global pipeline_status
    results = {}
    for season in seasons:
        with _pipeline_lock:
            pipeline_status["current_season"] = season
            pipeline_status["state"] = "running"
        logger.info("Running pipeline for season %s (db=%s)", season, db_path)
        try:
            pipeline = EPAPipeline(season, db_path=db_path)
            engine = pipeline.run()
            if engine:
                teams = list(engine.epas.keys())
                logger.info("Season %s complete: %d teams trained", season, len(teams))
                results[season] = {"teams": len(teams), "error": None}
            else:
                logger.warning("Season %s: no matches found", season)
                results[season] = {"teams": 0, "error": "no matches"}
        except Exception as e:
            logger.exception("Season %s failed: %s", season, e)
            results[season] = {"teams": 0, "error": str(e)}
    with _pipeline_lock:
        pipeline_status["state"] = "done"
        pipeline_status["results"] = results
    total = sum(r["teams"] for r in results.values())
    logger.info("All pipelines complete. Total teams trained: %d", total)


@router.post("/v1/data/run")
def run_pipeline(
    background_tasks: BackgroundTasks,
    season: Optional[str] = None,
):
    with _pipeline_lock:
        if pipeline_status["state"] == "running":
            raise HTTPException(status_code=409, detail="Pipeline already running")
    if season is not None and season not in SEASON_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown season '{season}'")
    seasons = [season] if season else sorted(SEASON_CONFIGS.keys())
    background_tasks.add_task(_run_pipelines, seasons, DB_PATH)
    return {"status": "started", "seasons": seasons}


@router.post("/v1/data/run/{season}")
def run_single_season(season: str, background_tasks: BackgroundTasks):
    with _pipeline_lock:
        if pipeline_status["state"] == "running":
            raise HTTPException(status_code=409, detail="Pipeline already running")
    if season not in SEASON_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown season '{season}'")
    background_tasks.add_task(_run_pipelines, [season], DB_PATH)
    return {"status": "started", "season": season}


@router.get("/v1/data/status")
def data_status():
    with _pipeline_lock:
        return dict(pipeline_status)

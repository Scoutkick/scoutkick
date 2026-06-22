import logging
import threading

from fastapi import APIRouter

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


@router.get("/v1/data/status")
def data_status():
    with _pipeline_lock:
        return dict(pipeline_status)

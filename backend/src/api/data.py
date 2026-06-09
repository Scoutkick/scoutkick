import sys
import traceback
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.src.core.config import SEASON_CONFIGS
from backend.src.services.pipeline_service import EPAPipeline
from backend.src.api.deps import DB_PATH

router = APIRouter(tags=["Data"])

pipeline_status: dict = {"state": "pending", "error": None}


def _run_pipelines(seasons: list[str], db_path: str):
    global pipeline_status
    results = {}
    for season in seasons:
        pipeline_status["current_season"] = season
        pipeline_status["state"] = "running"
        print(f"\n{'='*60}")
        print(f"[data] Running pipeline for season {season} (db={db_path})...")
        print(f"{'='*60}")
        try:
            pipeline = EPAPipeline(season, db_path=db_path)
            engine = pipeline.run()
            if engine:
                teams = list(engine.epas.keys())
                print(f"[data] Season {season} complete: {len(teams)} teams trained")
                results[season] = {"teams": len(teams), "error": None}
            else:
                print(f"[data] Season {season}: no matches found")
                results[season] = {"teams": 0, "error": "no matches"}
        except Exception as e:
            traceback.print_exc()
            print(f"[data] Season {season} failed: {e}", file=sys.stderr)
            results[season] = {"teams": 0, "error": str(e)}
    pipeline_status["state"] = "done"
    pipeline_status["results"] = results
    total = sum(r["teams"] for r in results.values())
    print(f"\n{'='*60}")
    print(f"[data] All pipelines complete. Total teams trained: {total}")
    print(f"{'='*60}")


@router.post("/v1/data/run")
def run_pipeline(
    background_tasks: BackgroundTasks,
    season: Optional[str] = None,
):
    if pipeline_status["state"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running")
    if season is not None and season not in SEASON_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown season '{season}'")
    seasons = [season] if season else sorted(SEASON_CONFIGS.keys())
    background_tasks.add_task(_run_pipelines, seasons, DB_PATH)
    return {"status": "started", "seasons": seasons}


@router.post("/v1/data/run/{season}")
def run_single_season(season: str, background_tasks: BackgroundTasks):
    if pipeline_status["state"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running")
    if season not in SEASON_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown season '{season}'")
    background_tasks.add_task(_run_pipelines, [season], DB_PATH)
    return {"status": "started", "season": season}


@router.get("/v1/data/status")
def data_status():
    return pipeline_status

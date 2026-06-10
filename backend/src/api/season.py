import numpy as np
from fastapi import APIRouter, HTTPException
from backend.src.api.deps import get_storage

router = APIRouter(tags=["Season"])


def _serialize_meta(meta: dict) -> dict:
    r = dict(meta)
    for k, v in r.items():
        if isinstance(v, np.ndarray):
            r[k] = v.tolist()
        elif isinstance(v, (np.integer,)):
            r[k] = int(v)
        elif isinstance(v, (np.floating,)):
            r[k] = float(v)
    return r


@router.get("/v1/seasons")
def list_seasons():
    """List all seasons that have pipeline data stored in the database."""
    storage = get_storage()
    all_meta = storage.load_all_seasons_meta()
    value = [_serialize_meta(m) for m in all_meta]
    return {"value": value, "count": len(value)}


@router.get("/v1/season/{season}")
def get_season(season: str):
    """Get metadata (score_mean, score_sd, num_matches, etc.) for a specific season."""
    storage = get_storage(season)
    meta = storage.load_season_meta()
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Season {season} not found")
    return _serialize_meta(meta)

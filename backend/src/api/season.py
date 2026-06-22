import numpy as np
from fastapi import APIRouter, HTTPException
from backend.src.api.deps import get_storage
from backend.src.api.schemas import DistributionResponse, PaginatedResponse, SeasonMeta
from backend.src.core.constants import CURR_YEAR

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


@router.get("/v1/seasons", response_model=PaginatedResponse)
def list_seasons():
    """List all seasons that have pipeline data stored in the database."""
    storage = get_storage()
    all_meta = storage.load_all_seasons_meta()
    value = [_serialize_meta(m) for m in all_meta]
    return {"value": value, "count": len(value)}


@router.get("/v1/season/{season}", response_model=SeasonMeta)
def get_season(season: str):
    """Get metadata (score_mean, score_sd, num_matches, etc.) for a specific season."""
    storage = get_storage(season)
    meta = storage.load_season_meta()
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Season {season} not found")
    return _serialize_meta(meta)


@router.get("/v1/teams/{season}/distributions", response_model=DistributionResponse)
def get_team_distributions(season: str):
    """Get norm_epa distribution (percentiles, histogram) across all teams in a season."""
    storage = get_storage(season)
    teams = storage.load_all_teams()

    norm_epas = [v["norm_epa"] for v in teams.values() if v.get("norm_epa") is not None]

    if not norm_epas:
        raise HTTPException(status_code=404, detail=f"No team data found for season {season}")

    arr = np.array(norm_epas)
    percentiles = {
        "p1": float(np.percentile(arr, 1)),
        "p5": float(np.percentile(arr, 5)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }

    hist, bin_edges = np.histogram(arr, bins=20)
    histogram = [
        {"bin_start": float(bin_edges[i]), "bin_end": float(bin_edges[i + 1]), "count": int(hist[i])}
        for i in range(len(hist))
    ]

    return {
        "season": season,
        "count": int(len(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "percentiles": percentiles,
        "histogram": histogram,
    }

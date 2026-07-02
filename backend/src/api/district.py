from fastapi import APIRouter
from backend.src.api.deps import get_storage
from backend.src.api.schemas import PaginatedResponse
from backend.src.core.constants import CURR_YEAR

router = APIRouter(tags=["District"])


@router.get("/v1/districts", response_model=PaginatedResponse)
def list_districts():
    """List all FTC districts (region codes) with event and team counts across all seasons."""
    storage = get_storage(CURR_YEAR)
    districts = storage.load_all_districts()
    return {"value": districts, "count": len(districts)}

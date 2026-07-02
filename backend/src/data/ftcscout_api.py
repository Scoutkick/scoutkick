import json
import logging
import os
import hashlib
import tempfile
from typing import Any, Optional, Union
from requests import Session

logger = logging.getLogger(__name__)

# Base URL for FTCscout GraphQL API
GRAPHQL_URL = os.environ.get("FTCSCOUT_URL", "https://api.ftcscout.org/graphql")
CACHE_DIR = os.environ.get("FTCSCOUT_CACHE_DIR", "backend/cache/ftcscout")

session = Session()

def _post_graphql(query: str, variables: Optional[dict] = None) -> Union[Any, bool]:
    """Low-level POST request to the GraphQL endpoint."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        timeout = int(os.environ.get("FTCSCOUT_TIMEOUT", "60"))
        response = session.post(GRAPHQL_URL, json=payload, timeout=timeout)
        if response.status_code == 200:
            json_data = response.json()
            if "errors" in json_data:
                logger.error("GraphQL Errors: %s", json_data["errors"])
                return False
            return json_data.get("data")
    except Exception as e:
        logger.error("API Request Error: %s", e)

    return False

def get_ftcscout(query: str, variables: Optional[dict] = None, cache: bool = True) -> Union[Any, bool]:
    """
    Wraps GraphQL calls with local disk caching.
    Caches are stored as JSON files based on the hash of the query and variables.
    """
    query_hash = hashlib.sha256(f"{query}{variables}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{query_hash}.json")

    if cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Cache read error: %s", e)

    data = _post_graphql(query, variables)

    if data is not False:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, cache_path)
            except Exception:
                os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    return data

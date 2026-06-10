import logging
import os
import hashlib
import pickle
from typing import Any, Optional, Union
from requests import Session

logger = logging.getLogger(__name__)

# Base URL for FTCscout GraphQL API
GRAPHQL_URL = os.environ.get("FTCSCOUT_URL", "https://api.ftcscout.org/graphql")
CACHE_DIR = os.environ.get("FTCSCOUT_CACHE_DIR", "cache/ftcscout")

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
    Caches are stored as pickle files based on the hash of the query and variables.
    """
    query_hash = hashlib.sha256(f"{query}{variables}".encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{query_hash}.p")

    if cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning("Cache read error: %s", e)

    data = _post_graphql(query, variables)

    if data is not False:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    return data

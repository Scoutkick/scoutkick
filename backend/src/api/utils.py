from typing import Any, Callable, Dict, List, Optional


def sort_and_page(
    items: List[Dict],
    sort_key_map: Dict[str, Callable],
    metric: str,
    ascending: bool,
    offset: int,
    limit: int,
    default_metric: str = "",
) -> Dict[str, Any]:
    key_fn = sort_key_map.get(metric, sort_key_map.get(default_metric, lambda x: 0))
    items.sort(key=key_fn, reverse=not ascending)
    return {"value": items[offset:offset + limit], "count": len(items)}

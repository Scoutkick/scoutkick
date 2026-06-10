import logging
import statistics
from typing import List, Optional

import numpy as np

from backend.src.core.config import FTC_VECTOR_SIZE
from backend.src.data.cleaner import BaseCleaner
from backend.src.data.read_ftcscout import get_matches

logger = logging.getLogger(__name__)


def calibrate_score_sd(
    cleaner: BaseCleaner,
    season_id: str,
    max_matches: Optional[int] = None,
) -> float:
    matches = get_matches(cleaner)

    if not matches:
        logger.warning("calibrate_score_sd: no matches found for %s, using default", season_id)
        return 20.0

    if max_matches is not None:
        matches = matches[:max_matches]

    scores: List[float] = []
    for m in matches:
        red_total = m.get("red_scores", {}).get("totalPointsNp")
        blue_total = m.get("blue_scores", {}).get("totalPointsNp")
        if red_total is not None:
            scores.append(float(red_total))
        if blue_total is not None:
            scores.append(float(blue_total))

    if len(scores) < 2:
        logger.warning("calibrate_score_sd: too few scores (%d), using default", len(scores))
        return 20.0

    sd = statistics.stdev(scores)
    logger.info("calibrate_score_sd(%s): %.2f from %d scores across %d matches",
                season_id, sd, len(scores), len(matches))
    return round(sd, 2)


def calibrate_component_means(
    cleaner: BaseCleaner,
    season_id: str,
    max_matches: Optional[int] = None,
) -> np.ndarray:
    matches = get_matches(cleaner)

    if not matches:
        return np.zeros(FTC_VECTOR_SIZE)

    if max_matches is not None:
        matches = matches[:max_matches]

    vec_sum = np.zeros(FTC_VECTOR_SIZE)
    count = 0
    for m in matches:
        red_raw = cleaner.aggregate(m.get("red_scores", {}))
        blue_raw = cleaner.aggregate(m.get("blue_scores", {}))
        red_vec = cleaner.clean(red_raw)
        blue_vec = cleaner.clean(blue_raw)
        vec_sum += red_vec + blue_vec
        count += 2

    if count == 0:
        return np.zeros(FTC_VECTOR_SIZE)

    means = vec_sum / count
    logger.info("calibrate_component_means(%s): %d observations", season_id, count)
    return means

import numpy as np
from typing import Dict, List, Any
from abc import ABC
from backend.src.core.config import FTC_VECTOR_SIZE


class BaseCleaner(ABC):
    SEASON_ID: str = ""
    GRAPHQL_FRAGMENT: str = ""

    FIELD_TO_EPA_INDEX: Dict[str, int] = {}
    BOOL_FIELDS: List[str] = []
    FIELD_WEIGHTS: Dict[str, float] = {}
    COMPOSITE_DIMS: Dict[int, List[str]] = {}
    API_FIELDS: List[str] = []

    _registry: Dict[str, "BaseCleaner"] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.API_FIELDS:
            fields = set(cls.FIELD_TO_EPA_INDEX.keys())
            for dim_fields in cls.COMPOSITE_DIMS.values():
                fields.update(dim_fields)
            cls.API_FIELDS = sorted(fields)
        if cls.SEASON_ID:
            BaseCleaner._registry[cls.SEASON_ID] = cls()

    @classmethod
    def get_cleaner(cls, season_id: str) -> "BaseCleaner":
        if season_id not in cls._registry:
            raise ValueError(f"No cleaner registered for season {season_id}")
        return cls._registry[season_id]

    def clean(self, data: Dict[str, Any]) -> np.ndarray:
        vec = np.zeros(FTC_VECTOR_SIZE)
        for field, idx in self.FIELD_TO_EPA_INDEX.items():
            val = data.get(field, 0)
            if field in self.BOOL_FIELDS:
                val = 1.0 if val else 0.0
            vec[idx] = val * self.FIELD_WEIGHTS.get(field, 1.0)
        for idx, fields in self.COMPOSITE_DIMS.items():
            vec[idx] = sum(data.get(f, 0) for f in fields)
        return vec

    def get_graphql_fragment(self) -> str:
        fields = "\n".join(f"            {f}" for f in self.API_FIELDS)
        return f"""        ... on {self.GRAPHQL_FRAGMENT} {{
          red {{
{fields}
          }}
          blue {{
{fields}
          }}
        }}"""

    def aggregate(self, scores: Dict[str, Any]) -> Dict[str, Any]:
        return scores

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        return np.full((n, FTC_VECTOR_SIZE), 1.0 / n)


# ── 2025: Into The Deep ──────────────────────────────────────────

class FTC2025Cleaner(BaseCleaner):
    SEASON_ID = "2025"
    GRAPHQL_FRAGMENT = "MatchScores2025"

    API_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "dcBasePoints",
        "movementRp", "goalRp", "patternRp",
        "autoArtifactClassifiedPoints", "dcArtifactClassifiedPoints",
        "dcDepotPoints", "alliance",
        "autoLeave1", "autoLeave2",
        "dcBase1", "dcBase2",
    ]

    BOOL_FIELDS = ["movementRp", "goalRp", "patternRp"]

    FIELD_WEIGHTS = {
        "autoArtifactClassifiedPoints": 1.0 / 3.0,
        "dcArtifactClassifiedPoints": 1.0 / 3.0,
    }

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "dcBasePoints": 3,
        "movementRp": 4,
        "goalRp": 5,
        "patternRp": 6,
        "autoArtifactClassifiedPoints": 7,
        "dcArtifactClassifiedPoints": 8,
        "dcDepotPoints": 9,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        dc1 = float(raw_scores.get("dcBase1", 0))
        dc2 = float(raw_scores.get("dcBase2", 0))
        dc_total = dc1 + dc2
        if dc_total > 0:
            weights[0, 3] = dc1 / dc_total
            weights[1, 3] = dc2 / dc_total
        al1 = float(raw_scores.get("autoLeave1", 0))
        al2 = float(raw_scores.get("autoLeave2", 0))
        auto_total = float(raw_scores.get("autoPoints", 0))
        auto_leave_total = al1 + al2
        if auto_total > 0 and auto_leave_total > 0:
            known_share = auto_leave_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (al1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (al2 / auto_total) + unknown_share * 0.5
        return weights


# ── 2024: CENTERSTAGE ────────────────────────────────────────────

class FTC2024Cleaner(BaseCleaner):
    SEASON_ID = "2024"
    GRAPHQL_FRAGMENT = "MatchScores2024"

    API_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints",
        "autoParkPoints", "dcParkPoints",
        "autoSamplePoints", "autoSpecimenPoints",
        "dcSamplePoints", "dcSpecimenPoints",
        "autoPark1", "autoPark2",
        "dcPark1", "dcPark2",
    ]

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
    }

    COMPOSITE_DIMS = {3: ["autoParkPoints", "dcParkPoints"]}

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        p1 = float(raw_scores.get("autoPark1", 0)) + float(raw_scores.get("dcPark1", 0))
        p2 = float(raw_scores.get("autoPark2", 0)) + float(raw_scores.get("dcPark2", 0))
        total = p1 + p2
        if total > 0:
            weights[0, 3] = p1 / total
            weights[1, 3] = p2 / total
        return weights


# ── 2023: CENTERSTAGE ────────────────────────────────────────────

class FTC2023Cleaner(BaseCleaner):
    SEASON_ID = "2023"
    GRAPHQL_FRAGMENT = "MatchScores2023"

    API_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoNavPoints", "autoPixelPoints", "purplePoints", "yellowPoints",
        "egNavPoints", "dronePoints", "setLinePoints", "mosaicPoints",
        "autoNav1", "autoNav2", "purple1", "purple2",
        "yellow1", "yellow2", "drone1", "drone2",
        "egNav2023_1", "egNav2023_2",
    ]

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "egPoints": 3,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        an1 = float(raw_scores.get("autoNav1", 0))
        an2 = float(raw_scores.get("autoNav2", 0))
        auto_nav_total = an1 + an2
        auto_total = float(raw_scores.get("autoPoints", 0))
        if auto_total > 0 and auto_nav_total > 0:
            known_share = auto_nav_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (an1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (an2 / auto_total) + unknown_share * 0.5
        eg_nav_1 = float(raw_scores.get("egNav2023_1", 0))
        eg_nav_2 = float(raw_scores.get("egNav2023_2", 0))
        dr1 = float(raw_scores.get("drone1", 0))
        dr2 = float(raw_scores.get("drone2", 0))
        purple1 = float(raw_scores.get("purple1", 0))
        purple2 = float(raw_scores.get("purple2", 0))
        yellow1 = float(raw_scores.get("yellow1", 0))
        yellow2 = float(raw_scores.get("yellow2", 0))
        known_eg = eg_nav_1 + eg_nav_2 + dr1 + dr2
        known_dc = purple1 + purple2 + yellow1 + yellow2
        eg_total = float(raw_scores.get("egPoints", 0))
        if eg_total > 0 and known_eg > 0:
            r1_eg_share = (eg_nav_1 + dr1) / eg_total
            r2_eg_share = (eg_nav_2 + dr2) / eg_total
            unknown_eg_share = 1.0 - (known_eg / eg_total)
            weights[0, 3] = r1_eg_share + unknown_eg_share * 0.5
            weights[1, 3] = r2_eg_share + unknown_eg_share * 0.5
        dc_total = float(raw_scores.get("dcPoints", 0))
        if dc_total > 0 and known_dc > 0:
            r1_dc_share = (purple1 + yellow1) / dc_total
            r2_dc_share = (purple2 + yellow2) / dc_total
            unknown_dc_share = 1.0 - (known_dc / dc_total)
            weights[0, 2] = r1_dc_share + unknown_dc_share * 0.5
            weights[1, 2] = r2_dc_share + unknown_dc_share * 0.5
        return weights


# ── 2022: Power Play ────────────────────────────────────────────

class FTC2022Cleaner(BaseCleaner):
    SEASON_ID = "2022"
    GRAPHQL_FRAGMENT = "MatchScores2022"

    API_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoNavPoints", "autoConePoints",
        "egNavPoints", "ownershipPoints", "circuitPoints",
        "autoNav2022_1", "autoNav2022_2",
        "egNav1", "egNav2",
    ]

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "egPoints": 3,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        an1 = float(raw_scores.get("autoNav2022_1", 0))
        an2 = float(raw_scores.get("autoNav2022_2", 0))
        auto_nav_total = an1 + an2
        auto_total = float(raw_scores.get("autoPoints", 0))
        if auto_total > 0 and auto_nav_total > 0:
            known_share = auto_nav_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (an1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (an2 / auto_total) + unknown_share * 0.5
        en1 = float(raw_scores.get("egNav1", 0))
        en2 = float(raw_scores.get("egNav2", 0))
        eg_nav_total = en1 + en2
        eg_total = float(raw_scores.get("egPoints", 0))
        if eg_total > 0 and eg_nav_total > 0:
            known_share = eg_nav_total / eg_total
            unknown_share = 1.0 - known_share
            weights[0, 3] = (en1 / eg_total) + unknown_share * 0.5
            weights[1, 3] = (en2 / eg_total) + unknown_share * 0.5
        return weights


# ── 2021: Freight Frenzy ─────────────────────────────────────────

class FTC2021Cleaner(BaseCleaner):
    SEASON_ID = "2021"
    GRAPHQL_FRAGMENT = ""

    PER_ROBOT_TRAD = [
        "autoNavigated1", "autoNavigated2",
        "autoFreight1", "autoFreight2",
        "dcFreight1", "dcFreight2",
        "egParked1", "egParked2",
    ]

    TRAD_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoCarouselPoints", "autoNavPoints", "autoFreightPoints", "autoBonusPoints",
        "dcAllianceHubPoints", "dcSharedHubPoints", "dcStoragePoints",
        "egDuckPoints", "allianceBalancedPoints", "sharedUnbalancedPoints",
        "egParkPoints", "cappingPoints",
    ] + PER_ROBOT_TRAD

    PER_ROBOT_REMOTE = [
        "autoNavigated1", "autoNavigated2",
        "autoFreight1", "autoFreight2",
        "dcFreight1", "dcFreight2",
        "egParked1", "egParked2",
    ]

    REMOTE_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoCarouselPoints", "autoNavPoints", "autoFreightPoints", "autoBonusPoints",
        "dcAllianceHubPoints", "dcStoragePoints",
        "egDuckPoints", "allianceBalancedPoints",
        "egParkPoints", "cappingPoints",
    ] + PER_ROBOT_REMOTE

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "egPoints": 3,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        an1 = float(raw_scores.get("autoNavigated1", 0))
        an2 = float(raw_scores.get("autoNavigated2", 0))
        auto_nav_total = an1 + an2
        auto_total = float(raw_scores.get("autoPoints", 0))
        if auto_total > 0 and auto_nav_total > 0:
            known_share = auto_nav_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (an1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (an2 / auto_total) + unknown_share * 0.5
        ep1 = float(raw_scores.get("egParked1", 0))
        ep2 = float(raw_scores.get("egParked2", 0))
        eg_park_total = ep1 + ep2
        eg_total = float(raw_scores.get("egPoints", 0))
        if eg_total > 0 and eg_park_total > 0:
            known_share = eg_park_total / eg_total
            unknown_share = 1.0 - known_share
            weights[0, 3] = (ep1 / eg_total) + unknown_share * 0.5
            weights[1, 3] = (ep2 / eg_total) + unknown_share * 0.5
        return weights

    def get_graphql_fragment(self) -> str:
        trad = "\n".join(f"            {f}" for f in self.TRAD_FIELDS)
        remote = "\n".join(f"            {f}" for f in self.REMOTE_FIELDS)
        return f"""        ... on MatchScores2021Trad {{
          red {{
{trad}
          }}
          blue {{
{trad}
          }}
        }}
        ... on MatchScores2021Remote {{
          alliance
{remote}
        }}"""


# ── 2020: Ultimate Goal ──────────────────────────────────────────

class FTC2020Cleaner(BaseCleaner):
    SEASON_ID = "2020"
    GRAPHQL_FRAGMENT = ""

    PER_ROBOT_TRAD = [
        "autoWobble1", "autoWobble2",
        "autoNav2020_1", "autoNav2020_2",
        "wobbleEndPos1", "wobbleEndPos2",
    ]

    TRAD_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoNavPoints", "autoTowerPoints", "autoWobblePoints", "autoPowershotPoints",
        "egWobblePoints", "egPowershotPoints", "egWobbleRingPoints",
    ] + PER_ROBOT_TRAD

    PER_ROBOT_REMOTE = [
        "autoWobble1", "autoWobble2",
        "autoNav2020_1", "autoNav2020_2",
        "wobbleEndPos1", "wobbleEndPos2",
    ]

    REMOTE_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoNavPoints", "autoTowerPoints", "autoWobblePoints", "autoPowershotPoints",
        "egWobblePoints", "egPowershotPoints", "egWobbleRingPoints",
    ] + PER_ROBOT_REMOTE

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "egPoints": 3,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        an1 = float(raw_scores.get("autoNav2020_1", 0))
        an2 = float(raw_scores.get("autoNav2020_2", 0))
        auto_nav_total = an1 + an2
        auto_total = float(raw_scores.get("autoPoints", 0))
        if auto_total > 0 and auto_nav_total > 0:
            known_share = auto_nav_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (an1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (an2 / auto_total) + unknown_share * 0.5
        aw1 = float(raw_scores.get("autoWobble1", 0))
        aw2 = float(raw_scores.get("autoWobble2", 0))
        wobble_auto_total = aw1 + aw2
        if auto_total > 0 and wobble_auto_total > 0:
            known_share = wobble_auto_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (weights[0, 1] + (aw1 / auto_total) + unknown_share * 0.5) / 2
            weights[1, 1] = (weights[1, 1] + (aw2 / auto_total) + unknown_share * 0.5) / 2
        we1 = float(raw_scores.get("wobbleEndPos1", 0))
        we2 = float(raw_scores.get("wobbleEndPos2", 0))
        wobble_eg_total = we1 + we2
        eg_total = float(raw_scores.get("egPoints", 0))
        if eg_total > 0 and wobble_eg_total > 0:
            known_share = wobble_eg_total / eg_total
            unknown_share = 1.0 - known_share
            weights[0, 3] = (we1 / eg_total) + unknown_share * 0.5
            weights[1, 3] = (we2 / eg_total) + unknown_share * 0.5
        return weights

    def get_graphql_fragment(self) -> str:
        trad = "\n".join(f"            {f}" for f in self.TRAD_FIELDS)
        remote = "\n".join(f"            {f}" for f in self.REMOTE_FIELDS)
        return f"""        ... on MatchScores2020Trad {{
          red {{
{trad}
          }}
          blue {{
{trad}
          }}
        }}
        ... on MatchScores2020Remote {{
          alliance
{remote}
        }}"""


# ── 2019: SkyStone ───────────────────────────────────────────────

class FTC2019Cleaner(BaseCleaner):
    SEASON_ID = "2019"
    GRAPHQL_FRAGMENT = "MatchScores2019"

    API_FIELDS = [
        "totalPointsNp", "autoPoints", "dcPoints", "egPoints",
        "autoNavPoints", "autoRepositioningPoints", "autoDeliveryPoints", "autoPlacementPoints",
        "dcDeliveryPoints", "dcPlacementPoints",
        "skyscraperBonusPoints", "cappingPoints",
        "egParkPoints", "egFoundationMovedPoints",
        "autoNav2019_1", "autoNav2019_2",
        "egParked1", "egParked2",
        "capLevel1", "capLevel2",
    ]

    FIELD_TO_EPA_INDEX = {
        "totalPointsNp": 0,
        "autoPoints": 1,
        "dcPoints": 2,
        "egPoints": 3,
    }

    def get_attribution_weights(self, raw_scores: Dict[str, Any],
                                team_numbers: List[int]) -> np.ndarray:
        n = len(team_numbers)
        weights = np.full((n, FTC_VECTOR_SIZE), 1.0 / n)
        an1 = float(raw_scores.get("autoNav2019_1", 0))
        an2 = float(raw_scores.get("autoNav2019_2", 0))
        auto_nav_total = an1 + an2
        auto_total = float(raw_scores.get("autoPoints", 0))
        if auto_total > 0 and auto_nav_total > 0:
            known_share = auto_nav_total / auto_total
            unknown_share = 1.0 - known_share
            weights[0, 1] = (an1 / auto_total) + unknown_share * 0.5
            weights[1, 1] = (an2 / auto_total) + unknown_share * 0.5
        ep1 = float(raw_scores.get("egParked1", 0))
        ep2 = float(raw_scores.get("egParked2", 0))
        eg_park_total = ep1 + ep2
        eg_total = float(raw_scores.get("egPoints", 0))
        if eg_total > 0 and eg_park_total > 0:
            known_share = eg_park_total / eg_total
            unknown_share = 1.0 - known_share
            weights[0, 3] = (ep1 / eg_total) + unknown_share * 0.5
            weights[1, 3] = (ep2 / eg_total) + unknown_share * 0.5
        return weights




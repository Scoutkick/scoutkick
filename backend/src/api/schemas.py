from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Generic wrappers ──

class PaginatedResponse(BaseModel):
    value: List[Any]
    count: int


# ── Team ──

class TeamSummary(BaseModel):
    team: int
    total: float
    auto: float
    teleop: float
    endgame: float
    norm_epa: Optional[float] = None
    matches: int


class TeamMatch(BaseModel):
    event_code: str
    match_id: str
    epa_pre: Optional[float] = None
    epa_post: Optional[float] = None
    win_prob: Optional[float] = None
    is_elim: bool = False
    processed_at: Optional[str] = None


class TeamDetail(BaseModel):
    team: int
    season: str
    total: float
    auto: float
    teleop: float
    endgame: float
    mean: List[float]
    var: List[float]
    skew: float
    n: float
    count: int
    norm_epa: Optional[float] = None
    team_matches: List[TeamMatch]


class TeamEvent(BaseModel):
    event_code: str
    event_type: Optional[str] = None
    epa_start: Optional[float] = None
    epa_max: Optional[float] = None
    epa_mean: Optional[float] = None
    epa_pre_elim: Optional[float] = None
    count: Optional[int] = None
    norm_epa: Optional[float] = None
    mean: Optional[List[float]] = None
    var: Optional[List[float]] = None


# ── Event ──

class EventSummary(BaseModel):
    event_code: str
    event_type: Optional[str] = None
    team_count: int
    epa_max: Optional[float] = None
    epa_mean: Optional[float] = None


class EventTeam(BaseModel):
    team: int
    epa_start: Optional[float] = None
    epa_max: Optional[float] = None
    epa_mean: Optional[float] = None
    epa_pre_elim: Optional[float] = None
    count: Optional[int] = None
    norm_epa: Optional[float] = None


class EventDetail(BaseModel):
    event_code: str
    event_type: Optional[str] = None
    season: str
    team_count: int
    teams: List[EventTeam]


class EventMatchTeam(BaseModel):
    team: int
    epa_pre: Optional[float] = None
    epa_post: Optional[float] = None
    win_prob: Optional[float] = None


class EventMatch(BaseModel):
    event_code: str
    match_id: str
    is_elim: bool = False
    teams: List[EventMatchTeam]


# ── Match ──

class MatchSummary(BaseModel):
    event_code: str
    match_id: str
    team: int
    epa_pre: Optional[float] = None
    epa_post: Optional[float] = None
    win_prob: Optional[float] = None
    is_elim: bool = False
    processed_at: Optional[str] = None


class MatchDetail(BaseModel):
    event_code: str
    match_id: str
    season: str
    is_elim: bool = False
    teams: List[EventMatchTeam]


# ── Predict ──

class PredictTeam(BaseModel):
    team: int
    total: float
    auto: float
    teleop: float
    endgame: float
    norm_epa: Optional[float] = None


class PredictionResult(BaseModel):
    red_teams: List[PredictTeam]
    blue_teams: List[PredictTeam]
    red_win_prob: float
    blue_win_prob: float
    predicted_red: Dict[str, float]
    predicted_blue: Dict[str, float]


class CompareTeam(BaseModel):
    team: int
    total: float
    auto: float
    teleop: float
    endgame: float
    variance: float
    skew: float
    matches: int


class CompareResult(BaseModel):
    season: str
    teams: List[CompareTeam]


# ── Season ──

class SeasonMeta(BaseModel):
    season: str
    score_mean: Optional[float] = None
    score_sd: Optional[float] = None
    component_means: Optional[List[float]] = None
    num_matches: Optional[int] = None
    num_teams: Optional[int] = None
    updated_at: Optional[str] = None


# ── FTCScout Proxy ──

class Location(BaseModel):
    venue: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class EventInfo(BaseModel):
    event_code: str
    name: Optional[str] = None
    event_type: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    location: Optional[Location] = None
    regionCode: Optional[str] = None
    team_count: int = 0
    epa_max: Optional[float] = None
    epa_mean: Optional[float] = None


class TeamInfo(BaseModel):
    team: int
    name: Optional[str] = None
    school_name: Optional[str] = None
    sponsors: List[str] = Field(default_factory=list)
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    rookie_year: Optional[int] = None
    website: Optional[str] = None


# ── Site (frontend-optimized bundles) ──

class TeamInfo(BaseModel):
    team: int
    name: Optional[str] = None
    school_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    rookie_year: Optional[int] = None


class TeamSeasonSummary(BaseModel):
    team: int
    season: str
    total: float
    auto: float
    teleop: float
    endgame: float
    mean: List[float]
    var: List[float]
    skew: float
    n: float
    count: int
    norm_epa: Optional[float] = None
    rank: Optional[int] = None
    country_rank: Optional[int] = None
    state_rank: Optional[int] = None
    district_rank: Optional[int] = None
    country_team_count: Optional[int] = None
    state_team_count: Optional[int] = None
    district_team_count: Optional[int] = None


class SiteTeamPage(BaseModel):
    team_info: TeamInfo
    season: TeamSeasonSummary
    matches: List[TeamMatch]
    season_meta: SeasonMeta
    event_names: Dict[str, str]


class SiteEventStanding(BaseModel):
    team: int
    name: Optional[str] = None
    norm_epa: Optional[float] = None
    rank: Optional[int] = None
    epa_start: Optional[float] = None
    epa_max: Optional[float] = None
    epa_mean: Optional[float] = None
    epa_pre_elim: Optional[float] = None
    count: Optional[int] = None


class SiteEventPage(BaseModel):
    event_code: str
    name: Optional[str] = None
    season: str
    event_type: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    location: Optional[Location] = None
    standings: List[SiteEventStanding]
    qual_matches: List[EventMatch]
    elim_matches: List[EventMatch]
    season_meta: SeasonMeta


class SiteMatchPage(BaseModel):
    event_code: str
    event_name: Optional[str] = None
    match_id: str
    season: str
    is_elim: bool = False
    teams: List[EventMatchTeam]
    red_teams: List[int]
    blue_teams: List[int]
    red_total: Optional[float] = None
    blue_total: Optional[float] = None
    red_win_prob: Optional[float] = None
    season_meta: SeasonMeta


class SiteTeamLight(BaseModel):
    team: int
    name: Optional[str] = None


class SiteEventLight(BaseModel):
    event_code: str
    name: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


# ── Data Pipeline ──

class PipelineStatus(BaseModel):
    state: str
    current_season: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

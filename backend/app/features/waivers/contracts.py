from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["this_week", "next_7_days", "ros"]
QualityState = Literal["available", "partial", "missing", "stale", "unknown", "unsupported", "unavailable"]
SampleLabel = Literal["EXCELLENT", "GOOD", "LIMITED", "VERY LIMITED", "INSUFFICIENT FOR STRONG RECOMMENDATION", "NO CURRENT-SEASON EVIDENCE"]
Decision = Literal["MUST ADD", "ADD", "STREAM", "WATCH", "PASS", "INSUFFICIENT EVIDENCE"]


class Evidence(BaseModel):
    state: QualityState
    source: str
    as_of: datetime | None = None
    detail: str
    sample_count: int | None = None


class Components(BaseModel):
    roster_fit: float | None = None
    player_value: float | None = None
    opportunity: float | None = None
    schedule: float | None = None
    acquisition_value: float | None = None


class ValueEvidence(BaseModel):
    value: float | None = None
    games: int = 0
    season: str | None = None
    per_game_stats: dict[str, float] = Field(default_factory=dict)
    label: str
    sample_label: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    scoring_contributions: dict[str, float] = Field(default_factory=dict)


class RankingEvidence(BaseModel):
    value: float | None = None
    recent_weight: float | None = None
    historical_value: float | None = None
    historical_games: int = 0
    historical_season: str | None = None
    label: str = "Production ranking unavailable"


class RoleWindow(BaseModel):
    average: float | None = None
    median: float | None = None
    games: int = 0
    game_ids: list[str] = Field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    as_of: datetime | None = None
    missing_game_ids: list[str] = Field(default_factory=list)
    stale_game_ids: list[str] = Field(default_factory=list)


class RoleMetric(BaseModel):
    quality: Evidence
    recent: RoleWindow = Field(default_factory=RoleWindow)
    comparison: RoleWindow = Field(default_factory=RoleWindow)
    delta: float | None = None
    median_delta: float | None = None
    unit: str


class StartsEvidence(BaseModel):
    quality: Evidence
    season: str | None = None
    season_starts: int | None = None
    season_games: int | None = None
    recent_starts: int | None = None
    detail: str = "Game-level starter evidence is not established; season starts do not prove the current lineup."


class CurrentRole(BaseModel):
    minutes: RoleMetric
    usage: RoleMetric
    starts: StartsEvidence
    quality: Evidence
    trend: Literal["RISING", "STABLE", "FALLING", "INSUFFICIENT EVIDENCE"] = "INSUFFICIENT EVIDENCE"
    season_usage: float | None = None
    season_usage_quality: Evidence
    method: str
    limitations: list[str]


class Opportunity(BaseModel):
    minutes: float | None = None
    minutes_trend: float | None = None
    usage_trend: float | None = None
    historical_start_rate: float | None = None
    role: str = "Unknown"
    score: float | None = None
    score_parts: dict[str, float] = Field(default_factory=dict)
    current_role: CurrentRole | None = None


class Schedule(BaseModel):
    games_remaining: int | None = None
    off_day_games: int | None = None
    back_to_backs: int | None = None
    next_7_days_games: int | None = None
    opponents: list[str] = Field(default_factory=list)
    source_row_count: int = 0
    window_start: date
    window_end: date
    imported_at: datetime | None = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    coverage: Literal["COMPLETE", "PARTIAL", "UNKNOWN", "STALE"] = "UNKNOWN"
    diagnostic_reason: Literal[
        "NBA_ID_UNMAPPED",
        "TEAM_MAPPING_MISSING",
        "NO_PLAYER_SCHEDULE_ROWS",
        "NO_GAMES_IN_WINDOW",
        "SCHEDULE_STALE",
        "SCHEDULE_ROWS_PRESENT",
        "SCHEDULE_SOURCE_INCOMPLETE",
    ] = "NO_PLAYER_SCHEDULE_ROWS"


class CoverageMetric(BaseModel):
    count: int
    total: int
    percentage: float


class CoverageScope(BaseModel):
    total: int
    candidates: int
    roster: int


class IdentityCoverage(BaseModel):
    complete: CoverageMetric
    unresolved: CoverageMetric
    resolution_counts: dict[str, int] = Field(default_factory=dict)


class ProductionCoverage(BaseModel):
    recent_supported: CoverageMetric
    recent_missing: CoverageMetric
    recent_stale: CoverageMetric
    season_supported: CoverageMetric
    season_missing: CoverageMetric
    season_stale: CoverageMetric


class ScheduleCoverage(BaseModel):
    supported: CoverageMetric
    unknown: CoverageMetric
    stale: CoverageMetric
    source_incomplete: CoverageMetric


class StatusCoverage(BaseModel):
    explicit: CoverageMetric
    yahoo_blank: CoverageMetric
    stale: CoverageMetric


class RoleCoverage(BaseModel):
    minutes_qualified: CoverageMetric
    usage_supported: CoverageMetric
    game_level_starts_supported: CoverageMetric
    season_starts_supported: CoverageMetric
    insufficient_sample: CoverageMetric
    missing_inputs: CoverageMetric


class AcquisitionCoverage(BaseModel):
    supported: CoverageMetric
    unsupported: CoverageMetric


class CoverageSlice(BaseModel):
    identity: IdentityCoverage
    production: ProductionCoverage
    schedule: ScheduleCoverage
    status: StatusCoverage
    role: RoleCoverage


class PotentialNbaMatch(BaseModel):
    nba_player_id: str
    player_name: str
    team: str | None


class MappingWorklistItem(BaseModel):
    internal_id: int
    yahoo_player_id: str
    yahoo_name: str
    yahoo_team: str | None
    normalized_name: str
    potential_nba_matches: list[PotentialNbaMatch] = Field(default_factory=list)
    conflict_reason: str
    resolution_state: Literal[
        "EXACT_ID",
        "EXACT_NAME_TEAM",
        "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM",
        "TEAM_CHANGE_SUPPORTED",
        "AMBIGUOUS",
        "NO_MATCH",
        "MISSING_MAPPING",
        "NON_NBA_PLAYER",
    ]


RootCause = Literal[
    "RESOLVABLE_INTERNAL_DEFECT",
    "STALE_EXISTING_SOURCE",
    "MISSING_MAPPING",
    "MISSING_EXISTING_SOURCE_FIELD",
    "SOURCE_DOES_NOT_SUPPLY",
    "SOURCE_CONTRACT_UNVERIFIED",
    "REQUIRES_MORE_GAMES",
    "REQUIRES_NEW_SOURCE",
    "INTENTIONALLY_UNSUPPORTED",
]


class WaiverCoverage(BaseModel):
    population: CoverageScope
    pool: CoverageSlice
    candidates: CoverageSlice
    roster: CoverageSlice
    acquisition: AcquisitionCoverage
    mapping_worklist: list[MappingWorklistItem] = Field(default_factory=list)


DataGapCategory = Literal[
    "FIXABLE DATA ISSUE",
    "WAITING FOR MORE GAMES",
    "SOURCE DOES NOT SUPPLY",
    "NEW SOURCE REQUIRED",
    "UNVERIFIED YAHOO CONTEXT",
    "SOURCE CONTRACT UNVERIFIED",
    "INTENTIONALLY UNSUPPORTED",
]


class DataGap(BaseModel):
    category: DataGapCategory
    field: str
    count: int
    total: int
    percentage: float
    reason: str
    root_cause: RootCause


class DropOption(BaseModel):
    player_id: int | None
    player_name: str
    before_score: float | None
    after_score: float | None
    net_improvement: float | None
    component_deltas: Components
    reasons: list[str]
    component_before: Components = Field(default_factory=Components)
    component_after: Components = Field(default_factory=Components)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    starting_slots_before: int | None = None
    starting_slots_after: int | None = None
    starting_slots_required: int | None = None


class Candidate(BaseModel):
    player_id: int
    yahoo_player_id: str
    player_name: str
    position: str | None
    yahoo_team: str | None = None
    nba_team: str | None
    raw_yahoo_status: str | None = None
    yahoo_status: str | None
    identity_mapping_state: Literal[
        "EXACT_ID",
        "EXACT_NAME_TEAM",
        "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM",
        "TEAM_CHANGE_SUPPORTED",
        "AMBIGUOUS",
        "NO_MATCH",
        "MISSING_MAPPING",
        "NON_NBA_PLAYER",
    ] = "MISSING_MAPPING"
    identity_mapping_reason: str = "NBA player identity has not been mapped."
    mapping_diagnostic: Literal[
        "YAHOO_ID_MISSING",
        "NBA_ID_UNMAPPED",
        "NBA_PLAYER_MISSING",
        "TEAM_MAPPING_MISSING",
        "GAME_LOGS_MISSING",
        "SEASON_STATS_MISSING",
        "SCHEDULE_ROWS_MISSING",
        "SCHEDULE_STALE",
        "COMPLETE_MAPPING",
    ] = "NBA_ID_UNMAPPED"
    status_diagnostic: Literal[
        "YAHOO_SUPPLIED_BLANK",
        "STALE_PLAYER_POOL_IMPORT",
        "NORMALIZATION_DEFECT",
        "MISSING_PLAYER_OBSERVATION",
        "MAPPING_ISSUE",
        "UNRECOGNIZED_STATUS",
        "STATUS_PRESENT",
    ] = "MISSING_PLAYER_OBSERVATION"
    availability: Literal["free_agent", "waivers", "unrostered", "rostered", "unknown"]
    eligible: bool
    recent: ValueEvidence
    ros: ValueEvidence
    opportunity: Opportunity
    schedule: Schedule
    components: Components
    overall_score: float | None = None
    effective_weights: dict[str, float] = Field(default_factory=dict)
    recommended_action: Decision
    current_season_games: int = 0
    evidence_quality: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    hold_type: Literal["streamer", "longer_term_hold", "undetermined"]
    best_drop_options: list[DropOption] = Field(default_factory=list)
    net_improvement: float | None = None
    reasons: list[str]
    limitations: list[str]
    data_quality: dict[str, Evidence]
    ranking_value: RankingEvidence = Field(default_factory=RankingEvidence)
    comparison: DropOption | None = None
    roster_decision: Literal["review_replacement", "keep_on_measured_model", "unavailable"] = "unavailable"


class WaiverBoard(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None = None
    mode: Mode
    generated_at: datetime
    model_version: str = "waiver-evidence-phase3"
    weights: dict[str, float]
    best_overall_available_id: int | None
    best_add_for_team_id: int | None
    team_needs: list[str]
    candidates: list[Candidate]
    excluded_count: int
    unknown_availability_count: int
    limitations: list[str]
    data_quality: dict[str, Evidence]
    coverage: WaiverCoverage
    data_gaps: list[DataGap] = Field(default_factory=list)
    roster: list[Candidate] = Field(default_factory=list)
    selected_drop_player_id: int | None = None
    top_measured_candidate_id: int | None = None
    waiver_rules: list[str] = Field(default_factory=list)
    selected_player_result: str = "INSUFFICIENT EVIDENCE"


class WaiverImpact(BaseModel):
    league_key: str
    team_key: str
    mode: Mode
    model_version: str = "waiver-evidence-phase3"
    candidate: Candidate
    comparison: DropOption | None
    limitations: list[str]


class SwapAnalysis(BaseModel):
    add_player: Candidate
    drop_player: Candidate
    mode: Mode
    decision: Decision
    comparison: DropOption
    reasons: list[str]
    limitations: list[str]


class AcquisitionContext(BaseModel):
    rules: list[str]
    data_quality: Evidence
    current_priority: int | None = None
    weekly_adds_used: int | None = None
    weekly_adds_remaining: int | None = None
    claim_clear_at: datetime | None = None
    detail: str = "Current priority, weekly usage and exact claim-clear time are unverified; acquisition value does not affect ranking."


class TransactionAnalysis(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None = None
    mode: Mode
    generated_at: datetime
    model_version: str = "waiver-evidence-phase3"
    decision: Literal["MUST ADD", "ADD", "STREAM", "HOLD"]
    decision_reasons: list[str] = Field(default_factory=list)
    best_transaction: SwapAnalysis | None
    top_supported_transactions: list[SwapAnalysis]
    watch_transactions: list[SwapAnalysis]
    evaluated_pair_count: int
    supported_pair_count: int
    watch_pair_count: int
    excluded_pair_count: int
    excluded_pair_reasons: dict[str, int]
    data_quality: dict[str, Evidence]
    acquisition_context: AcquisitionContext
    limitations: list[str]

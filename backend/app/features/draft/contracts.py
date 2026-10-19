from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DraftMetricsResult(BaseModel):
    league_key: str
    season: str
    players_scored: int
    players_missing_nba_mapping: int
    players_missing_stats: int


class DraftUtilityRequest(BaseModel):
    league_key: str
    team_key: str
    season: str
    drafted_player_ids: list[int] = Field(max_length=1500)
    available_player_ids: list[int] = Field(min_length=1, max_length=1500)
    draft_position: int | None = Field(default=None, ge=1, le=30, description="Manager's fixed snake-draft slot, 1-based")
    round_number: int | None = Field(default=None, ge=1, le=100, description="Current round, 1-based")
    total_teams: int | None = Field(default=None, ge=2, le=30)
    recent_pick_player_ids: list[int] = Field(default_factory=list, max_length=30)
    adp_by_player_id: dict[int, float] = Field(default_factory=dict, max_length=1500)
    mode: Literal["balanced", "upside", "safe"] = "balanced"


class DraftTiming(BaseModel):
    draft_position: int
    round_number: int
    total_teams: int
    current_pick_number: int
    picks_until_next_turn: int
    next_pick_number: int


class DraftRun(BaseModel):
    position_group: Literal["center", "guard", "forward"]
    recent_pick_count: int
    window_size: int
    active: bool


class DraftPlayerAvailability(BaseModel):
    player_identity_id: int
    adp: float | None
    market_value_delta: float | None
    reach_score: float | None
    fall_score: float | None
    draft_rank: int | None
    draft_frequency: float | None
    adp_source: str | None
    positional_scarcity: float | None
    availability_score: float | None
    next_pick_survival_probability: float | None
    miss_risk_score: float | None
    expected_loss_if_gone: float | None = None
    opportunity_cost_if_wait: float | None = None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"]
    data_freshness: Literal["unknown", "fresh", "stale", "request"]
    market_data_as_of: datetime | None = None
    draft_now: bool | None
    safe_to_wait: bool | None
    decision_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    explanation: str
    blocker: str | None


class DraftWaitFallback(BaseModel):
    player_identity_id: int
    player_name: str
    utility_score: float
    survival_probability: float
    probability_selected_if_waiting: float


class DraftUtilityPick(BaseModel):
    yahoo_status: str | None = None
    yahoo_status_label: str | None = None
    recommendation_eligibility: Literal["excluded", "uncertain", "unknown"] = "unknown"
    yahoo_status_reason: str | None = None
    yahoo_status_as_of: datetime | None = None
    player_identity_id: int
    yahoo_player_id: str
    nba_player_id: str
    player_name: str
    positions: list[str]
    fantasy_value: float
    replacement_value: float
    positional_scarcity: float
    durability_score: float
    risk_score: float
    upside_score: float
    positional_need_score: float
    roster_construction_score: float
    utility_score: float
    mode_adjusted_utility_score: float
    wait_utility_now: float
    adp: float | None
    market_value_delta: float | None
    reach_score: float | None
    fall_score: float | None
    miss_risk_score: float | None
    expected_loss_if_gone: float | None
    opportunity_cost_if_wait: float | None
    expected_fallback_utility: float | None
    expected_wait_utility: float | None
    expected_wait_cost: float | None
    wait_fallbacks: list[DraftWaitFallback]
    decision_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    wait_cost_method: Literal["independent_heuristic", "unavailable"]
    draft_rank: int | None
    draft_frequency: float | None
    adp_source: str | None
    availability_score: float | None
    next_pick_survival_probability: float | None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"]
    data_freshness: Literal["unknown", "fresh", "stale", "request"]
    draft_now: bool | None
    safe_to_wait: bool | None
    run_bonus: float
    reasons: list[str]


class DraftRosterImpact(BaseModel):
    rank_without_roster: int
    rank_with_roster: int
    score_without_roster: float
    score_change: float
    need_without_roster: float
    need_with_roster: float
    construction_without_roster: float
    construction_with_roster: float
    need_score_change: float
    scarcity_need_score_change: float
    construction_score_change: float


class DraftBoardPlayer(BaseModel):
    yahoo_status: str | None = None
    yahoo_status_label: str | None = None
    recommendation_eligibility: Literal["excluded", "uncertain", "unknown"] = "unknown"
    yahoo_status_reason: str | None = None
    yahoo_status_as_of: datetime | None = None
    player_identity_id: int
    player_name: str
    positions: list[str]
    decision_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_score: float | None
    value_score: float | None
    roster_impact: DraftRosterImpact | None = None
    adp: float | None = None
    adp_source: str | None = None
    market_data_as_of: datetime | None = None
    market_value_delta: float | None = None
    survival_probability: float | None
    miss_risk_score: float | None = None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"] = "unknown"
    data_freshness: Literal["unknown", "fresh", "stale", "request"] = "unknown"
    expected_wait_cost: float | None
    target_status: Literal["target", "priority", "watch", "avoid"] | None = None
    data_quality: dict[str, Literal[
        "available", "estimated", "heuristic", "stale", "unknown", "insufficient_evidence"
    ]]


class DraftUtilityResult(BaseModel):
    roster_fit_version: int = 1
    league_key: str
    team_key: str
    season: str
    drafted_count: int
    available_count: int
    mode: Literal["balanced", "upside", "safe"]
    primary_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    draft_timing: DraftTiming | None
    draft_runs: list[DraftRun]
    player_availability: list[DraftPlayerAvailability]
    ranked_players: list[DraftBoardPlayer] = Field(default_factory=list)
    best_pick: DraftUtilityPick | None
    best_value_before_next_pick: DraftUtilityPick | None
    adp_missing_available_player_ids: list[int]
    unscored_available_player_ids: list[int]


class DraftSessionCreateRequest(BaseModel):
    league_key: str
    season: str = Field(pattern=r"^\d{4}-\d{2}$")
    manager_team_key: str
    draft_position: int = Field(ge=1, le=30)
    total_teams: int = Field(ge=2, le=30)
    rounds: int = Field(ge=1, le=100)
    team_slots: dict[str, int] = Field(min_length=2, max_length=30)
    mode: Literal["balanced", "upside", "safe"] = "balanced"

    @model_validator(mode="after")
    def validate_team_slots(self) -> "DraftSessionCreateRequest":
        if self.team_slots is None:
            return self
        if len(self.team_slots) != self.total_teams:
            raise ValueError("team_slots must include every league team exactly once")
        slots = list(self.team_slots.values())
        if sorted(slots) != list(range(1, self.total_teams + 1)):
            raise ValueError("team_slots must map teams to unique 1-based draft slots")
        if self.team_slots.get(self.manager_team_key) != self.draft_position:
            raise ValueError("manager_team_key must map to draft_position")
        return self


class DraftLiveSessionCreateRequest(BaseModel):
    league_key: str
    season: str = Field(pattern=r"^\d{4}-\d{2}$")
    manager_team_key: str
    draft_position: int | None = Field(default=None, ge=1, le=30)
    total_teams: int = Field(ge=2, le=30)
    rounds: int = Field(ge=1, le=100)
    team_slots: dict[str, int] = Field(default_factory=dict, max_length=30)
    mode: Literal["balanced", "upside", "safe"] = "balanced"

    @model_validator(mode="after")
    def validate_partial_team_slots(self) -> "DraftLiveSessionCreateRequest":
        slots = list(self.team_slots.values())
        if any(not 1 <= slot <= self.total_teams for slot in slots):
            raise ValueError("team_slots must use positions within the league")
        if len(slots) != len(set(slots)):
            raise ValueError("team_slots must map unique teams to unique positions")
        manager_position = self.team_slots.get(self.manager_team_key)
        if manager_position is not None and self.draft_position != manager_position:
            raise ValueError("manager_team_key must map to draft_position")
        return self


class DraftMockCreateRequest(DraftSessionCreateRequest):
    team_slots: dict[str, int] | None = Field(default=None, min_length=2, max_length=30)
    aggressiveness: float = Field(default=0.5, ge=0.0, le=1.0)
    seed: int | None = Field(default=None, ge=0, le=9223372036854775807)
    opponent_order_seed: int | None = Field(default=None, ge=0, le=9223372036854775807)
    reuse_same_opponent_order: bool = False
    pick_timer_seconds: int | None = Field(default=None, ge=5, le=600)
    practice_speed: Literal["realistic", "fast", "instant_until_my_turn"] = "realistic"
    auto_pick_enabled: bool = True
    auto_pick_policy: Literal[
        "recommended", "highest_decision_score", "best_value", "highest_priority_target"
    ] = "recommended"
    live_sync_rehearsal: bool = False


class DraftMockBatchCreateRequest(DraftMockCreateRequest):
    count: int = Field(ge=1, le=500)
    reuse_same_opponent_order: bool = False


class DraftMockOrderRequest(BaseModel):
    league_key: str
    manager_team_key: str
    draft_position: int = Field(ge=1, le=30)
    total_teams: int = Field(ge=2, le=30)
    seed: int = Field(ge=0, le=9223372036854775807)
    team_slots: dict[str, int] | None = Field(default=None, min_length=2, max_length=30)


class DraftMockOrderResponse(BaseModel):
    league_key: str
    draft_position: int
    team_slots: dict[str, int]
    order_seed: int
    reused_advanced_mapping: bool = False


class DraftOrderUpdateRequest(BaseModel):
    expected_version: int = Field(ge=0)
    draft_position: int | None = Field(default=None, ge=1, le=30)
    team_slots: dict[str, int] = Field(default_factory=dict, max_length=30)
    replace_mapping: bool = False
    clear_manager_position: bool = False

    @model_validator(mode="after")
    def validate_manager_position_update(self) -> "DraftOrderUpdateRequest":
        if self.clear_manager_position and self.draft_position is not None:
            raise ValueError("draft_position cannot be set when clear_manager_position is true")
        return self


class DraftMockActionRequest(BaseModel):
    action: Literal["next_pick", "until_my_turn"]


class DraftSyncStateView(BaseModel):
    session_id: str
    source_type: Literal["yahoo_draftresults", "mock_yahoo_snapshot"]
    enabled: bool
    paused: bool
    status: Literal[
        "synced", "source_empty", "source_unavailable", "source_lagging",
        "local_ahead", "conflict", "authentication_required", "malformed_source",
        "paused", "completed",
    ]
    last_retrieved_at: datetime | None
    last_successful_retrieval_at: datetime | None
    source_confirmed_through: int
    local_recorded_through: int
    consecutive_failures: int
    conflict_overall_pick: int | None
    conflict_evidence: dict[str, Any]
    mock_mode: Literal["normal", "fast", "step"] | None = None
    mock_outage: bool | None = None
    mock_hold_delivery: bool | None = None


class DraftSyncResult(BaseModel):
    sync: DraftSyncStateView
    accepted_picks: list[int] = Field(default_factory=list)
    confirmed_picks: list[int] = Field(default_factory=list)
    changed: bool = False


class DraftMockRehearsalActionRequest(BaseModel):
    action: Literal[
        "normal", "fast", "step_one_pick", "deliver_next_snapshot", "pause_source",
        "resume_source", "simulate_source_lag", "release_delayed_picks",
        "simulate_duplicate_snapshot", "simulate_multiple_picks_together",
        "simulate_source_outage", "recover_source", "simulate_local_ahead_confirmation",
        "simulate_pick_conflict", "resolve_with_yahoo", "keep_local_and_pause",
        "undo_latest_local", "simulate_malformed_source", "simulate_unknown_player",
        "reset_rehearsal",
    ]


class DraftPickUpdateRequest(BaseModel):
    selected_player_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    source: str = Field(default="manual", min_length=1, max_length=80)
    picked_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_picked_at(self) -> "DraftPickUpdateRequest":
        if self.picked_at is not None and self.picked_at.tzinfo is None:
            raise ValueError("picked_at must include a timezone")
        return self


class DraftPickUndoRequest(BaseModel):
    expected_version: int = Field(ge=0)
    source: str = Field(default="manual", min_length=1, max_length=80)
    evidence: dict[str, Any] = Field(default_factory=dict)


class DraftTargetRequest(BaseModel):
    status: Literal["target", "priority", "watch", "avoid"]
    expected_version: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=2000)


class DraftPickView(BaseModel):
    overall_pick: int
    round_number: int
    team_slot: int
    team_key: str | None
    selected_player_id: int | None
    source: str
    picked_at: str | None
    selection_basis: str | None = None
    selection_source: str | None = None


class DraftTargetView(BaseModel):
    player_id: int
    status: Literal["target", "priority", "watch", "avoid"]
    note: str | None


class DraftSessionTiming(BaseModel):
    current_pick: int | None
    next_pick: int | None
    current_round: int | None
    next_round: int | None
    picks_until_next: int | None
    your_turn: bool | None
    current_team_key: str | None = None


class DraftSessionState(BaseModel):
    session_id: str
    league_key: str
    season: str
    manager_team_key: str
    draft_position: int | None
    total_teams: int
    rounds: int
    team_slots: dict[str, int]
    draft_order_status: Literal["unresolved", "partial", "confirmed", "conflict"]
    draft_order_evidence: dict[str, Any]
    status: Literal["active", "paused", "completed"]
    session_type: Literal["mock", "live"]
    draft_source: Literal["manual", "internal_mock", "yahoo_live"] = "manual"
    sync_enabled: bool = False
    browser_practice: bool = False
    mock_aggressiveness: float | None = None
    mock_seed: int | None = None
    mock_batch_id: str | None = None
    mock_run_index: int | None = None
    mock_attempt_index: int | None = None
    mock_generated_team_slots: dict[str, int] | None = None
    mock_opponent_order_seed: int | None = None
    mock_run_status: Literal["queued", "running", "paused", "awaiting_manager", "completed", "failed", "canceled"] | None = None
    mock_evaluation: dict[str, Any] | None = None
    pick_deadline_at: datetime | None = None
    pick_timer_seconds: int | None = None
    pick_timer_source: Literal["yahoo", "practice", "not_applicable"] | None = None
    auto_pick_enabled: bool | None = None
    auto_pick_policy: Literal[
        "recommended", "highest_decision_score", "best_value", "highest_priority_target"
    ] | None = None
    practice_speed: Literal["realistic", "fast", "instant_until_my_turn"] | None = None
    archived_at: datetime | None = None
    mode: Literal["balanced", "upside", "safe"]
    version: int
    next_overall_pick: int
    timing: DraftSessionTiming
    picks: list[DraftPickView]
    targets: list[DraftTargetView]
    latest_recommendation: dict[str, Any] | None
    recommendation_version: int | None


class DraftMockRunRef(BaseModel):
    session_id: str
    run_index: int | None
    attempt_index: int
    status: Literal["active", "paused", "completed"]
    worker_status: Literal["queued", "running", "paused", "awaiting_manager", "completed", "failed", "canceled"]


class DraftMockBatchState(BaseModel):
    batch_id: str
    league_key: str
    manager_team_key: str
    requested_runs: int
    completed_runs: int
    paused_runs: int
    active_runs: int
    failed_runs: int
    queued_runs: int = 0
    running_runs: int = 0
    canceled_runs: int = 0
    aggressiveness: float
    seed: int
    status: Literal["queued", "running", "paused", "completed", "failed", "canceled"]
    created_at: str
    session_ids: list[str]
    runs: list[DraftMockRunRef]


class DraftMockRunOrderPreview(BaseModel):
    league_key: str
    manager_team_key: str
    draft_position: int
    order_seed: int
    team_slots: dict[str, int]
    reused_advanced_mapping: bool


class DraftMockHistoryItem(BaseModel):
    kind: Literal["session", "batch"]
    object_id: str
    league_key: str
    manager_team_key: str
    name: str
    status: str
    created_at: str
    archived_at: datetime | None
    run_count: int
    session_id: str | None = None
    batch_id: str | None = None


class DraftMockHistoryResponse(BaseModel):
    active_practice: list[DraftMockHistoryItem]
    completed_practice: list[DraftMockHistoryItem]
    running_batches: list[DraftMockHistoryItem]
    completed_batches: list[DraftMockHistoryItem]
    archived: list[DraftMockHistoryItem]


class DraftMockHistorySelection(BaseModel):
    kind: Literal["session", "batch"]
    object_id: str


class DraftMockBulkLifecycleRequest(BaseModel):
    items: list[DraftMockHistorySelection] = Field(min_length=1, max_length=500)
    queued_runs: int = 0
    running_runs: int = 0
    canceled_runs: int = 0


class DraftMockBatchCreateResult(BaseModel):
    batch: DraftMockBatchState
    session_ids: list[str]


class DraftMockActionResult(BaseModel):
    state: DraftSessionState
    event: Literal["pick_simulated", "manager_turn", "draft_complete", "paused", "resumed"]
    simulated_picks: int


class DraftMockBatchRunResult(BaseModel):
    batch: DraftMockBatchState


class DraftMockBatchActionRequest(BaseModel):
    action: Literal["pause", "resume", "cancel", "retry_failed"]


class DraftRecommendationView(BaseModel):
    action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_score: float | None
    confidence: Literal["low", "medium", "high", "unavailable"]
    recommended_player: DraftUtilityPick | None
    best_value_at_risk: DraftUtilityPick | None = None
    survival_probability: float | None
    expected_wait_cost: float | None
    wait_analysis: list[DraftWaitFallback]
    alternatives: list[DraftWaitFallback]
    reasons: list[str]
    warnings: list[str]
    data_quality: dict[str, Literal[
        "available", "estimated", "heuristic", "stale", "unknown", "insufficient_evidence"
    ]]


class DraftRosterPlayer(BaseModel):
    player_identity_id: int
    player_name: str
    positions: list[str]
    roster_slot: str | None


class DraftRosterSlot(BaseModel):
    position: str
    player: DraftRosterPlayer | None


class DraftRosterView(BaseModel):
    filled_count: int
    open_count: int
    slots: list[DraftRosterSlot]
    drafted_players: list[DraftRosterPlayer]


class DraftBoardView(BaseModel):
    session: DraftSessionState
    recommendation: DraftRecommendationView | None
    players: list[DraftBoardPlayer]
    roster: DraftRosterView


class DraftReplayResponse(BaseModel):
    session_id: str
    session_version: int
    total_versions: int
    session: DraftSessionState
    board: DraftBoardView | None


class DraftSessionEventResult(BaseModel):
    state: DraftSessionState
    event: Literal["created", "recorded", "corrected", "undone", "unchanged"]

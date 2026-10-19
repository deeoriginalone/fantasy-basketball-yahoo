export type DraftMode = "balanced" | "upside" | "safe";
export type TargetStatus = "target" | "priority" | "watch" | "avoid";
export type DecisionAction = "draft_now" | "wait" | "insufficient_evidence";

export interface LeagueTeam {
  team_key: string;
  team_name: string | null;
}

export interface League {
  league_key: string;
  league_name: string;
  season: number | null;
  roster_positions: Array<{ position: string; count: number; is_starting_position?: number }>;
  teams: LeagueTeam[];
}

export interface DraftPick {
  overall_pick: number;
  round_number: number;
  team_slot: number;
  team_key: string | null;
  selected_player_id: number | null;
  source: string;
  picked_at: string | null;
  selection_basis: string | null;
  selection_source: string | null;
}

export interface DraftTarget {
  player_id: number;
  status: TargetStatus;
  note: string | null;
}

export interface DraftSession {
  session_id: string;
  league_key: string;
  season: string;
  manager_team_key: string;
  draft_position: number | null;
  total_teams: number;
  rounds: number;
  team_slots: Record<string, number>;
  draft_order_status: "unresolved" | "partial" | "confirmed" | "conflict";
  draft_order_evidence: Record<string, unknown>;
  status: "active" | "paused" | "completed";
  session_type: "mock" | "live";
  draft_source: "manual" | "internal_mock" | "yahoo_live";
  sync_enabled: boolean;
  browser_practice?: boolean;
  mock_aggressiveness: number | null;
  mock_seed: number | null;
  mock_batch_id: string | null;
  mock_run_index: number | null;
  mock_attempt_index: number | null;
  mock_run_status: "queued" | "running" | "paused" | "completed" | "failed" | null;
  mock_evaluation: MockEvaluation | null;
  mode: DraftMode;
  version: number;
  next_overall_pick: number;
  timing: {
    current_pick: number | null;
    next_pick: number | null;
    current_round: number | null;
    next_round: number | null;
    picks_until_next: number | null;
    your_turn: boolean | null;
    current_team_key: string | null;
  };
  picks: DraftPick[];
  targets: DraftTarget[];
  latest_recommendation: Record<string, unknown> | null;
  recommendation_version: number | null;
}

export interface MockOrderPreview {
  league_key: string;
  draft_position: number;
  team_slots: Record<string, number>;
  order_seed: number;
  reused_advanced_mapping: boolean;
}

export interface DraftSyncState {
  session_id: string;
  source_type: "yahoo_draftresults" | "mock_yahoo_snapshot";
  enabled: boolean;
  paused: boolean;
  status: "synced" | "source_empty" | "source_unavailable" | "source_lagging"
    | "local_ahead" | "conflict" | "authentication_required" | "malformed_source"
    | "paused" | "completed";
  last_retrieved_at: string | null;
  last_successful_retrieval_at: string | null;
  source_confirmed_through: number;
  local_recorded_through: number;
  consecutive_failures: number;
  conflict_overall_pick: number | null;
  conflict_evidence: Record<string, unknown>;
  mock_mode: "normal" | "fast" | "step" | null;
  mock_outage: boolean | null;
  mock_hold_delivery: boolean | null;
}

export interface DraftSyncResult {
  sync: DraftSyncState;
  accepted_picks: number[];
  confirmed_picks: number[];
  changed: boolean;
}

export interface MockEvaluation {
  manager_decision_count: number;
  recommendations: Array<{
    overall_pick: number;
    recommended_player_id: number | null;
    selected_player_id: number | null;
    decision: DecisionAction | null;
    predicted_survival_probability: number | null;
    expected_wait_cost: number | null;
    selection_basis: string | null;
  }>;
  players_drafted: Array<{
    overall_pick: number;
    team_slot: number;
    player_id: number | null;
  }>;
  survival_outcomes: Array<{
    overall_pick: number;
    player_id: number;
    predicted_probability: number | null;
    survived_to_next_manager_turn: boolean | null;
    survived_to_end: boolean | null;
    outcome: string;
  }>;
  wait_cost_outcomes: Array<{
    overall_pick: number;
    player_id: number;
    predicted_wait_cost: number | null;
    realized_wait_cost: number | null;
    outcome: string;
  }>;
}

export interface DraftMockBatch {
  batch_id: string;
  league_key: string;
  manager_team_key: string;
  requested_runs: number;
  completed_runs: number;
  paused_runs: number;
  active_runs: number;
  failed_runs: number;
  aggressiveness: number;
  seed: number;
  status: "queued" | "running" | "paused" | "completed" | "failed";
  created_at: string;
  session_ids: string[];
  runs: Array<{
    session_id: string;
    run_index: number | null;
    attempt_index: number;
    status: "active" | "paused" | "completed";
    worker_status: "queued" | "running" | "paused" | "completed" | "failed";
  }>;
}

export interface DraftReplay {
  session_id: string;
  session_version: number;
  total_versions: number;
  session: DraftSession;
  board: DraftBoard | null;
}

export interface YahooStatusEvidence {
  yahoo_status?: string | null;
  yahoo_status_label?: string | null;
  recommendation_eligibility?: "excluded" | "uncertain" | "unknown";
  yahoo_status_reason?: string | null;
  yahoo_status_as_of?: string | null;
}

export interface UtilityPick extends YahooStatusEvidence {
  player_identity_id: number;
  player_name: string;
  positions: string[];
  fantasy_value: number;
  utility_score: number;
  mode_adjusted_utility_score: number;
  next_pick_survival_probability: number | null;
  survival_confidence: "unknown" | "heuristic_unvalidated";
  expected_wait_cost: number | null;
  decision_action: DecisionAction;
  decision_confidence: "low" | "medium" | "high" | "unavailable";
  data_freshness: "unknown" | "fresh" | "stale" | "request";
  reasons: string[];
  wait_fallbacks: Array<{
    player_identity_id: number;
    player_name: string;
    utility_score: number;
    survival_probability: number;
    probability_selected_if_waiting: number;
  }>;
}

export interface RosterImpact {
  rank_without_roster: number;
  rank_with_roster: number;
  score_without_roster: number;
  score_change: number;
  need_without_roster: number;
  need_with_roster: number;
  construction_without_roster: number;
  construction_with_roster: number;
  need_score_change: number;
  scarcity_need_score_change: number;
  construction_score_change: number;
}

export interface BoardPlayer extends YahooStatusEvidence {
  player_identity_id: number;
  player_name: string;
  positions: string[];
  utility: UtilityPick | null;
  decision_action: DecisionAction;
  decision_score: number | null;
  value_score: number | null;
  roster_impact?: RosterImpact | null;
  adp: number | null;
  adp_source: string | null;
  market_data_as_of?: string | null;
  market_value_delta: number | null;
  survival_probability: number | null;
  miss_risk_score: number | null;
  survival_confidence: "unknown" | "heuristic_unvalidated";
  data_freshness: "unknown" | "fresh" | "stale" | "request";
  expected_wait_cost: number | null;
  target_status: TargetStatus | null;
  data_quality: Record<string, string>;
}

export interface Recommendation {
  action: DecisionAction;
  decision_score: number | null;
  confidence: "low" | "medium" | "high" | "unavailable";
  recommended_player: UtilityPick | null;
  best_value_at_risk: UtilityPick | null;
  survival_probability: number | null;
  expected_wait_cost: number | null;
  wait_analysis: UtilityPick["wait_fallbacks"];
  alternatives: UtilityPick["wait_fallbacks"];
  reasons: string[];
  warnings: string[];
  data_quality: Record<string, string>;
}

export interface RosterPlayer {
  player_identity_id: number;
  player_name: string;
  positions: string[];
  roster_slot: string | null;
}

export interface DraftBoard {
  session: DraftSession;
  recommendation: Recommendation | null;
  players: BoardPlayer[];
  roster: {
    filled_count: number;
    open_count: number;
    slots: Array<{ position: string; player: RosterPlayer | null }>;
    drafted_players: RosterPlayer[];
  };
}

export interface PlayerIdentity {
  id: number;
  player_name: string;
  position: string | null;
  team: string | null;
}
export type WaiverMode = "this_week" | "next_7_days" | "ros";
export type WaiverSampleLabel = "EXCELLENT" | "GOOD" | "LIMITED" | "VERY LIMITED" | "INSUFFICIENT FOR STRONG RECOMMENDATION" | "NO CURRENT-SEASON EVIDENCE";

export interface WaiverEvidence {
  state: "available" | "partial" | "missing" | "stale" | "unknown" | "unsupported" | "unavailable";
  source: string;
  as_of: string | null;
  detail: string;
  sample_count?: number | null;
}

export interface RoleWindow {
  average: number | null;
  median: number | null;
  games: number;
  game_ids: string[];
  window_start: string | null;
  window_end: string | null;
  as_of: string | null;
  missing_game_ids: string[];
  stale_game_ids: string[];
}

export interface RoleMetric {
  quality: WaiverEvidence;
  recent: RoleWindow;
  comparison: RoleWindow;
  delta: number | null;
  median_delta: number | null;
  unit: string;
}

export interface CurrentRole {
  minutes: RoleMetric;
  usage: RoleMetric;
  starts: {
    quality: WaiverEvidence;
    season: string | null;
    season_starts: number | null;
    season_games: number | null;
    recent_starts: number | null;
    detail: string;
  };
  quality: WaiverEvidence;
  trend: "RISING" | "STABLE" | "FALLING" | "INSUFFICIENT EVIDENCE";
  season_usage: number | null;
  season_usage_quality: WaiverEvidence;
  method: string;
  limitations: string[];
}

export interface WaiverComponents {
  roster_fit: number | null;
  player_value: number | null;
  opportunity: number | null;
  schedule: number | null;
  acquisition_value: number | null;
}

export interface CoverageMetric {
  count: number;
  total: number;
  percentage: number;
}

export interface MappingWorklistItem {
  internal_id: number;
  yahoo_player_id: string;
  yahoo_name: string;
  yahoo_team: string | null;
  normalized_name: string;
  potential_nba_matches: { nba_player_id: string; player_name: string; team: string | null }[];
  conflict_reason: string;
  resolution_state: "EXACT_ID" | "EXACT_NAME_TEAM" | "NORMALIZED_NAME_TEAM" | "KNOWN_ALIAS_TEAM" | "TEAM_CHANGE_SUPPORTED" | "AMBIGUOUS" | "NO_MATCH" | "MISSING_MAPPING" | "NON_NBA_PLAYER";
}

export interface CoverageSlice {
  identity: { complete: CoverageMetric; unresolved: CoverageMetric; resolution_counts: Record<string, number> };
  production: {
    recent_supported: CoverageMetric;
    recent_missing: CoverageMetric;
    recent_stale: CoverageMetric;
    season_supported: CoverageMetric;
    season_missing: CoverageMetric;
    season_stale: CoverageMetric;
  };
  schedule: {
    supported: CoverageMetric;
    unknown: CoverageMetric;
    stale: CoverageMetric;
    source_incomplete: CoverageMetric;
  };
  status: { explicit: CoverageMetric; yahoo_blank: CoverageMetric; stale: CoverageMetric };
  role: {
    minutes_qualified: CoverageMetric;
    usage_supported: CoverageMetric;
    game_level_starts_supported: CoverageMetric;
    season_starts_supported: CoverageMetric;
    insufficient_sample: CoverageMetric;
    missing_inputs: CoverageMetric;
  };
}

export interface WaiverCoverage {
  population: { total: number; candidates: number; roster: number };
  pool: CoverageSlice;
  candidates: CoverageSlice;
  roster: CoverageSlice;
  acquisition: { supported: CoverageMetric; unsupported: CoverageMetric };
  mapping_worklist: MappingWorklistItem[];
}

export interface WaiverDataGap {
  category: "FIXABLE DATA ISSUE" | "WAITING FOR MORE GAMES" | "SOURCE DOES NOT SUPPLY" | "NEW SOURCE REQUIRED" | "UNVERIFIED YAHOO CONTEXT" | "SOURCE CONTRACT UNVERIFIED" | "INTENTIONALLY UNSUPPORTED";
  field: string;
  count: number;
  total: number;
  percentage: number;
  reason: string;
  root_cause: "RESOLVABLE_INTERNAL_DEFECT" | "STALE_EXISTING_SOURCE" | "MISSING_MAPPING" | "MISSING_EXISTING_SOURCE_FIELD" | "SOURCE_DOES_NOT_SUPPLY" | "SOURCE_CONTRACT_UNVERIFIED" | "REQUIRES_MORE_GAMES" | "REQUIRES_NEW_SOURCE" | "INTENTIONALLY_UNSUPPORTED";
}

export interface WaiverDrop {
  player_id: number | null;
  player_name: string;
  before_score: number | null;
  after_score: number | null;
  net_improvement: number | null;
  component_before: WaiverComponents;
  component_after: WaiverComponents;
  effective_weights: Record<string, number>;
  starting_slots_before: number | null;
  starting_slots_after: number | null;
  starting_slots_required: number | null;
  component_deltas: WaiverComponents;
  reasons: string[];
}

export interface WaiverCandidate {
  player_id: number;
  yahoo_player_id: string;
  player_name: string;
  position: string | null;
  yahoo_team: string | null;
  nba_team: string | null;
  raw_yahoo_status: string | null;
  yahoo_status: string | null;
  identity_mapping_state: MappingWorklistItem["resolution_state"];
  identity_mapping_reason: string;
  mapping_diagnostic: "YAHOO_ID_MISSING" | "NBA_ID_UNMAPPED" | "NBA_PLAYER_MISSING" | "TEAM_MAPPING_MISSING" | "GAME_LOGS_MISSING" | "SEASON_STATS_MISSING" | "SCHEDULE_ROWS_MISSING" | "SCHEDULE_STALE" | "COMPLETE_MAPPING";
  status_diagnostic: "YAHOO_SUPPLIED_BLANK" | "STALE_PLAYER_POOL_IMPORT" | "NORMALIZATION_DEFECT" | "MISSING_PLAYER_OBSERVATION" | "MAPPING_ISSUE" | "UNRECOGNIZED_STATUS" | "STATUS_PRESENT";
  availability: "free_agent" | "waivers" | "unrostered" | "rostered" | "unknown";
  eligible: boolean;
  recent: {
    value: number | null;
    games: number;
    season: string | null;
    label: string;
    sample_label: WaiverSampleLabel;
    per_game_stats: Record<string, number>;
    scoring_weights: Record<string, number>;
    scoring_contributions: Record<string, number>;
  };
  ros: {
    value: number | null;
    games: number;
    season: string | null;
    label: string;
    sample_label: WaiverSampleLabel;
    per_game_stats: Record<string, number>;
    scoring_weights: Record<string, number>;
    scoring_contributions: Record<string, number>;
  };
  ranking_value: {
    value: number | null;
    recent_weight: number | null;
    historical_value: number | null;
    historical_games: number;
    historical_season: string | null;
    label: string;
  };
  opportunity: {
    minutes: number | null;
    minutes_trend: number | null;
    usage_trend: number | null;
    historical_start_rate: number | null;
    role: string;
    score: number | null;
    score_parts: Record<string, number>;
    current_role: CurrentRole | null;
  };
  schedule: {
    games_remaining: number | null;
    off_day_games: number | null;
    back_to_backs: number | null;
    next_7_days_games: number | null;
    opponents: string[];
    source_row_count: number;
    window_start: string;
    window_end: string;
    imported_at: string | null;
    freshness: "fresh" | "stale" | "unknown";
    coverage: "COMPLETE" | "PARTIAL" | "UNKNOWN" | "STALE";
    diagnostic_reason: "NBA_ID_UNMAPPED" | "TEAM_MAPPING_MISSING" | "NO_PLAYER_SCHEDULE_ROWS" | "NO_GAMES_IN_WINDOW" | "SCHEDULE_STALE" | "SCHEDULE_ROWS_PRESENT" | "SCHEDULE_SOURCE_INCOMPLETE";
  };
  components: WaiverComponents;
  overall_score: number | null;
  effective_weights: Record<string, number>;
  recommended_action: "MUST ADD" | "ADD" | "STREAM" | "WATCH" | "PASS" | "INSUFFICIENT EVIDENCE";
  current_season_games: number;
  evidence_quality: WaiverSampleLabel;
  hold_type: "streamer" | "longer_term_hold" | "undetermined";
  comparison: WaiverDrop | null;
  best_drop_options: WaiverDrop[];
  net_improvement: number | null;
  roster_decision: "review_replacement" | "keep_on_measured_model" | "unavailable";
  reasons: string[];
  limitations: string[];
  data_quality: Record<string, WaiverEvidence>;
}

export interface WaiverBoard {
  league_key: string;
  team_key: string;
  team_name: string | null;
  mode: WaiverMode;
  generated_at: string;
  model_version: string;
  weights: Record<string, number>;
  best_overall_available_id: number | null;
  best_add_for_team_id: number | null;
  team_needs: string[];
  roster: WaiverCandidate[];
  selected_drop_player_id: number | null;
  top_measured_candidate_id: number | null;
  waiver_rules: string[];
  selected_player_result: string;
  candidates: WaiverCandidate[];
  excluded_count: number;
  unknown_availability_count: number;
  limitations: string[];
  data_quality: Record<string, WaiverEvidence>;
  coverage: WaiverCoverage;
  data_gaps: WaiverDataGap[];
}

export interface WaiverImpact {
  league_key: string;
  team_key: string;
  mode: WaiverMode;
  model_version: string;
  candidate: WaiverCandidate;
  comparison: WaiverDrop | null;
  limitations: string[];
}

export interface SwapAnalysis {
  add_player: WaiverCandidate;
  drop_player: WaiverCandidate;
  mode: WaiverMode;
  decision: WaiverCandidate["recommended_action"];
  comparison: WaiverDrop;
  reasons: string[];
  limitations: string[];
}

export interface TransactionAnalysis {
  league_key: string;
  team_key: string;
  team_name: string | null;
  mode: WaiverMode;
  generated_at: string;
  model_version: string;
  decision: "MUST ADD" | "ADD" | "STREAM" | "HOLD";
  decision_reasons: string[];
  best_transaction: SwapAnalysis | null;
  top_supported_transactions: SwapAnalysis[];
  watch_transactions: SwapAnalysis[];
  evaluated_pair_count: number;
  supported_pair_count: number;
  watch_pair_count: number;
  excluded_pair_count: number;
  excluded_pair_reasons: Record<string, number>;
  data_quality: Record<string, WaiverEvidence>;
  acquisition_context: {
    rules: string[];
    data_quality: WaiverEvidence;
    current_priority: number | null;
    weekly_adds_used: number | null;
    weekly_adds_remaining: number | null;
    claim_clear_at: string | null;
    detail: string;
  };
  limitations: string[];
}

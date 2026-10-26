import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import type {
  CoverageMetric,
  CoverageSlice,
  WaiverBoard,
  WaiverCandidate,
  WaiverDataGap,
  WaiverEvidence,
  WaiverImpact,
  WaiverMode,
  TransactionAnalysis,
  SwapAnalysis,
} from "./waiverTypes";

const CURRENT_WAIVER_MODEL_VERSION = "waiver-evidence-phase3";

function number(value: number | null | undefined): string {
  return value == null ? "Unavailable" : value.toFixed(1);
}

function exact(value: number | null | undefined): string {
  return value == null ? "Unavailable" : String(value);
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function timestamp(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    timeZoneName: "short",
  });
}

function pacificDate(value: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function daysUntilPacificSunday(value: string): number {
  const [year, month, day] = pacificDate(value).split("-").map(Number);
  return (7 - new Date(Date.UTC(year, month - 1, day)).getUTCDay()) % 7;
}

function Quality({ fields }: { fields: Record<string, WaiverEvidence> }) {
  return <dl className="waiver-quality">{Object.entries(fields).map(([name, field]) =>
    <div key={name} className={`waiver-evidence is-${field.state}`}>
      <dt>{label(name)}: <strong>{field.state}</strong></dt>
      <dd>{field.detail}<br />{field.source} · {field.as_of ? timestamp(field.as_of) : "Source timestamp unavailable"}{field.sample_count != null && <> · {field.sample_count} observations</>}</dd>
    </div>,
  )}</dl>;
}

function coverageLabel(name: string, metric: CoverageMetric): string {
  return `${metric.count}/${metric.total} (${metric.percentage.toFixed(1)}%) ${label(name)}`;
}

function CoverageScopeDetails({ title, scope }: { title: string; scope: CoverageSlice }) {
  return <section aria-label={`${title} coverage`}>
    <h4>{title}</h4>
    <dl className="waiver-quality">
      <div><dt>Identity</dt><dd>{coverageLabel("complete mappings", scope.identity.complete)} · {coverageLabel("unresolved mappings", scope.identity.unresolved)} · states: {Object.entries(scope.identity.resolution_counts).map(([state, count]) => `${label(state)} ${count}`).join(", ") || "none"}</dd></div>
      <div><dt>Production</dt><dd>{coverageLabel("recent supported", scope.production.recent_supported)} · {coverageLabel("recent missing", scope.production.recent_missing)} · {coverageLabel("recent stale", scope.production.recent_stale)} · {coverageLabel("season supported", scope.production.season_supported)} · {coverageLabel("season missing", scope.production.season_missing)} · {coverageLabel("season stale", scope.production.season_stale)}</dd></div>
      <div><dt>Schedule</dt><dd>{coverageLabel("in-window rows", scope.schedule.supported)} · {coverageLabel("unknown", scope.schedule.unknown)} · {coverageLabel("stale", scope.schedule.stale)} · {coverageLabel("source incomplete", scope.schedule.source_incomplete)}</dd></div>
      <div><dt>Status</dt><dd>{coverageLabel("explicit", scope.status.explicit)} · {coverageLabel("Yahoo blank", scope.status.yahoo_blank)} · {coverageLabel("stale", scope.status.stale)}</dd></div>
      <div><dt>Role</dt><dd>{coverageLabel("qualified minutes", scope.role.minutes_qualified)} · {coverageLabel("supported game-level usage", scope.role.usage_supported)} · {coverageLabel("recent game-level starts", scope.role.game_level_starts_supported)} · {coverageLabel("season starts", scope.role.season_starts_supported)} · {coverageLabel("insufficient sample", scope.role.insufficient_sample)} · {coverageLabel("missing role inputs", scope.role.missing_inputs)}</dd></div>
    </dl>
  </section>;
}

function CoverageSummary({ board }: { board: WaiverBoard }) {
  const { coverage } = board;
  const scopes: { title: string; value: CoverageSlice }[] = [
    { title: "Full persisted Yahoo pool", value: coverage.pool },
    { title: "Eligible candidates", value: coverage.candidates },
    { title: "Configured roster", value: coverage.roster },
  ];
  const categories: WaiverDataGap["category"][] = [
    "FIXABLE DATA ISSUE",
    "WAITING FOR MORE GAMES",
    "SOURCE DOES NOT SUPPLY",
    "NEW SOURCE REQUIRED",
    "UNVERIFIED YAHOO CONTEXT",
    "SOURCE CONTRACT UNVERIFIED",
    "INTENTIONALLY UNSUPPORTED",
  ];
  return <section aria-labelledby="waiver-coverage">
    <h3 id="waiver-coverage">Persisted evidence coverage</h3>
    <p>Population: {coverage.population.total} Yahoo-pool observations · {coverage.population.candidates} eligible candidates · {coverage.population.roster} configured-roster players. Percentages below use the full persisted pool unless identified as a different scope.</p>
    {scopes.map(({ title, value }) => <CoverageScopeDetails key={title} title={title} scope={value} />)}
    <p><strong>Acquisition context:</strong> {coverageLabel("supported", coverage.acquisition.supported)} · {coverageLabel("unsupported", coverage.acquisition.unsupported)}</p>
    <h3>DATA GAPS</h3>
    {categories.map((category) => {
      const gaps = board.data_gaps.filter((gap) => gap.category === category);
      return <section key={category} aria-label={category}>
        <h4>{category}</h4>
        {gaps.length
          ? <ul>{gaps.map((gap) => <li key={`${gap.category}-${gap.field}`}><strong>{gap.field}: {gap.count}/{gap.total} ({gap.percentage.toFixed(1)}%).</strong> {gap.reason}</li>)}</ul>
          : <p>{category === "NEW SOURCE REQUIRED"
            ? "No additional source is selected: current evidence and verified source terms did not establish a suitable free/legal replacement."
            : "No persisted gap is currently counted in this category."}</p>}
      </section>;
    })}
    {coverage.mapping_worklist.length > 0 && <details>
      <summary>Identity mapping worklist · {coverage.mapping_worklist.length} unresolved records</summary>
      <ul>{coverage.mapping_worklist.map((item) => <li key={`${item.internal_id}-${item.yahoo_player_id}`}>
        <strong>{item.yahoo_name}</strong> · Yahoo ID {item.yahoo_player_id} · Yahoo team {item.yahoo_team ?? "unknown"} · {label(item.resolution_state)}.
        {" "}{item.conflict_reason}
        {" "}Potential normalized-name NBA matches: {item.potential_nba_matches.length
          ? item.potential_nba_matches.map((match) => `${match.player_name} (${match.nba_player_id}, ${match.team ?? "team unknown"})`).join("; ")
          : "none in the persisted NBA player table"}.
      </li>)}</ul>
    </details>}
  </section>;
}

function sampleClass(sample: string): string {
  return `waiver-sample waiver-sample-${sample.toLowerCase().replaceAll(" ", "-")}`;
}

function sampleRisk(candidate: WaiverCandidate): string[] {
  return [
    ...(candidate.recent.games < 7
      ? [`Recent evidence: ${candidate.recent.sample_label.toLowerCase()}.`] : []),
    ...(candidate.ros.games < 7
      ? [`Historical evidence: ${candidate.ros.sample_label.toLowerCase()}.`] : []),
    ...(!candidate.yahoo_status ? ["Yahoo status is unknown."] : []),
    ...Object.entries(candidate.data_quality)
      .filter(([, evidence]) => ["partial", "missing", "stale", "unknown"].includes(evidence.state))
      .map(([name, evidence]) => `${label(name)} evidence is ${evidence.state}.`),
    ...candidate.limitations,
  ];
}

function CandidateSamples({ candidate }: { candidate: WaiverCandidate }) {
  const windows: [string, WaiverCandidate["recent"]][] = [["Recent", candidate.recent], ["Season Evidence", candidate.ros]];
  return <div className="waiver-samples">
    <p><strong>Current-season evidence: {candidate.evidence_quality}</strong> · {candidate.current_season_games} games. Evidence quality is not probability.</p>
    <div><strong>Recent {number(candidate.recent.value)} fantasy PPG</strong><span className={sampleClass(candidate.recent.sample_label)}>{candidate.recent.sample_label}</span>
      <small>{candidate.recent.games} games · {candidate.recent.season ?? "season unavailable"}</small></div>
    <div><strong>Season Evidence {number(candidate.ros.value)} fantasy PPG</strong><span className={sampleClass(candidate.ros.sample_label)}>{candidate.ros.sample_label}</span>
      <small>{candidate.ros.games} games · {candidate.ros.season ?? "no historical season"} · historical, not a projection</small></div>
    <details><summary>Exact Fantasy PPG inputs and contributions</summary>
      {windows.map(([title, value]) =>
        <p key={title}><strong>{title}:</strong> {Object.entries(value.scoring_weights ?? {})
          .map(([field, weight]) => `${field === "TOV" ? "TO (NBA TOV)" : field} ${exact(value.per_game_stats[field])} × ${exact(weight)} = ${exact(value.scoring_contributions?.[field])}`).join(" + ") || "Unavailable: complete persisted scoring/stat inputs required."}
          {value.value !== null && <> · Total {exact(value.value)} fantasy PPG</>}</p>,
      )}
    </details>
  </div>;
}

export function RoleEvidence({ candidate }: { candidate: WaiverCandidate }) {
  const role = candidate.opportunity.current_role;
  const status = candidate.data_quality.status;
  return <div className="waiver-role">
    <p><strong>CURRENT ROLE</strong></p>
    <p><strong>Role evidence: {role?.trend ?? "INSUFFICIENT EVIDENCE"}</strong> · {role?.quality.state ?? "unavailable"}. Descriptive observations, not a projection.</p>
    {role ? <>
      <dl className="waiver-comparison">
        {([["Minutes", role.minutes, 1], ["Usage", role.usage, 100]] as const).map(([title, metric, multiplier]) =>
          <div key={title}><dt>{title}</dt><dd>
            Recent {number(metric.recent.average == null ? null : metric.recent.average * multiplier)}{title === "Usage" ? "%" : ""} ({metric.recent.games} games)
            {" · "}comparison {number(metric.comparison.average == null ? null : metric.comparison.average * multiplier)} ({metric.comparison.games} games)
            {" · "}delta {metric.delta != null && metric.delta > 0 ? "+" : ""}{number(metric.delta == null ? null : metric.delta * multiplier)}{title === "Usage" ? " percentage points" : " minutes"}
            <br />{metric.quality.state} · {metric.recent.window_start ?? "No dates"}–{metric.recent.window_end ?? "No dates"} vs {metric.comparison.window_start ?? "No comparison dates"}–{metric.comparison.window_end ?? "No comparison dates"}
          </dd></div>,
        )}
        <div><dt>Starts</dt><dd>{role.starts.season_starts ?? "Unavailable"} season starts / {role.starts.season_games ?? "unknown"} games · {role.starts.quality.state}<br />Recent starts: {role.starts.recent_starts ?? "Unavailable"}. {role.starts.detail}</dd></div>
        <div><dt>Season usage context</dt><dd>{number(role.season_usage == null ? null : role.season_usage * 100)}% · {role.season_usage_quality.state}. Not recent usage or trend.</dd></div>
      </dl>
      <details><summary>Role calculation and source evidence</summary>
        <p>{role.method}</p>
        {([["Minutes", role.minutes, 1], ["Usage", role.usage, 100]] as const).map(([title, metric, multiplier]) =>
          <p key={title}>{title} median corroboration: {number(metric.recent.median == null ? null : metric.recent.median * multiplier)} vs {number(metric.comparison.median == null ? null : metric.comparison.median * multiplier)} · delta {number(metric.median_delta == null ? null : metric.median_delta * multiplier)}{title === "Usage" ? " percentage points" : " minutes"}.
            <br />Recent game IDs: {metric.recent.game_ids.join(", ") || "Unavailable"} · comparison game IDs: {metric.comparison.game_ids.join(", ") || "Unavailable"}.
            <br />Missing/invalid IDs: {[...metric.recent.missing_game_ids, ...metric.comparison.missing_game_ids].join(", ") || "None observed"} · stale import IDs: {[...metric.recent.stale_game_ids, ...metric.comparison.stale_game_ids].join(", ") || "None observed"}.
          </p>,
        )}
        <p>Opportunity parts (each counted once): {Object.entries(candidate.opportunity.score_parts).map(([key, value]) => `${label(key)} ${number(value)}`).join(" · ") || "Unavailable: qualified role evidence required."}</p>
        <Quality fields={{ role: role.quality, minutes: role.minutes.quality, usage: role.usage.quality, starts: role.starts.quality, season_usage: role.season_usage_quality }} />
        <ul>{role.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </> : <p>Role inputs unavailable; no neutral opportunity or role assumption is made.</p>}
    <p><strong>Yahoo raw status:</strong> {candidate.raw_yahoo_status ?? "(not supplied)"} · normalized status: {candidate.yahoo_status ?? "UNKNOWN"} · {status?.state ?? "unavailable"} · {status?.as_of ? timestamp(status.as_of) : "Timestamp unavailable"}.
      {" "}{status?.detail ?? "Blank status is unknown, not healthy."} Diagnostic: {candidate.status_diagnostic ? label(candidate.status_diagnostic) : "unknown"}. No injury-return date is inferred.</p>
    <p><strong>Identity mapping:</strong> {label(candidate.identity_mapping_state)} · Yahoo team {candidate.yahoo_team ?? "unknown"} vs NBA team {candidate.nba_team ?? "unknown"} · {candidate.identity_mapping_reason}</p>
    <p><strong>SCHEDULE</strong></p>
    <p>{candidate.schedule.window_start}–{candidate.schedule.window_end} Pacific · {candidate.schedule.games_remaining ?? "Unknown"} persisted games · {candidate.schedule.off_day_games ?? "Unknown"} off-days · {candidate.schedule.back_to_backs ?? "Unknown"} back-to-back pairs.
      {" "}Coverage: {candidate.schedule.coverage ?? "UNKNOWN"} · {candidate.data_quality.schedule?.state ?? "unavailable"} · {label(candidate.schedule.diagnostic_reason ?? "unknown")} · {candidate.schedule.source_row_count} persisted source rows · {candidate.schedule.imported_at ? timestamp(candidate.schedule.imported_at) : "Import timestamp unavailable"}.
      {" "}Opponents: {candidate.schedule.opponents.join(", ") || "Unavailable"}. Opponent identity is not matchup difficulty.</p>
    <details><summary>Identity-chain diagnostic</summary>
      <p>{label(candidate.mapping_diagnostic ?? "unknown")} · {candidate.data_quality.identity?.detail ?? "Identity evidence unavailable"}.</p>
      <p>Yahoo player → internal identity → NBA player → current team → game logs → season stats → player schedule.</p>
    </details>
  </div>;
}

function ReplacementCard({ candidate, rank, onAnalyze }: {
  candidate: WaiverCandidate;
  rank: number;
  onAnalyze: (id: number) => void;
}) {
  const comparison = candidate.comparison;
  const risks = sampleRisk(candidate);
  return <article className="waiver-replacement-card">
    <header><div><p className="waiver-kicker">Replacement option {rank}</p><h3>{candidate.player_name}</h3></div>
      <span className={`waiver-decision is-${candidate.roster_decision}`}>{candidate.recommended_action}</span></header>
    <p>{candidate.position ?? "Position unknown"} · {candidate.nba_team ?? "NBA team unknown"} · Yahoo status: {candidate.yahoo_status ?? "Unknown status"}</p>
    <CandidateSamples candidate={candidate} />
    <RoleEvidence candidate={candidate} />
    <p><strong>Ranking blend:</strong> {candidate.ranking_value.label} · blended value {number(candidate.ranking_value.value)} · recent weight {candidate.ranking_value.recent_weight === null ? "Unavailable" : `${(candidate.ranking_value.recent_weight * 100).toFixed(0)}%`} · historical {number(candidate.ranking_value.historical_value)} ({candidate.ranking_value.historical_games} games, {candidate.ranking_value.historical_season ?? "season unavailable"}). Historical value is not a projection.</p>
    <dl className="waiver-comparison">
      <div><dt>Selected drop</dt><dd>{comparison?.player_name ?? "No measured comparison for this roster player"}</dd></div>
      <div><dt>Roster before</dt><dd>{number(comparison?.before_score)}</dd></div>
      <div><dt>Roster after</dt><dd>{number(comparison?.after_score)}</dd></div>
      <div><dt>Net improvement</dt><dd>{number(comparison?.net_improvement)}</dd></div>
    </dl>
    {comparison && (comparison.net_improvement === null || comparison.net_improvement <= 0
      ? <p className="waiver-outcome is-no-improvement"><strong>No measured improvement.</strong> This swap is a tradeoff, not a recommendation to replace the selected player.</p>
      : <p className="waiver-outcome"><strong>Positive measured roster-index change.</strong> This is descriptive evidence, not a projection or guarantee.</p>)}
    {comparison && <>
      <p><strong>Component changes</strong> (roster-mean / coverage indices; before → after; delta)</p>
      <ul className="waiver-component-list">{Object.entries(comparison.component_before).map(([key, before]) => {
        const after = comparison.component_after[key as keyof typeof comparison.component_after];
        const delta = comparison.component_deltas[key as keyof typeof comparison.component_deltas];
        return <li key={key}>{label(key)}: {number(before)} → {number(after)} ({delta !== null && delta > 0 ? "+" : ""}{number(delta)})</li>;
      })}</ul>
      <p><strong>Effective comparison weights:</strong> {Object.entries(comparison.effective_weights).map(([key, value]) => `${label(key)} ${(value * 100).toFixed(1)}%`).join(" · ") || "Unavailable"}.</p>
      <p><strong>Starting-slot compatibility:</strong> {comparison.starting_slots_before ?? "?"} before → {comparison.starting_slots_after ?? "?"} after; {comparison.starting_slots_required ?? "?"} starting slots required.</p>
    </>}
    <p><strong>Schedule:</strong> {candidate.schedule.games_remaining ?? "Unknown"} games, {candidate.schedule.off_day_games ?? "unknown"} off-day games, {candidate.schedule.back_to_backs ?? "unknown"} back-to-back pairs · {candidate.schedule.window_start}–{candidate.schedule.window_end} Pacific · {candidate.schedule.opponents.join(", ") || "opponents unavailable"}.</p>
    <p><strong>Opportunity:</strong> {candidate.opportunity.role}; {number(candidate.opportunity.minutes)} minutes · opportunity index {number(candidate.components.opportunity)}.</p>
    <h4>Reasons and tradeoffs</h4>
    {candidate.reasons.length ? <ul>{candidate.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p>No supported reason recorded.</p>}
    <h4>Risks and limitations</h4>
    {risks.length ? <ul>{risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <p>No additional limitations reported.</p>}
    <button className="button button-quiet" onClick={() => onAnalyze(candidate.player_id)}>Analyze option: {candidate.player_name}</button>
  </article>;
}

function RosterPicker({ roster, selectedId, onSelect }: {
  roster: WaiverCandidate[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const [search, setSearch] = useState("");
  const matchingRoster = roster.filter((candidate) =>
    `${candidate.player_name} ${candidate.position ?? ""}`.toLowerCase().includes(search.trim().toLowerCase()),
  );
  return <section className="panel waiver-panel" aria-labelledby="waiver-roster">
    <h2 id="waiver-roster">Who should I replace?</h2>
    <p>Select one player to compare every replacement against. Selection is preserved when analysis mode changes.</p>
    {!roster.length ? <p role="status">No imported manager roster is available for replacement comparisons.</p> :
      <>
      <label className="waiver-filter">Search roster players
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
      </label>
      <fieldset className="waiver-roster-picker"><legend>Choose one player to drop</legend>
        {!matchingRoster.length && <p role="status">No roster players match this search.</p>}
        {matchingRoster.map((candidate) => <label className={`waiver-roster-card${candidate.player_id === selectedId ? " is-selected" : ""}`} key={candidate.player_id}>
          <input type="radio" name="selected-drop" value={candidate.player_id} checked={candidate.player_id === selectedId} onChange={() => onSelect(candidate.player_id)} />
          <span className="waiver-roster-main"><strong>{candidate.player_name}</strong><span>{candidate.position ?? "Position unknown"} · {candidate.yahoo_status ?? "Unknown status"} · {candidate.schedule.games_remaining ?? "?"} schedule games</span></span>
          <span className="waiver-roster-evidence">{label(candidate.roster_decision)}<br />Recent {number(candidate.recent.value)} fantasy PPG · {candidate.recent.games} games<br />Season Evidence {number(candidate.ros.value)} fantasy PPG · {candidate.ros.games} games</span>
        </label>)}
      </fieldset>
      </>}
  </section>;
}

export function Replacements({ board, loading, error, selectedDropId, onAnalyze }: {
  board: WaiverBoard | null;
  loading: boolean;
  error: string;
  selectedDropId: number | null;
  onAnalyze: (id: number) => void;
}) {
  if (board && board.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <section className="panel waiver-panel" aria-labelledby="waiver-replacements">
      <h2 id="waiver-replacements">Top 3 replacements</h2>
      <p className="notice notice-error" role="alert">Replacement evidence uses incompatible model {board.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Do not use these results.</p>
    </section>;
  }
  const measured = board?.candidates.find((candidate) => candidate.player_id === board.top_measured_candidate_id);
  return <section className="panel waiver-panel" aria-labelledby="waiver-replacements">
    <h2 id="waiver-replacements">Top 3 replacements</h2>
    <p>Each comparison uses only the selected drop: {board?.roster.find((candidate) => candidate.player_id === selectedDropId)?.player_name ?? "select a roster player"}.</p>
    {board && <p className="waiver-outcome"><strong>{board.selected_player_result}</strong></p>}
    <p className="waiver-measured-label">Top measured option: {measured?.player_name ?? "not established"} · {measured ? "model-ranked, limited evidence" : "limited evidence"}</p>
    {loading && <p role="status">Loading replacements for the selected player...</p>}
    {error && <p role="alert">{error} Select the roster player again or reload to retry.</p>}
    {!loading && !error && !board && selectedDropId === null && <p>No comparison is available without a roster player selection.</p>}
    {!loading && !error && board && !board.candidates.length && <p role="status">No replacement candidates are supported for this selected player.</p>}
    {!loading && !error && board && <div className="waiver-replacement-list">
      {board.candidates.slice(0, 3).map((candidate, index) =>
        <ReplacementCard key={candidate.player_id} candidate={candidate} rank={index + 1} onAnalyze={onAnalyze} />)}
    </div>}
  </section>;
}

export function WaiverResults({ board, onAnalyze }: { board: WaiverBoard; onAnalyze: (id: number) => void }) {
  const restOfWeek = board.mode === "this_week" && daysUntilPacificSunday(board.generated_at) < 2;
  const [search, setSearch] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [evidenceFilter, setEvidenceFilter] = useState("all");
  const [scheduleAvailable, setScheduleAvailable] = useState(false);
  const [sortBy, setSortBy] = useState("ppg");
  if (board.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <p className="notice notice-error" role="alert">Board results use incompatible model {board.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Decision, ranking, and analysis actions are disabled.</p>;
  }
  const ppg = (candidate: WaiverCandidate) =>
    (board.mode === "ros" ? candidate.ros : candidate.recent).value;
  const candidates = board.candidates.filter((candidate) => {
    const matchesSearch = `${candidate.player_name} ${candidate.nba_team ?? ""}`.toLowerCase().includes(search.trim().toLowerCase());
    const positions = (candidate.position ?? "").split(",").map((position) => position.trim().toUpperCase());
    const matchesPosition = positionFilter === "all" || positions.includes(positionFilter);
    const matchesStatus = statusFilter === "all"
      || (statusFilter === "unknown" ? candidate.yahoo_status === null : candidate.yahoo_status === statusFilter);
    const matchesEvidence = evidenceFilter === "all"
      || (evidenceFilter === "WATCH" || evidenceFilter === "INSUFFICIENT EVIDENCE"
        ? candidate.recommended_action === evidenceFilter
        : candidate.evidence_quality === evidenceFilter);
    const hasSchedule = candidate.schedule.games_remaining !== null && candidate.schedule.freshness === "fresh";
    return matchesSearch && matchesPosition && matchesStatus && matchesEvidence
      && (!scheduleAvailable || hasSchedule);
  }).sort((left, right) => {
    const evidenceOrder = ["EXCELLENT", "GOOD", "LIMITED", "VERY LIMITED", "INSUFFICIENT FOR STRONG RECOMMENDATION", "NO CURRENT-SEASON EVIDENCE"];
    const leftValue = sortBy === "ppg" ? ppg(left)
      : sortBy === "games" ? left.current_season_games
        : sortBy === "next7" ? left.schedule.next_7_days_games
          : -evidenceOrder.indexOf(left.evidence_quality);
    const rightValue = sortBy === "ppg" ? ppg(right)
      : sortBy === "games" ? right.current_season_games
        : sortBy === "next7" ? right.schedule.next_7_days_games
          : -evidenceOrder.indexOf(right.evidence_quality);
    return (rightValue ?? -Infinity) - (leftValue ?? -Infinity)
      || left.player_id - right.player_id;
  });
  return <>
    <section className="panel waiver-panel" aria-labelledby="waiver-ranked">
      <details>
      <summary id="waiver-ranked">All available players ({board.candidates.length})</summary>
      <p>Recent and Season Evidence are historical Yahoo-rule fantasy points per game, not projections. Sample labels are evidence quality, not probability. Fit, schedule and opportunity are model indices / 100.</p>
      <p>{board.excluded_count} Yahoo O/NA players excluded. {board.unknown_availability_count} players withheld for unknown availability.</p>
      {!board.candidates.length ? <p role="status">No available players have sufficient persisted availability evidence. Review freshness and mapping diagnostics.</p> :
        <>
        <div className="waiver-filters" aria-label="Available player filters">
          <label className="waiver-filter">Search players
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <label className="waiver-filter">Position
            <select value={positionFilter} onChange={(event) => setPositionFilter(event.target.value)}>
              <option value="all">All positions</option>
              {["PG", "SG", "SF", "PF", "C"].map((position) => <option key={position} value={position}>{position}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Yahoo status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option><option value="unknown">Unknown / blank</option>
              {[...new Set(board.candidates.map((candidate) => candidate.yahoo_status).filter((status): status is string => status !== null))].sort().map((status) =>
                <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Decision / evidence
            <select value={evidenceFilter} onChange={(event) => setEvidenceFilter(event.target.value)}>
              <option value="all">All decisions</option><option value="WATCH">WATCH</option><option value="INSUFFICIENT EVIDENCE">Insufficient evidence</option>
              {["EXCELLENT", "GOOD", "LIMITED", "VERY LIMITED", "INSUFFICIENT FOR STRONG RECOMMENDATION", "NO CURRENT-SEASON EVIDENCE"].map((item) =>
                <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Sort by
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              <option value="ppg">Fantasy PPG</option><option value="games">Current-season games</option>
              <option value="next7">Next 7 Days games</option><option value="evidence">Evidence quality</option>
            </select>
          </label>
          <label className="waiver-checkbox"><input type="checkbox" checked={scheduleAvailable} onChange={(event) => setScheduleAvailable(event.target.checked)} /> Schedule available</label>
        </div>
        {!candidates.length ? <p role="status">No players match the current filters.</p> :
        <div className="waiver-table-scroll" role="region" aria-label="Waiver candidates, scroll horizontally for all columns" tabIndex={0}>
          <table className="waiver-table">
            <caption>Available players. Analysis opens evidence only; no Yahoo transaction is executed.</caption>
            <thead><tr>{["Rank", "Player", "Pos", "Status", "CURRENT ROLE", "Fantasy PPG", "Season Evidence", "Decision", "Team Fit", "Next 7 Days", "Action"].map((column) =>
              <th key={column} scope="col">{column}</th>)}</tr></thead>
            <tbody>{candidates.map((row, index) => <tr key={row.player_id}>
              <td>{row.overall_score === null ? "Unscored" : index + 1}</td>
              <th scope="row"><button className="waiver-player" onClick={() => onAnalyze(row.player_id)}>{row.player_name}</button><small>{row.nba_team ?? "NBA team unknown"} · score {number(row.overall_score)} · {label(row.hold_type)}</small></th>
              <td>{row.position ?? "Unknown"}</td>
              <td>{row.yahoo_status ?? "Unknown status"}</td>
              <td>{row.opportunity.role}</td>
              <td>{number(ppg(row))}<small>{(board.mode === "ros" ? row.ros : row.recent).games} games · {row.evidence_quality}</small></td>
              <td>{number(row.ros.value)}<small>{row.ros.games} games · {row.ros.sample_label} · historical, not projection</small></td>
              <td>{row.recommended_action}</td>
              <td>{number(row.components.roster_fit)}</td>
              <td>{row.schedule.next_7_days_games ?? "Unknown"} games<small>{row.schedule.diagnostic_reason}</small></td>
              <td><button className="button button-quiet" onClick={() => onAnalyze(row.player_id)}>Analyze {label(row.recommended_action)}</button></td>
            </tr>)}</tbody>
          </table>
        </div>}
        </>}
      </details>
    </section>
    <details className="panel waiver-panel" aria-labelledby="waiver-quality">
      <summary id="waiver-quality">Advanced Evidence · Data quality and freshness</summary>
      <p>Read from persisted data only · calculated {timestamp(board.generated_at)} · {board.model_version}</p>
      <p>Default configured weights: {Object.entries(board.weights).map(([key, value]) => `${label(key)} ${(value * 100).toFixed(0)}%`).join(" · ")}. Missing components are omitted and measured weights renormalized, never filled with invented values.</p>
      <p>Best overall available ID: {board.best_overall_available_id ?? "Unavailable"} · best team-fit ID: {board.best_add_for_team_id ?? "Unavailable"} · top measured candidate ID: {board.top_measured_candidate_id ?? "Unavailable"}.</p>
      <ul>{board.team_needs.map((need) => <li key={need}>{need}</li>)}</ul>
      {board.waiver_rules?.length
        ? <><h3>Persisted waiver rules</h3><ul>{board.waiver_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul></>
        : <p>Fresh persisted waiver rules are unavailable.</p>}
      <p>Current priority, weekly adds used/remaining, and claim-clear time are unverified.</p>
      <Quality fields={board.data_quality} />
      <CoverageSummary board={board} />
      <h3>Unsupported analytics and limitations</h3>
      <ul>{board.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
    </details>
    <p className="waiver-window-note">{board.mode === "this_week"
      ? `Rest of Week${restOfWeek ? " · limited days remaining" : ""}: persisted games through Sunday Pacific Time, not a verified Yahoo matchup week.`
      : board.mode === "next_7_days"
        ? "Next 7 Days: today through today + 6 in Pacific Time; this is not the Yahoo matchup week."
        : "Season Evidence: historical/stat-based evidence, not a projection."}</p>
  </>;
}

export function ImpactContent({ impact, selectedDropId }: { impact: WaiverImpact; selectedDropId: number }) {
  if (impact.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <p className="notice notice-error" role="alert">Impact evidence uses incompatible model {impact.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Do not use this analysis.</p>;
  }
  const player = impact.candidate;
  const comparison = impact.comparison;
  return <>
    <h2 id="waiver-impact-title">{player.player_name}: add/drop analysis</h2>
    <p>{player.position ?? "Unknown position"} · {player.nba_team ?? "Unknown NBA team"} · Yahoo {player.yahoo_status ?? "unknown status"} · {label(player.availability)} · {label(player.hold_type)}</p>
    <CandidateSamples candidate={player} />
    <RoleEvidence candidate={player} />
    <p>Ranking blend: {player.ranking_value.label} · recent weight {player.ranking_value.recent_weight === null ? "Unavailable" : `${(player.ranking_value.recent_weight * 100).toFixed(0)}%`} · historical evidence, not a projection.</p>
    <h3>Why this player?</h3>
    <ul>{player.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    <p>Minutes {number(player.opportunity.minutes)}; minutes trend {number(player.opportunity.minutes_trend)}; usage trend {number(player.opportunity.usage_trend)}; historical start rate {number(player.opportunity.historical_start_rate)}. No inferred injury opportunity.</p>
    <p>Persisted schedule {player.schedule.window_start} through {player.schedule.window_end} (Pacific Time): {player.schedule.games_remaining ?? "unknown"} games, {player.schedule.off_day_games ?? "unknown"} off-day games, {player.schedule.back_to_backs ?? "unknown"} back-to-back pairs. Opponents: {player.schedule.opponents.join(", ") || "Unavailable"}.</p>
    <h3>Selected drop comparison</h3>
    {comparison ? <>
      <p>Add {player.player_name}; {comparison.player_id === null ? "no drop required by the imported roster capacity" : `drop ${comparison.player_name}`}.</p>
      <dl className="waiver-comparison"><div><dt>Roster before</dt><dd>{number(comparison.before_score)}</dd></div>
        <div><dt>Roster after</dt><dd>{number(comparison.after_score)}</dd></div>
        <div><dt>Net model improvement</dt><dd>{number(comparison.net_improvement)}</dd></div></dl>
      <p>This is a descriptive roster-index difference, not expected fantasy points or a prediction.</p>
      <ul>{comparison.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      <h4>Component changes</h4>
      <dl className="waiver-quality">{Object.entries(comparison.component_deltas).map(([key, value]) =>
        <div key={key}><dt>{label(key)}</dt><dd>{number(value)}</dd></div>)}</dl>
      <p>Starting-slot compatibility: {comparison.starting_slots_before ?? "?"} before → {comparison.starting_slots_after ?? "?"} after; {comparison.starting_slots_required ?? "?"} required.</p>
    </> : <p>No measured comparison is available for selected roster player ID {selectedDropId}. The selected drop will not be changed automatically.</p>}
    <details><summary>Advanced Evidence · components, weights, and source quality</summary>
      <h3>Component scores and effective weights</h3>
      <dl className="waiver-quality">{Object.entries(player.components).map(([key, value]) =>
        <div key={key}><dt>{label(key)}</dt><dd>{exact(value)} / 100 · {((player.effective_weights[key] ?? 0) * 100).toFixed(1)}%</dd></div>)}</dl>
      <Quality fields={player.data_quality} />
      <ul>{player.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </details>
    <p>Analysis only. Complete any transaction yourself in Yahoo after checking current availability.</p>
  </>;
}

function ImpactDialog({ playerId, mode, dropPlayerId, onClose }: {
  playerId: number;
  mode: WaiverMode;
  dropPlayerId: number;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [impact, setImpact] = useState<WaiverImpact | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setImpact(null);
    setError("");
    api.getWaiverImpact(playerId, mode, dropPlayerId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setImpact(data); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Impact analysis failed."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [playerId, mode, dropPlayerId]);
  return <dialog ref={dialog} className="waiver-dialog" aria-label="Player impact analysis" onCancel={onClose}>
    <button className="button button-quiet waiver-close" autoFocus onClick={onClose}>Close analysis</button>
    {loading && <p role="status">Loading persisted player impact...</p>}
    {error && <p role="alert">{error}</p>}
    {impact && impact.model_version !== CURRENT_WAIVER_MODEL_VERSION &&
      <p className="notice notice-error" role="alert">Impact response uses incompatible model {impact.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. The analysis is blocked.</p>}
    {impact?.model_version === CURRENT_WAIVER_MODEL_VERSION && <ImpactContent impact={impact} selectedDropId={dropPlayerId} />}
  </dialog>;
}

export function TransactionSummary({ analysis, onAnalyze }: {
  analysis: TransactionAnalysis;
  onAnalyze: (swap: SwapAnalysis) => void;
}) {
  if (analysis.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <section className="panel waiver-panel" aria-labelledby="waiver-transaction">
      <h2 id="waiver-transaction">BEST MOVE NOW</h2>
      <p className="notice notice-error" role="alert">Transaction response uses incompatible model {analysis.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. No decision or transaction details are shown.</p>
    </section>;
  }
  const best = analysis.best_transaction;
  return <section className="panel waiver-panel" aria-labelledby="waiver-transaction">
    <h2 id="waiver-transaction">BEST MOVE NOW</h2>
    <p>Best Supported Transaction or HOLD · Model {analysis.model_version}.</p>
    <p>Hypothetical analysis only. No Yahoo transaction is executed.</p>
    {best ? <>
      <h3>ADD: {best.add_player.player_name}</h3>
      <p><strong>DROP: {best.drop_player.player_name}</strong> · Decision: {best.decision}</p>
      <p><strong>Positive measured change.</strong> Descriptive model-index evidence, not a fantasy-point gain, projection, win estimate, or probability.</p>
      <details><summary>Exact roster model-index values</summary>
        <p>{exact(best.comparison.before_score)} → {exact(best.comparison.after_score)} · +{exact(best.comparison.net_improvement)} descriptive model-index points.</p>
      </details>
      <h4>WHY</h4>
      <ul>
        <li>Positive supported Yahoo-points roster-model change; not predicted fantasy-point gain.</li>
        <li>Yahoo fantasy PPG evidence: add {number((analysis.mode === "ros" ? best.add_player.ros : best.add_player.recent).value)} / drop {number((analysis.mode === "ros" ? best.drop_player.ros : best.drop_player.recent).value)}. Historical/stat-based, not projected.</li>
        <li>Add evidence: {best.add_player.evidence_quality} · {best.add_player.current_season_games} current-season games. Drop evidence: {best.drop_player.evidence_quality} · {best.drop_player.current_season_games} games.</li>
        <li>Starting-slot coverage: {best.comparison.starting_slots_before} → {best.comparison.starting_slots_after} of {best.comparison.starting_slots_required} slots.</li>
        {best.decision === "STREAM" && <li>Measured schedule/opportunity materially supports this short-term comparison: {best.add_player.schedule.games_remaining} persisted games; {best.add_player.opportunity.role}.</li>}
      </ul>
      <details><summary>Current role, status, and schedule evidence</summary><RoleEvidence candidate={best.add_player} /></details>
      <h4>RISKS</h4>
      <p>Add Yahoo status: {best.add_player.yahoo_status ?? "Unknown"} · drop status: {best.drop_player.yahoo_status ?? "Unknown"}. Q/P remains uncertain.</p>
      <p>Schedule: {best.add_player.data_quality.schedule?.state ?? "unknown"} coverage; counts are not guaranteed lineup starts.</p>
      <ul>{best.limitations.map((risk) => <li key={risk}>{risk}</li>)}</ul>
      <button className="button button-primary" onClick={() => onAnalyze(best)}>VIEW ANALYSIS</button>
    </> : <>
      <h3>HOLD</h3>
      <p>No supported waiver transaction currently clears the evidence threshold for {analysis.team_name ?? "Box Score Bully"}. WATCH comparisons are not recommendations.</p>
      <ul>{(analysis.decision_reasons ?? []).slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
    </>}
    <p>{analysis.evaluated_pair_count} pairs evaluated · {analysis.supported_pair_count} supported · {analysis.excluded_pair_count} excluded from the supported pool.</p>
    <h3>WATCHLIST</h3>
    <p>Promising measured swaps blocked by evidence quality. These are not supported add recommendations.</p>
    {analysis.watch_transactions.length ? <ul>{analysis.watch_transactions.map((swap) =>
      <li key={`${swap.add_player.player_id}-${swap.drop_player.player_id}`}>
        WATCH: {swap.add_player.player_name} / drop {swap.drop_player.player_name}.
        <p>Yahoo fantasy PPG: {number((analysis.mode === "ros" ? swap.add_player.ros : swap.add_player.recent).value)} · {swap.add_player.current_season_games} current-season games · {swap.add_player.schedule.next_7_days_games ?? "Unknown"} Next 7 Days games · Yahoo status {swap.add_player.yahoo_status ?? "UNKNOWN"}.</p>
        <p><strong>Why watch:</strong> positive measured roster-index change with observed comparison evidence.</p>
        <p><strong>Why not add:</strong> {swap.add_player.current_season_games < 7
          ? "current-season sample is below the existing seven-game eligibility gate"
          : "current role, status, schedule, or replacement evidence remains insufficient"} · {swap.add_player.opportunity.current_role?.trend ?? "INSUFFICIENT EVIDENCE"} role · {swap.add_player.schedule.diagnostic_reason}.</p>
        <details><summary>Measured index and blockers</summary>
          <p>+{exact(swap.comparison.net_improvement)} descriptive model-index points; this is not projected fantasy points, wins, or probability.</p>
          <ul>{swap.reasons.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </details>
        <details><summary>Current role and schedule evidence: {swap.add_player.player_name}</summary><RoleEvidence candidate={swap.add_player} /></details>
        <button className="button button-quiet" onClick={() => onAnalyze(swap)}>View watch analysis: {swap.add_player.player_name} / {swap.drop_player.player_name}</button>
      </li>,
    )}</ul> : <p>No positive measured WATCH swaps are available.</p>}
    <details><summary>Evidence and acquisition context</summary>
      <Quality fields={analysis.data_quality} />
      <ul>{Object.entries(analysis.excluded_pair_reasons).map(([reason, count]) => <li key={reason}>{reason}: {count} pairs</li>)}</ul>
      <ul>{analysis.acquisition_context.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
      <p>{analysis.acquisition_context.detail}</p>
    </details>
  </section>;
}

function GlobalTransactions({ mode, reload, onAnalyze }: {
  mode: WaiverMode;
  reload: number;
  onAnalyze: (swap: SwapAnalysis) => void;
}) {
  const [result, setResult] = useState<{ mode: WaiverMode; reload: number; analysis: TransactionAnalysis } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    setError("");
    api.getWaiverTransactions(mode, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setResult({ mode, reload, analysis: data }); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Supported transaction analysis failed."); });
    return () => controller.abort();
  }, [mode, reload]);
  if (error) return <p role="alert">{error} The current Phase-3 transaction analysis is unavailable; reload after the API is updated.</p>;
  if (!result || result.mode !== mode || result.reload !== reload || result.analysis.mode !== mode) return <p role="status">Loading supported transaction analysis...</p>;
  return <TransactionSummary analysis={result.analysis} onAnalyze={onAnalyze} />;
}

export function WaiverCenter() {
  const [mode, setMode] = useState<WaiverMode>("this_week");
  const [baseBoard, setBaseBoard] = useState<WaiverBoard | null>(null);
  const [replacementResult, setReplacementResult] = useState<{ mode: WaiverMode; dropId: number; board: WaiverBoard } | null>(null);
  const [selectedDropPlayerId, setSelectedDropPlayerId] = useState<number | null>(null);
  const [playerId, setPlayerId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [replacementLoading, setReplacementLoading] = useState(false);
  const [error, setError] = useState("");
  const [replacementError, setReplacementError] = useState("");
  const [retry, setRetry] = useState(0);
  const [transactionPair, setTransactionPair] = useState<SwapAnalysis | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setBaseBoard(null);
    setReplacementResult(null);
    setTransactionPair(null);
    setLoading(true);
    setError("");
    api.getWaivers(mode, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setBaseBoard(data); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not load waiver evidence."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mode, retry]);

  const receivedBaseBoard = baseBoard?.mode === mode ? baseBoard : null;
  const activeBaseBoard = receivedBaseBoard?.model_version === CURRENT_WAIVER_MODEL_VERSION ? receivedBaseBoard : null;
  const selectedDropId = activeBaseBoard
    ? (activeBaseBoard.roster.some((candidate) => candidate.player_id === selectedDropPlayerId)
      ? selectedDropPlayerId
      : activeBaseBoard.roster[0]?.player_id ?? null)
    : null;

  useEffect(() => {
    if (!activeBaseBoard || selectedDropId === null) {
      setReplacementResult(null);
      setReplacementLoading(false);
      return;
    }
    if (selectedDropPlayerId !== selectedDropId) {
      setSelectedDropPlayerId(selectedDropId);
      return;
    }
    const controller = new AbortController();
    setReplacementResult(null);
    setReplacementLoading(true);
    setReplacementError("");
    api.getWaiverReplacements(selectedDropId, mode, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setReplacementResult({ mode, dropId: selectedDropId, board: data });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setReplacementError(cause instanceof Error ? cause.message : "Could not load replacements.");
      })
      .finally(() => { if (!controller.signal.aborted) setReplacementLoading(false); });
    return () => controller.abort();
  }, [activeBaseBoard, mode, selectedDropId, selectedDropPlayerId, retry]);

  const currentBoard = selectedDropId === null
    ? activeBaseBoard
    : replacementResult?.mode === mode && replacementResult.dropId === selectedDropId
      ? replacementResult.board
      : null;
  const analyze = (id: number) => {
    if (selectedDropId !== null) setPlayerId(id);
  };
  const modes: [WaiverMode, string][] = [["this_week", "Rest of Week"], ["next_7_days", "Next 7 Days"], ["ros", "Season Evidence"]];

  return <main className="waiver-center">
    <header className="waiver-heading"><div><Link to="/">Court IQ · Draft desk</Link><h1>Waiver Command Center</h1>
      <p>{activeBaseBoard?.team_name ?? "Your Roster"}</p></div>
      <button className="button button-quiet" onClick={() => {
        setBaseBoard(null);
        setReplacementResult(null);
        setTransactionPair(null);
        setRetry((value) => value + 1);
      }}>Reload persisted evidence</button></header>
    <p>Who to add, who to drop, and why. No projections, fabricated evidence, or automatic Yahoo transactions.</p>
    <p>The app-configured manager team scopes analysis; this is not Yahoo-authenticated ownership evidence. Times and date windows use Pacific Time (PST/PDT).</p>
    {receivedBaseBoard && receivedBaseBoard.model_version !== CURRENT_WAIVER_MODEL_VERSION &&
      <p className="notice notice-error" role="alert">Stale deployed version: {receivedBaseBoard.model_version}. Expected {CURRENT_WAIVER_MODEL_VERSION}; board actions are disabled.</p>}
    <GlobalTransactions mode={mode} reload={retry} onAnalyze={setTransactionPair} />
    <div className="waiver-controls">
      <fieldset><legend>Analysis window</legend>{modes.map(([value, title]) =>
        <label key={value}><input type="radio" name="waiver-mode" checked={mode === value} onChange={() => setMode(value)} />{title}</label>)}</fieldset>
    </div>
    <RosterPicker roster={activeBaseBoard?.roster ?? []} selectedId={selectedDropId} onSelect={setSelectedDropPlayerId} />
    <Replacements
      board={replacementResult?.mode === mode && replacementResult.dropId === selectedDropId ? replacementResult.board : null}
      loading={loading || replacementLoading}
      error={replacementError}
      selectedDropId={selectedDropId}
      onAnalyze={analyze}
    />
    {error && <p role="alert">{error} Use Reload persisted evidence to retry.</p>}
    {loading && <p role="status">Loading persisted waiver evidence...</p>}
    {currentBoard && !loading && <WaiverResults board={currentBoard} onAnalyze={analyze} />}
    {playerId !== null && selectedDropId !== null &&
      <ImpactDialog key={`${mode}-${playerId}-${selectedDropId}`} playerId={playerId} mode={mode} dropPlayerId={selectedDropId} onClose={() => setPlayerId(null)} />}
    {transactionPair && transactionPair.mode === mode && <TransactionDialog swap={transactionPair} onClose={() => setTransactionPair(null)} />}
  </main>;
}

function TransactionDialog({ swap, onClose }: { swap: SwapAnalysis; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);
  return <dialog ref={dialog} className="waiver-dialog" aria-label="Supported transaction analysis" onCancel={onClose}>
    <button className="button button-quiet waiver-close" autoFocus onClick={onClose}>Close transaction analysis</button>
    <p>{swap.decision} · hypothetical ADD {swap.add_player.player_name} / DROP {swap.drop_player.player_name}</p>
    <ImpactContent impact={{
      league_key: "", team_key: "", mode: swap.mode, model_version: CURRENT_WAIVER_MODEL_VERSION, candidate: swap.add_player,
      comparison: swap.comparison, limitations: swap.limitations,
    }} selectedDropId={swap.drop_player.player_id} />
    <h3>Selected drop evidence: {swap.drop_player.player_name}</h3>
    <CandidateSamples candidate={swap.drop_player} />
    <RoleEvidence candidate={swap.drop_player} />
    <ul>{swap.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
  </dialog>;
}

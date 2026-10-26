import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./WaiverCenter.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const apiOutput = ts.transpileModule(api, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;

function load(states = []) {
  let index = 0;
  const exports = {};
  const loader = (name) => name === "./api" ? { api: {} } : name === "react" && states.length
    ? { ...React, useState: (initial) => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {} }
    : name === "react-router-dom" ? { Link: ({ to, children }) => React.createElement("a", { href: to }, children) }
      : require(name);
  new Function("require", "exports", output)(loader, exports);
  return exports;
}

function loadApi() {
  const exports = {};
  new Function("require", "exports", apiOutput)(require, exports);
  return exports;
}

const components = { roster_fit: 72, player_value: 70, opportunity: 60, schedule: 80, acquisition_value: null };
const evidence = { state: "partial", source: "Persisted NBA", as_of: "2026-10-25T00:00:00Z", detail: "Partial schedule and coverage." };
const roleWindow = (average, games = 3) => ({ average, median: average, games, game_ids: [], window_start: "2026-10-20", window_end: "2026-10-24", as_of: evidence.as_of, missing_game_ids: [], stale_game_ids: [] });
const currentRole = {
  minutes: { quality: { ...evidence, state: "available", detail: "Three fresh valid games on each side." }, recent: roleWindow(30), comparison: roleWindow(23), delta: 7, median_delta: 7, unit: "minutes" },
  usage: { quality: { ...evidence, state: "unavailable" }, recent: roleWindow(null, 0), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "fraction" },
  starts: { quality: { ...evidence, state: "unavailable" }, season: "2026-27", season_starts: null, season_games: null, recent_starts: null, detail: "Season starts do not prove the current lineup." },
  quality: { ...evidence, state: "available" }, trend: "RISING",
  season_usage: .231, season_usage_quality: evidence,
  method: "Latest three vs preceding three games; not a projection.", limitations: ["Game-level usage is unavailable."],
};
const drop = (id, net = 10) => ({
  player_id: id, player_name: id === 2 ? "Weak Guard" : "Bench Forward", before_score: 66, after_score: 66 + net,
  net_improvement: net, component_before: components, component_after: { ...components, roster_fit: 72 + net },
  effective_weights: { roster_fit: .4 }, starting_slots_before: 3, starting_slots_after: 3,
  starting_slots_required: 2, component_deltas: { ...components, roster_fit: net }, reasons: ["Same measured model on both sides."],
});
const candidate = (id, name, comparison = drop(2), tweaks = {}) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, position: "C",
  yahoo_team: "DEN", nba_team: "DEN", raw_yahoo_status: id === 3 ? "" : "Q",
  yahoo_status: id === 3 ? null : "Q", identity_mapping_state: "EXACT_NAME_TEAM",
  identity_mapping_reason: "Yahoo and NBA names and team abbreviations match.",
  availability: "free_agent", eligible: true,
  recent: { value: 30, games: 2, season: "2026-27", label: "Recent", sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION", per_game_stats: {} },
  ros: { value: 35, games: 60, season: "2025-26", label: "History", sample_label: "EXCELLENT", per_game_stats: {} },
  ranking_value: { value: 32, recent_weight: .4, historical_value: 35, historical_games: 60, historical_season: "2025-26", label: "Recent / historical blend" },
  opportunity: { minutes: 30, minutes_trend: 2, usage_trend: null, historical_start_rate: .5, role: "Current role unverified" },
  schedule: { games_remaining: 2, off_day_games: 1, back_to_backs: 1, next_7_days_games: 2, opponents: ["BOS"], source_row_count: 4, window_start: "2026-10-25", window_end: "2026-10-31", imported_at: evidence.as_of, freshness: "fresh", coverage: "PARTIAL", diagnostic_reason: "SCHEDULE_ROWS_PRESENT" },
  components, overall_score: 80, effective_weights: { roster_fit: .4 }, recommended_action: "WATCH",
  current_season_games: 2, evidence_quality: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  hold_type: "streamer", comparison, best_drop_options: comparison ? [comparison] : [], net_improvement: comparison?.net_improvement ?? null,
  roster_decision: "review_replacement", reasons: ["Fits an uncovered center slot"], limitations: ["Current rolling priority unavailable"],
  data_quality: { status: { ...evidence, state: id === 3 ? "unknown" : "available" }, schedule: evidence, recent: { ...evidence, state: "partial" } },
  ...tweaks,
});
const roster = [
  candidate(2, "Weak Guard", null, { availability: "rostered", roster_decision: "keep_on_measured_model", position: "G", recent: { value: 12, games: 10, season: "2026-27", label: "Recent", sample_label: "EXCELLENT", per_game_stats: {} }, ros: { value: 14, games: 60, season: "2025-26", label: "History", sample_label: "EXCELLENT", per_game_stats: {} } }),
  candidate(4, "Bench Forward", null, { availability: "rostered", roster_decision: "review_replacement", position: "F" }),
];
const metric = (count, total = 4) => ({ count, total, percentage: total ? count / total * 100 : 0 });
const coverageSlice = () => ({
  identity: { complete: metric(4), unresolved: metric(0), resolution_counts: { EXACT_NAME_TEAM: 4 } },
  production: { recent_supported: metric(3), recent_missing: metric(1), recent_stale: metric(0), season_supported: metric(4), season_missing: metric(0), season_stale: metric(0) },
  schedule: { supported: metric(3), unknown: metric(1), stale: metric(0), source_incomplete: metric(1) },
  status: { explicit: metric(3), yahoo_blank: metric(1), stale: metric(0) },
  role: { minutes_qualified: metric(3), usage_supported: metric(0), game_level_starts_supported: metric(0), season_starts_supported: metric(1), insufficient_sample: metric(1), missing_inputs: metric(4) },
});
const coverage = {
  population: { total: 4, candidates: 2, roster: 2 },
  pool: coverageSlice(), candidates: coverageSlice(), roster: coverageSlice(),
  acquisition: { supported: metric(0, 1), unsupported: metric(1, 1) },
  mapping_worklist: [],
};
const board = (dropId = 2, mode = "this_week", order = [1, 3], best_add_for_team_id = null) => ({
  league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
  mode, generated_at: "2026-10-25T00:00:00Z", model_version: "waiver-evidence-phase3",
  weights: { roster_fit: .35, player_value: .25, opportunity: .15, schedule: .15, acquisition_value: .1 },
  best_add_for_team_id, best_overall_available_id: 1, top_measured_candidate_id: null,
  selected_drop_player_id: dropId, roster, team_needs: ["Uncovered center slot"],
  waiver_rules: ["Continual rolling list", "2-day waiver period", "4 adds/week", "Daily - Today deadline"],
  selected_player_result: "WATCH",
  candidates: order.map((id) => candidate(id, id === 1 ? "Available Center" : "Overall Guard", drop(dropId, id === 1 ? (dropId === 2 ? 15 : -5) : 4))),
  excluded_count: 2, unknown_availability_count: 1, limitations: ["No projections."],
  data_quality: { roster: { ...evidence, state: "stale", detail: "Stale roster." } },
  coverage, data_gaps: [],
});

test("replacement cards show a single measured drop, evidence, ranking blend and risks", () => {
  const { Replacements } = load();
  const html = renderToStaticMarkup(React.createElement(Replacements, {
    board: board(), loading: false, error: "", selectedDropId: 2, onAnalyze() {},
  }));
  assert.match(html, /Top 3 replacements/);
  assert.match(html, /Recent evidence: insufficient for strong recommendation/);
  assert.match(html, /INSUFFICIENT FOR STRONG RECOMMENDATION/);
  assert.match(html, /historical, not a projection/);
  assert.match(html, /Recent \/ historical blend/);
  assert.match(html, /Roster before/);
  assert.match(html, /Roster after/);
  assert.match(html, /Net improvement/);
  assert.match(html, /Starting-slot compatibility/);
  assert.match(html, /Effective comparison weights/);
  assert.match(html, /recent evidence is partial/);
  assert.match(html, /Yahoo status is unknown/);
  assert.match(html, /Top measured option: not established · limited evidence/);
});

test("current role shows measured deltas, independent missing inputs, status and schedule coverage", () => {
  const { RoleEvidence } = load();
  const row = candidate(1, "Role Player", null, {
    opportunity: { current_role: currentRole, score_parts: { minutes_level: 83.333 } },
    schedule: { ...candidate(1, "").schedule, coverage: "PARTIAL", imported_at: evidence.as_of },
  });
  const html = renderToStaticMarkup(React.createElement(RoleEvidence, { candidate: row }));
  for (const text of ["CURRENT ROLE", "RISING", "+7.0", "23.1", "percentage points", "Recent starts: Unavailable",
    "Unavailable", "PARTIAL", "Opponent identity is not matchup difficulty", "Game-level usage is unavailable",
    "Yahoo team DEN vs NBA team DEN", "4 persisted source rows"]) {
    assert.ok(html.includes(text), text);
  }
  assert.match(html, /Yahoo raw status:<\/strong> Q/);
  assert.doesNotMatch(html, /Expected minutes|Projected role|Usage will increase|Breakout probability/);
  for (const status of ["Q", "P", null]) {
    row.yahoo_status = status;
    const text = renderToStaticMarkup(React.createElement(RoleEvidence, { candidate: row }));
    assert.match(text, new RegExp(`normalized status: ${status ?? "UNKNOWN"}`));
    assert.match(text, /No injury-return date is inferred/);
  }
  row.opportunity.current_role = { ...currentRole, trend: "INSUFFICIENT EVIDENCE", quality: { ...evidence, state: "partial" } };
  assert.match(renderToStaticMarkup(React.createElement(RoleEvidence, { candidate: row })), /INSUFFICIENT EVIDENCE/);
});

test("negative net remains signed and is explicitly not presented as an improvement", () => {
  const { Replacements } = load();
  const negative = board(4, "this_week", [1, 3]);
  const html = renderToStaticMarkup(React.createElement(Replacements, {
    board: negative, loading: false, error: "", selectedDropId: 4, onAnalyze() {},
  }));
  assert.match(html, /Net improvement<\/dt><dd>-5\.0/);
  assert.match(html, /No measured improvement/);
  assert.match(html, /not a recommendation to replace the selected player/);
  assert.match(html, /roster fit: 72\.0 → 67\.0 \(-5\.0\)/);
});

test("all-player evidence is secondary, collapsible, and filterable", () => {
  const { WaiverResults } = load();
  const html = renderToStaticMarkup(React.createElement(WaiverResults, {
    board: board(), onAnalyze() {},
  }));
  assert.match(html, /<details><summary id="waiver-ranked">All available players/);
  assert.match(html, /Search players/);
  assert.match(html, /Yahoo status/);
  assert.match(html, /Decision \/ evidence/);
  assert.match(html, /Schedule available/);
  assert.match(html, /Next 7 Days games/);
  assert.doesNotMatch(html, /Best Overall Available|Best Fit for Box Score Bully/);
});

test("advanced evidence renders backend coverage, grouped data gaps and exact mapping worklist", () => {
  const { WaiverResults } = load();
  const result = board();
  result.data_gaps = [{
    category: "SOURCE CONTRACT UNVERIFIED", field: "Game-level usage",
    count: 4, total: 4, percentage: 100,
    reason: "Persisted game logs do not provide supported usage values.",
    root_cause: "SOURCE_CONTRACT_UNVERIFIED",
  }];
  result.coverage.mapping_worklist = [{
    internal_id: 101, yahoo_player_id: "y101", yahoo_name: "Unmapped Center",
    yahoo_team: "DEN", normalized_name: "unmapped center",
    potential_nba_matches: [], conflict_reason: "No same-name NBA player exists.",
    resolution_state: "NO_MATCH",
  }];
  const html = renderToStaticMarkup(React.createElement(WaiverResults, {
    board: result, onAnalyze() {},
  }));
  for (const text of ["Persisted evidence coverage", "4 Yahoo-pool observations", "Full persisted Yahoo pool", "Eligible candidates", "Configured roster", "DATA GAPS",
    "SOURCE DOES NOT SUPPLY", "Game-level usage: 4/4 (100.0%)",
    "NEW SOURCE REQUIRED", "No additional source is selected",
    "Identity mapping worklist · 1 unresolved records", "Unmapped Center", "NO MATCH"]) {
    assert.ok(html.includes(text), text);
  }
});

test("backend-owned HOLD and Yahoo calculation evidence are rendered without a fake winner", () => {
  const { Replacements } = load();
  const result = board();
  result.selected_player_result = "HOLD Weak Guard";
  result.candidates = [candidate(1, "Available Center", drop(2, -5), {
    recommended_action: "PASS",
    recent: {
      value: 52, games: 2, season: "2026-27", label: "Yahoo fantasy PPG",
      sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION",
      per_game_stats: { PTS: 20, REB: 10, AST: 6, BLK: 2, STL: 3, TOV: 4 },
      scoring_weights: { PTS: 1, REB: 1.2, AST: 1.5, BLK: 3, STL: 3, TOV: -1 },
      scoring_contributions: { PTS: 20, REB: 12, AST: 9, BLK: 6, STL: 9, TOV: -4 },
    },
  })];
  const html = renderToStaticMarkup(React.createElement(Replacements, {
    board: result, loading: false, error: "", selectedDropId: 2, onAnalyze() {},
  }));
  assert.match(html, /HOLD Weak Guard/);
  assert.match(html, /Exact Fantasy PPG inputs and contributions/);
  assert.match(html, /REB 10 × 1.2 = 12/);
  assert.match(html, /TO \(NBA TOV\) 4 × -1 = -4/);
  assert.match(html, /Total 52 fantasy PPG/);
  assert.doesNotMatch(html, /Best Add|MUST ADD|ROS Projection|confidence/);
});

test("rest-of-week uses the board timestamp's Pacific calendar date", () => {
  const { WaiverResults } = load();
  const render = (generated_at) => renderToStaticMarkup(React.createElement(WaiverResults, {
    board: { ...board(), generated_at }, onAnalyze() {},
  }));
  assert.match(render("2026-10-25T00:00:00Z"), /Rest of Week · limited days remaining/);
  assert.match(render("2026-10-22T00:00:00Z"), /persisted games through Sunday Pacific Time/);
});

test("impact analysis is fixed to the chosen drop and never offers alternate-drop controls", () => {
  const { ImpactContent } = load();
  const html = renderToStaticMarkup(React.createElement(ImpactContent, {
    impact: {
      model_version: "waiver-evidence-phase3",
      candidate: candidate(1, "Available Center", drop(2)),
      comparison: drop(2),
      limitations: [],
    },
    selectedDropId: 2,
  }));
  assert.match(html, /Selected drop comparison/);
  assert.match(html, /drop Weak Guard/);
  assert.match(html, /starting-slot compatibility/i);
  assert.doesNotMatch(html, /Compare dropping/);
});

test("roster selection, mode controls, stale loading and error states stay explicit", () => {
  const replacement = board(2);
  const states = ["this_week", board(), { mode: "this_week", dropId: 2, board: replacement }, 2, null, false, false, "", "", 0];
  const { WaiverCenter } = load(states);
  const html = renderToStaticMarkup(React.createElement(WaiverCenter));
  assert.match(html, /<h1>Waiver Command Center<\/h1><p>Box Score Bully<\/p>/);
  assert.match(html, /Who should I replace/);
  assert.match(html, /Weak Guard/);
  assert.match(html, /name="selected-drop"/);
  assert.match(html, /name="waiver-mode" checked=""\/>Rest of Week/);
  assert.match(html, /Next 7 Days/);
  assert.match(html, /Season Evidence/);
  assert.doesNotMatch(html, /ROS|ROS Projection|FAAB unavailable|confidence/);
  assert.match(html, /Continual rolling list/);
  assert.match(html, /2-day waiver period/);
  assert.match(html, /4 adds\/week/);
  assert.match(html, /Daily - Today deadline/);
  assert.doesNotMatch(html, /Stale deployed version/);
  assert.doesNotMatch(html, /FAAB/);
  assert.match(html, /<select/);
  assert.doesNotMatch(html, /Selected Team|My Team|FAAB/);

  const emptyStates = ["this_week", null, null, null, null, true, false, "", "", 0];
  const emptyHtml = renderToStaticMarkup(React.createElement(load(emptyStates).WaiverCenter));
  assert.match(emptyHtml, /Loading persisted waiver evidence/);
  assert.match(emptyHtml, /Loading replacements for the selected player/);
});

test("routes, GET-only replacement API, Pacific time, responsive overflow and modal focus are wired", () => {
  assert.match(app, /path="\/waivers" element={<WaiverCenter/);
  assert.match(api, /getWaiverReplacements/);
  assert.match(api, /\/waivers\/replacements/);
  assert.match(api, /drop_player_id/);
  assert.match(source, /api\.getWaiverImpact\(playerId, mode, dropPlayerId/);
  assert.match(source, /controller\.abort\(\)/);
  assert.match(source, /element\?\.showModal\(\)/);
  assert.match(source, /previousFocus\.focus\(\)/);
  assert.match(source, /onCancel={onClose}/);
  assert.match(source, /autoFocus/);
  assert.doesNotMatch(source, /api\.(addPlayer|dropPlayer|executeTransaction)/);
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.waiver-center/);
  assert.match(css, /\.waiver-table-scroll[^}]*overflow-x: auto/);
  assert.match(css, /\.waiver-center :focus-visible/);
});

const transactionAnalysis = (best = null) => {
  const add = candidate(1, "Available Center", drop(4, 5), { recommended_action: "WATCH" });
  const swap = {
    add_player: add, drop_player: roster[1], mode: "this_week", decision: "WATCH",
    comparison: add.comparison, reasons: ["Limited current-season evidence"], limitations: ["Partial schedule"],
  };
  return {
    team_name: "Box Score Bully", mode: "this_week", model_version: "waiver-evidence-phase3", decision: best ? "ADD" : "HOLD",
    best_transaction: best ? { ...swap, decision: "ADD" } : null,
    watch_transactions: [swap], top_supported_transactions: [],
    evaluated_pair_count: 20, supported_pair_count: 0, watch_pair_count: 1, excluded_pair_count: 20,
    excluded_pair_reasons: { "Limited sample": 20 }, data_quality: {},
    acquisition_context: { rules: ["Continual rolling list"], detail: "Weekly adds unverified." },
  };
};

test("global HOLD is first class and positive WATCH is not promoted", () => {
  const { TransactionSummary } = load();
  const html = renderToStaticMarkup(React.createElement(TransactionSummary, {
    analysis: transactionAnalysis(), onAnalyze() {},
  }));
  assert.match(html, /BEST MOVE NOW/);
  assert.match(html, /<h3>HOLD<\/h3>/);
  assert.match(html, /No supported waiver transaction currently clears the evidence threshold for Box Score Bully/);
  assert.match(html, /WATCHLIST/);
  assert.match(html, /WATCH: Available Center \/ drop Bench Forward/);
  assert.match(html, /20 pairs evaluated/);
  assert.doesNotMatch(html, /VIEW ANALYSIS|Best Add|confidence|ROS Projection/);
});

test("supported transaction summary renders exact add/drop and evidence with GET-only API", () => {
  const { TransactionSummary } = load();
  const html = renderToStaticMarkup(React.createElement(TransactionSummary, {
    analysis: transactionAnalysis(true), onAnalyze() {},
  }));
  assert.match(html, /ADD: Available Center/);
  assert.match(html, /DROP: Bench Forward/);
  assert.match(html, /Positive measured change/);
  assert.match(html, /\+5 descriptive model-index points/);
  assert.match(html, /VIEW ANALYSIS/);
  assert.match(html, /Starting-slot coverage/);
  assert.match(html, /WHY/);
  assert.match(html, /RISKS/);
  assert.match(api, /getWaiverTransactions/);
  assert.match(api, /\/waivers\/transactions/);
  assert.match(source, /comparison: swap.comparison/);
  assert.match(source, /selectedDropId={swap.drop_player.player_id}/);
});

test("incompatible model versions fail closed for board, replacement and transaction surfaces", () => {
  const { WaiverResults, Replacements, TransactionSummary } = load();
  const staleBoard = { ...board(), model_version: "waiver-evidence-v2" };
  const boardHtml = renderToStaticMarkup(React.createElement(WaiverResults, {
    board: staleBoard, onAnalyze() {},
  }));
  const replacementHtml = renderToStaticMarkup(React.createElement(Replacements, {
    board: staleBoard, loading: false, error: "", selectedDropId: 2, onAnalyze() {},
  }));
  const transactionHtml = renderToStaticMarkup(React.createElement(TransactionSummary, {
    analysis: { ...transactionAnalysis(true), model_version: "waiver-evidence-v2" }, onAnalyze() {},
  }));
  for (const html of [boardHtml, replacementHtml, transactionHtml]) {
    assert.match(html, /role="alert"/);
    assert.match(html, /incompatible model waiver-evidence-v2/);
    assert.doesNotMatch(html, /ADD: Available Center|WATCH: Available Center|Best Supported Transaction/);
  }
});

test("impact surfaces reject stale model responses instead of rendering player recommendations", () => {
  const { ImpactContent } = load();
  const html = renderToStaticMarkup(React.createElement(ImpactContent, {
    impact: {
      league_key: "league", team_key: "team", mode: "this_week",
      model_version: "waiver-evidence-v2", candidate: candidate(1, "Available Center"),
      comparison: drop(2), limitations: [],
    },
    selectedDropId: 2,
  }));
  assert.match(html, /role="alert"/);
  assert.match(html, /Impact evidence uses incompatible model waiver-evidence-v2/);
  assert.doesNotMatch(html, /Available Center: add\/drop analysis/);
});

test("structured 409 mismatch details and non-JSON errors remain readable", async () => {
  const originalFetch = globalThis.fetch;
  const { ApiError, api: client } = loadApi();
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "String API error" }), { status: 400 });
    await assert.rejects(client.getWaivers("this_week"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 400);
      assert.match(error.message, /String API error/);
      return true;
    });

    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: {
        message: "Persisted league contract mismatch; waiver analysis blocked",
        mismatches: ["scoring_type: persisted 'head', expected 'headpoint'", "num_teams: persisted '10', expected '12'"],
      },
    }), { status: 409, headers: { "Content-Type": "application/json" } });
    await assert.rejects(client.getWaivers("this_week"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 409);
      assert.match(error.message, /Persisted league contract mismatch/);
      assert.match(error.message, /scoring_type: persisted 'head', expected 'headpoint'/);
      assert.match(error.message, /num_teams: persisted '10', expected '12'/);
      assert.equal(error.mismatches.length, 2);
      return true;
    });

    globalThis.fetch = async () => new Response("upstream returned plain text", { status: 502 });
    await assert.rejects(client.getWaivers("this_week"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 502);
      assert.match(error.message, /upstream returned plain text/);
      return true;
    });

    globalThis.fetch = async () => new Response(JSON.stringify({
      detail: { unknown: "server detail" },
    }), { status: 400 });
    await assert.rejects(client.getWaivers("this_week"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 400);
      assert.match(error.message, /"unknown":"server detail"/);
      return true;
    });

    globalThis.fetch = async () => { throw new TypeError("synthetic network failure"); };
    await assert.rejects(client.getWaivers("this_week"), /synthetic network failure/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

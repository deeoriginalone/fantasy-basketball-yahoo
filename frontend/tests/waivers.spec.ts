import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const evidence = { state: "partial", source: "Persisted NBA", as_of: "2026-10-25T00:00:00Z", detail: "Partial schedule and coverage." };
const roleWindow = (average: number | null, games: number) => ({
  average, median: average, games, game_ids: games ? ["game-1", "game-2"] : [], window_start: games ? "2026-10-22" : null,
  window_end: games ? "2026-10-24" : null, as_of: evidence.as_of, missing_game_ids: [], stale_game_ids: [],
});
const currentRole = {
  minutes: { quality: { ...evidence, detail: "Recent 2/3; comparison 0/3: insufficient role sample." }, recent: roleWindow(30, 2), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "minutes" },
  usage: { quality: { ...evidence, state: "unavailable" }, recent: roleWindow(null, 0), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "fraction" },
  starts: { quality: { ...evidence, state: "unavailable" }, season: "2026-27", season_starts: null, season_games: null, recent_starts: null, detail: "Season starts do not establish the current lineup." },
  quality: evidence, trend: "INSUFFICIENT EVIDENCE", season_usage: .23, season_usage_quality: evidence,
  method: "Latest three vs preceding three games, each side needs three valid fresh games. No projection.",
  limitations: ["Game-level usage and starts are unavailable."],
};
const components = { roster_fit: 72, player_value: 70, opportunity: 60, schedule: 80, acquisition_value: null };
const drop = (id: number, net = 15) => ({
  player_id: id, player_name: id === 2 ? "Weak Guard" : "Bench Forward", before_score: 66, after_score: 66 + net,
  net_improvement: net, component_before: components, component_after: { ...components, roster_fit: 72 + net },
  effective_weights: { roster_fit: .4 }, starting_slots_before: 3, starting_slots_after: 3,
  starting_slots_required: 2, component_deltas: { ...components, roster_fit: net }, reasons: ["Same measured model on both sides."],
});
const player = (id: number, name: string, dropId: number | null = 2, net = 15) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, position: id === 3 ? "G" : "C", nba_team: "DEN",
  yahoo_status: id === 3 ? null : id === 1 ? "Q" : "P", availability: "free_agent", eligible: true,
  recent: { value: 52, games: 2, season: "2026-27",
    per_game_stats: { PTS: 20, REB: 10, AST: 6, BLK: 2, STL: 3, TOV: 4 },
    scoring_weights: { PTS: 1, REB: 1.2, AST: 1.5, BLK: 3, STL: 3, TOV: -1 },
    scoring_contributions: { PTS: 20, REB: 12, AST: 9, BLK: 6, STL: 9, TOV: -4 },
    label: "Recent", sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION" },
  ros: { value: 35, games: 60, season: "2025-26", per_game_stats: {}, label: "Historical", sample_label: "EXCELLENT" },
  ranking_value: { value: 32, recent_weight: .4, historical_value: 35, historical_games: 60, historical_season: "2025-26", label: "Recent / historical blend" },
  opportunity: { minutes: 30, minutes_trend: null, usage_trend: null, historical_start_rate: null, role: "INSUFFICIENT EVIDENCE", score: null, score_parts: {}, current_role: currentRole },
  identity_mapping_state: "EXACT_NAME_TEAM",
  identity_mapping_reason: "Yahoo and NBA identity evidence agrees.",
  mapping_diagnostic: "COMPLETE_MAPPING", status_diagnostic: id === 3 ? "YAHOO_SUPPLIED_BLANK" : "STATUS_PRESENT",
  schedule: { games_remaining: 2, off_day_games: 1, back_to_backs: 1, next_7_days_games: 2, opponents: ["BOS"], window_start: "2026-10-25", window_end: "2026-10-31", coverage: "PARTIAL", freshness: "fresh", diagnostic_reason: "SCHEDULE_ROWS_PRESENT", imported_at: evidence.as_of },
  components, overall_score: 80, effective_weights: { roster_fit: .4 }, recommended_action: "WATCH", hold_type: "undetermined",
  current_season_games: 2, evidence_quality: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  comparison: dropId === null ? null : drop(dropId, net),
  best_drop_options: dropId === null ? [] : [drop(dropId, net)], net_improvement: dropId === null ? null : net,
  roster_decision: "review_replacement", reasons: ["Fits an uncovered center slot"], limitations: ["Current rolling priority unavailable"],
  data_quality: { status: { ...evidence, state: id === 3 ? "unavailable" : "partial", detail: id === 3 ? "Blank status is unknown, not healthy." : "Q/P remains uncertain." }, schedule: evidence, recent: { ...evidence, state: "partial" } },
});
const roster = [
  player(2, "Weak Guard", null),
  { ...player(4, "Bench Forward", null), position: "F", roster_decision: "review_replacement" },
];
const board = (mode = "this_week", dropId: number | null = 2, order = [1, 3]) => ({
  league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
  mode, generated_at: "2026-10-25T00:00:00Z", model_version: "waiver-evidence-phase3",
  weights: { roster_fit: .35, player_value: .25, opportunity: .15, schedule: .15, acquisition_value: .1 },
  best_add_for_team_id: null, best_overall_available_id: 1, top_measured_candidate_id: null,
  selected_drop_player_id: 2, roster, team_needs: ["Uncovered center slot"],
  waiver_rules: ["Continual rolling list", "2-day waiver period", "4 adds/week", "Daily - Today deadline"],
  selected_player_result: "WATCH",
  candidates: order.map((id) => player(id, id === 1 ? "Available Center" : "Overall Guard", dropId, id === 1 ? (dropId === 2 ? 15 : -5) : 4)),
  excluded_count: 2, unknown_availability_count: 1, limitations: ["No projections."],
  data_quality: { roster: { ...evidence, state: "stale", detail: "Stale roster." } },
  coverage, data_gaps: [],
});

const swap = () => {
  const add = player(1, "Available Center", 4, 5);
  return {
    add_player: add, drop_player: roster[1], mode: "this_week", decision: "WATCH",
    comparison: add.comparison, reasons: ["Below seven current-season games"],
    limitations: ["Partial schedule coverage; historical evidence is not a projection."],
  };
};
const transactions = (mode = "this_week") => ({
  league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
  mode, generated_at: "2026-10-25T00:00:00Z", model_version: "waiver-evidence-phase3",
  decision: "HOLD", decision_reasons: ["Insufficient current-season sample"], best_transaction: null,
  top_supported_transactions: [], watch_transactions: [{ ...swap(), mode }],
  evaluated_pair_count: 4, supported_pair_count: 0, watch_pair_count: 1,
  excluded_pair_count: 4, excluded_pair_reasons: { "Insufficient current-season sample": 4 },
  data_quality: { settings: evidence },
  acquisition_context: {
    rules: ["Continual rolling list"], data_quality: evidence,
    current_priority: null, weekly_adds_used: null, weekly_adds_remaining: null, claim_clear_at: null,
    detail: "Current priority and weekly acquisitions are unverified.",
  },
  limitations: [],
});

const metric = (count: number, total = 4) => ({ count, total, percentage: total ? count / total * 100 : 0 });
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

let failSelectedDrop: number | null = null;
let slowSelectedDrop: number | null = null;
let staleSurface: "board" | "transactions" | "replacements" | "impact" | null = null;
let structuredTransactionError = false;

test.beforeEach(async ({ page }) => {
  failSelectedDrop = null;
  slowSelectedDrop = null;
  staleSurface = null;
  structuredTransactionError = false;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    expect(route.request().method()).toBe("GET");
    expect(url.searchParams.has("team_key")).toBe(false);
    expect(url.searchParams.has("league_key")).toBe(false);
    if (url.pathname === "/api/v1/waivers/transactions") {
      if (structuredTransactionError) {
        await route.fulfill({ status: 409, json: { detail: {
          message: "Persisted league contract mismatch; waiver analysis blocked",
          mismatches: ["scoring_type: persisted head, expected headpoint", "num_teams: persisted 10, expected 12"],
        } } });
        return;
      }
      const result = transactions(url.searchParams.get("mode") ?? "this_week");
      if (staleSurface === "transactions") result.model_version = "waiver-evidence-v2";
      await route.fulfill({ json: result });
    } else if (url.pathname.endsWith("/impact")) {
      const selected = Number(url.searchParams.get("drop_player_id"));
      const version = staleSurface === "impact" ? "waiver-evidence-v2" : "waiver-evidence-phase3";
      await route.fulfill({ json: {
        league_key: "478.l.50505", team_key: "478.l.50505.t.9", mode: url.searchParams.get("mode"),
        model_version: version,
        candidate: player(1, "Available Center", selected), comparison: drop(selected), limitations: [],
      } });
    } else if (url.pathname === "/api/v1/waivers/replacements") {
      const selected = Number(url.searchParams.get("drop_player_id"));
      if (slowSelectedDrop === selected) await new Promise((resolve) => setTimeout(resolve, 500));
      if (failSelectedDrop === selected) {
        await route.fulfill({ status: 503, json: { detail: "Replacement evidence unavailable" } });
        return;
      }
      const order = selected === 4 ? [3, 1] : [1, 3];
      const result = board(url.searchParams.get("mode") ?? "this_week", selected, order);
      if (staleSurface === "replacements") result.model_version = "waiver-evidence-v2";
      await route.fulfill({ json: result });
    } else if (url.pathname === "/api/v1/waivers") {
      const result = board(url.searchParams.get("mode") ?? "this_week");
      if (staleSurface === "board") result.model_version = "waiver-evidence-v2";
      await route.fulfill({ json: result });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Unexpected API call" } });
    }
  });
});

test("roster choice updates ranking, mode preserves it, and dialog uses exactly that drop", async ({ page }) => {
  const writes: string[] = [];
  const replacementRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/") && request.method() !== "GET") writes.push(request.url());
    if (request.url().includes("/waivers/replacements?")) replacementRequests.push(request.url());
  });
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "Waiver Command Center" })).toBeVisible();
  await expect(page.locator(".waiver-heading")).toContainText("Box Score Bully");
  await expect(page.getByText(/Stale deployed version/)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "BEST MOVE NOW" })).toBeVisible();
  const acquisitionDetails = page.locator("details").filter({ has: page.getByText("Evidence and acquisition context", { exact: true }) });
  await acquisitionDetails.locator("summary").click();
  await expect(acquisitionDetails.getByText("Continual rolling list", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("FAAB");
  const replacement = page.locator(".waiver-replacement-card").first();
  await replacement.getByText("Exact Fantasy PPG inputs and contributions").click();
  await expect(replacement).toContainText("Total 52 fantasy PPG");
  await expect(replacement).toContainText("WATCH");
  await expect(page.getByRole("heading", { name: "Who should I replace?" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Weak Guard/ })).toBeChecked();
  await expect(page.locator(".waiver-replacement-card").filter({ has: page.getByRole("heading", { name: "Overall Guard", exact: true }) })).toContainText("Yahoo status: Unknown status");
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  await expect(page.getByText("INSUFFICIENT FOR STRONG RECOMMENDATION").first()).toBeVisible();
  await expect(page.getByText(/historical, not a projection/).first()).toBeVisible();
  await expect(page.getByText(/All available players/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Best Overall Available" })).toHaveCount(0);

  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByRole("heading", { name: "Overall Guard", exact: true })).toBeVisible();
  await expect(page.getByText("Selected drop", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Bench Forward");
  expect(replacementRequests.some((request) => request.includes("drop_player_id=4"))).toBe(true);

  const nextWeekRequest = page.waitForRequest((request) =>
    request.url().includes("/waivers/replacements?") && request.url().includes("drop_player_id=4") && request.url().includes("mode=next_7_days"));
  await page.getByRole("radio", { name: "Next 7 Days", exact: true }).check();
  await nextWeekRequest;
  await expect(page.getByRole("radio", { name: "Next 7 Days", exact: true })).toBeChecked();
  await expect(page.getByRole("radio", { name: /Bench Forward/ })).toBeChecked();
  await expect(page.getByText("Next 7 Days: today through today + 6", { exact: false })).toBeVisible();

  const opener = page.getByRole("button", { name: "Analyze option: Overall Guard" }).first();
  const impactRequest = page.waitForRequest((request) =>
    request.url().includes("/impact?") && request.url().includes("drop_player_id=4") && request.url().includes("mode=next_7_days"));
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await impactRequest;
  await expect(dialog).toContainText("drop Bench Forward");
  await expect(dialog.getByRole("button", { name: /Compare dropping/ })).toHaveCount(0);
  await expect(dialog.getByText("Selected drop comparison")).toBeVisible();
  await expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();

  await page.getByText(/All available players/).click();
  const region = page.getByRole("region", { name: /Waiver candidates/ });
  await expect(region).toBeVisible();
  expect(await region.evaluate((element) => element.scrollWidth >= element.clientWidth)).toBe(true);
  const viewportWidth = page.viewportSize()!.width;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewportWidth);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(writes).toEqual([]);
});

test("a pending older selection cannot replace the newer selection result", async ({ page }) => {
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  slowSelectedDrop = 4;
  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByRole("status").filter({ hasText: "Loading replacements" })).toBeVisible();
  await page.getByRole("radio", { name: /Weak Guard/ }).check();
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Weak Guard");
  await expect(page.locator(".waiver-replacement-card").first()).not.toContainText("Bench Forward");
});

test("global HOLD separates WATCH and opens the exact optimizer pair without changing selected drop", async ({ page }) => {
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "BEST MOVE NOW" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toBeVisible();
  await expect(page.getByText(/No supported waiver transaction currently clears the evidence threshold for Box Score Bully/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "WATCHLIST" })).toBeVisible();
  const summary = page.locator("section").filter({ has: page.getByRole("heading", { name: "BEST MOVE NOW" }) });
  await expect(summary).toContainText("Why not add: current-season sample is below the existing seven-game eligibility gate");
  await page.getByText("Current role and schedule evidence: Available Center").click();
  await expect(summary).toContainText("Role evidence: INSUFFICIENT EVIDENCE");
  await expect(summary).toContainText("Recent 2/3; comparison 0/3");
  await expect(summary).toContainText("Coverage: PARTIAL");
  await expect(summary).toContainText("Recent starts: Unavailable");
  await expect(page.getByRole("radio", { name: /Weak Guard/ })).toBeChecked();
  const opener = page.getByRole("button", { name: "View watch analysis: Available Center / Bench Forward" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Supported transaction analysis" });
  await expect(dialog.getByRole("button", { name: "Close transaction analysis" })).toBeFocused();
  await expect(dialog).toContainText("hypothetical ADD Available Center / DROP Bench Forward");
  await expect(dialog).toContainText("drop Bench Forward");
  await expect(dialog).toContainText("5.0");
  await dialog.locator("summary").filter({ hasText: "Exact Fantasy PPG inputs and contributions" }).first().click();
  await expect(dialog).toContainText("Total 52 fantasy PPG");
  await expect(dialog).toContainText("CURRENT ROLE");
  await expect(dialog).toContainText("Yahoo Q");
  await expect(dialog).toContainText("normalized status: P");
  await expect(dialog).toContainText("No injury-return date is inferred");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await expect(page.getByRole("radio", { name: /Weak Guard/ })).toBeChecked();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test("global supported summary uses backend winner and transaction read errors do not become HOLD", async ({ page }) => {
  await page.route("**/api/v1/waivers/transactions?**", (route) => route.fulfill({ json: {
    ...transactions(), decision: "ADD", best_transaction: { ...swap(), decision: "ADD" },
  } }));
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "ADD: Available Center", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "VIEW ANALYSIS", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Supported transaction analysis" })).toContainText("DROP Bench Forward");
  await page.keyboard.press("Escape");
  await page.route("**/api/v1/waivers/transactions?**", (route) => route.fulfill({ status: 409, json: { detail: "Persisted contract mismatch" } }));
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByText("Persisted contract mismatch", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
});

test("model-version mismatch blocks only the affected decision surface", async ({ page }) => {
  staleSurface = "transactions";
  await page.goto("/waivers");
  const transactionPanel = page.locator("section").filter({ has: page.getByRole("heading", { name: "BEST MOVE NOW" }) });
  await expect(transactionPanel.getByRole("alert")).toContainText("incompatible model waiver-evidence-v2");
  await expect(transactionPanel.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();

  staleSurface = "board";
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByText(/Stale deployed version: waiver-evidence-v2/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toHaveCount(0);
  await expect(page.locator(".waiver-replacement-card")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Who should I replace?" })).toBeVisible();
});

test("stale replacement and impact responses cannot expose decision-ready advice", async ({ page }) => {
  staleSurface = "replacements";
  await page.goto("/waivers");
  await expect(page.locator("#waiver-replacements").locator("..").getByRole("alert"))
    .toContainText("incompatible model waiver-evidence-v2");
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toHaveCount(0);

  staleSurface = "impact";
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Analyze option: Available Center" }).click();
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("alert")).toContainText("incompatible model waiver-evidence-v2");
  await expect(dialog.getByText("Available Center: add/drop analysis")).toHaveCount(0);
});

test("structured 409 settings mismatch stays an accessible error, never HOLD", async ({ page }) => {
  structuredTransactionError = true;
  await page.goto("/waivers");
  const alert = page.getByRole("alert").filter({ hasText: "Persisted league contract mismatch" });
  await expect(alert).toContainText("Persisted league contract mismatch; waiver analysis blocked");
  await expect(alert).toContainText("scoring_type: persisted head, expected headpoint");
  await expect(alert).toContainText("num_teams: persisted 10, expected 12");
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
});

test("replacement errors and base errors are accessible and recover on reload", async ({ page }) => {
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  failSelectedDrop = 4;
  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByText("Replacement evidence unavailable", { exact: false })).toBeVisible();
  await expect(page.locator(".waiver-replacement-card")).toHaveCount(0);
  failSelectedDrop = null;
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();

  await page.route("**/api/v1/waivers?**", (route) => route.fulfill({ status: 503, json: { detail: "Persisted evidence unavailable" } }));
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByText("Persisted evidence unavailable", { exact: false })).toBeVisible();
});

test("mode controls stay available, Pacific window is explicit, and saved targets cannot override manager", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("team_key", "478.l.50505.t.1");
    localStorage.setItem("league_key", "other.league");
  });
  const responsePromise = page.waitForResponse((response) => response.url().includes("/api/v1/waivers?"));
  await page.goto("/waivers?league_key=other.league&team_key=478.l.50505.t.1");
  const response = await responsePromise;
  expect(new URL(response.url()).searchParams.get("mode")).toBe("this_week");
  expect(await response.json()).toMatchObject({ league_key: "478.l.50505", team_key: "478.l.50505.t.9" });
  await expect(page.getByText(/Rest of Week · limited days remaining/)).toBeVisible();
  await expect(page.getByText(/today through today \+ 6/)).toHaveCount(0);
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "Season Evidence", exact: true })).toBeVisible();
});

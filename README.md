# Fantasy Basketball GM

Docker-first Yahoo Fantasy Basketball application with a React Draft Room,
FastAPI services, and PostgreSQL persistence. Yahoo is authoritative for
fantasy-league/player identity, configuration, and state; persisted NBA and
authorized external data provide basketball inputs.

## Current Product Behavior

The final draft-era baseline preserves the draft module and its history.
**Championship HQ** is the post-draft development direction, not an implemented
post-draft analytics product. See the [ordered roadmap](docs/status/next-actions.md).

- **Yahoo Mock Practice:** one-time Windows observer install/pair, then join a
  12-team Yahoo mock, paste its draft URL, and Connect. Verified rounds and
  manager slot are required. Observations pass through the
  canonical normalizer/reconciler into disposable practice sessions. The
  observer never selects players in Yahoo; browser-based Production Live writes
  are not enabled.
- **Internal practice:** seeded rule-based mocks and synthetic sync rehearsal
  reuse persisted draft calculations and events. Neither validates Yahoo Live.
- **Production Live:** official authenticated `draftresults` polling, Sync Now,
  pause/resume, Quick Record/manual fallback, and conflict protection are
  implemented. Active-draft provider behavior and full manual recovery browser
  acceptance remain unverified; mock acceptance does not establish them.
- **Recommendations:** BEST PICK NOW ranks current adjusted roster value;
  WAIT ANALYSIS separately evaluates ADP/survival/fallback. ADP does not directly
  determine BEST PICK NOW. Only manager selections populate manager-roster
  inputs; all picks affect availability. Why this rank explains roster-driven
  effects, not accuracy. Historical production is not a future-season projection,
  small score differences do not prove player superiority, and survival/wait
  remains uncalibrated.
- **Status/data:** Yahoo O/NA are excluded from normal recommendations, best
  value at risk, and wait fallbacks. Q/P remain eligible with uncertainty;
  blank/unrecognized status is unknown, not healthy. Refresh is import-based,
  not continuous injury monitoring. Historical metrics remain visible.
  Missing/stale inputs, unmapped/unscored players, partial ADP, and preseason
  samples remain explicit limitations; no values or recovery forecasts are
  invented.

The Windows observer runs windowless/background with loopback-only CDP on the
dedicated Chrome PC and bounded sanitized logs. Never expose CDP on the LAN.
See the [observer workflow](scripts/yahoo-observer/README.md),
[dated current-state evidence](docs/status/current-state.md), and
[draft-day checklist](docs/draft-day-checklist.md).

The backend owns calculations and decisions; the frontend prioritizes actions
and explanations; decision history supports audit and learning.
**Never surface a statistic as a primary result without explaining why it
matters to this roster/matchup and what decision it informs.**

## Run

1. Copy `.env.example` to `.env`, configure Yahoo credentials, a PostgreSQL password, OAuth state secret, encryption key, and the registered HTTPS callback.
2. Build and start the stack with `docker compose up --build`.
3. Open `https://192.168.0.85:18002` for the Draft Room or append `/docs` for the API. Trust the local Caddy root certificate on the client before completing OAuth. Never commit `.env` or `caddy-root.crt`.

The API has no general user authentication and must stay on a trusted network.

To export and validate the public root certificate currently used by Caddy, run `scripts/export-caddy-root.sh`. It checks the root CA flag, validates the served TLS chain and configured host name/IP, prints certificate details, and writes only the public root to the ignored `caddy-root.crt`. It does not install trust or export private keys. See the [draft-day checklist](docs/draft-day-checklist.md) for safe client-trust guidance; never bypass TLS validation.

## Draft Workflow

1. Refresh NBA data and season stats: `POST /api/v1/nba/import?season=2026-27&recent_days=30`.
2. Build league-specific per-player draft metrics: `POST /api/v1/draft/metrics?league_key=478.l.50505&season=2026-27`.
3. Submit the manager team, players already drafted, and available Yahoo-pool player identity IDs to `POST /api/v1/draft/utility`.

Example request body:

```json
{
  "league_key": "478.l.50505",
  "team_key": "478.l.50505.t.9",
  "season": "2026-27",
  "draft_position": 9,
  "round_number": 2,
  "total_teams": 12,
  "drafted_player_ids": [10001, 10002],
  "available_player_ids": [10003, 10004],
  "recent_pick_player_ids": [10001, 10002],
  "adp_by_player_id": {"10003": 26.5, "10004": 40.0},
  "mode": "balanced"
}
```

The v1 endpoint returns the roster-best pick, best value at risk before the next turn, snake timing, positional runs, per-player availability assessments, component scores, explanations, and any IDs it could not score. It remains stateless and backward compatible. Recent pick IDs must be ordered oldest to newest; run detection examines the last ten.

For each player with ADP and draft timing, `market_value_delta = ADP - current_pick_number`: positive is a market reach, negative means the player has fallen past ADP. `reach_score` and `fall_score` range from 0 to 100 and scale each direction against one league round; they are descriptive heuristic indices, not probabilities or utility inputs. `expected_loss_if_gone` is the nonnegative `wait_utility_now` at stake. `expected_wait_cost` and its compatible alias `opportunity_cost_if_wait` use fallback expectation and can be positive, zero, negative, or unavailable. The best roster-fit player and the player with greatest positive expected wait cost are selected independently. Fantrax supplies no draft-rank field; the response says that comparison is unavailable. Opponent roster demand is not an input; only available pick history, market ADP, and the existing heuristic run signal inform survival.

### Persisted Draft Sessions (v2)

Use v2 when a draft should survive reloads. The regular `POST /api/v2/draft/sessions` route remains strict and requires a complete explicit team-slot map. Live Draft creation uses `POST /api/v2/draft/live-sessions` and permits a pending manager position and partial/empty opponent mapping. First-round picks from the existing Yahoo `draftresults` poll progressively establish authoritative team slots; later-round picks are validated against known slots but do not infer unknown order. Setting the manager slot is a deliberate action before manager timing and recommendations are enabled. Conflicts retain source evidence and stop automatic order discovery until manually resolved through `PUT /api/v2/draft/sessions/{session_id}/order`. `GET /api/v2/draft/sessions/{session_id}` reloads picks, targets, order state, session version, and the latest recommendation snapshot.

```json
{
  "league_key": "<imported-yahoo-league-key>",
  "season": "2026-27",
  "manager_team_key": "<manager-team-key>",
  "draft_position": 3,
  "total_teams": 4,
  "rounds": 13,
  "team_slots": {
    "<yahoo-team-key-for-slot-1>": 1,
    "<yahoo-team-key-for-slot-2>": 2,
    "<manager-team-key>": 3,
    "<yahoo-team-key-for-slot-4>": 4
  },
  "mode": "balanced"
}
```

Record the next overall pick with `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}` and `{ "selected_player_id": 10001, "expected_version": 0 }`. The service verifies that the player belongs to the imported Yahoo pool, derives the snake round/team slot from the overall pick, rejects out-of-order selections, and serializes updates with a session row lock. Repeating the same pick is idempotent. Stale versions return HTTP 409. Correct a pick with `PUT` on the same resource; undo only the latest pick with `POST .../{overall_pick}/undo`. The final configured pick marks the session completed; completed sessions reject new picks but still allow corrections and latest-pick undo. Undoing the final pick reopens the session. Each mutation appends an audit event and a recommendation snapshot in the same transaction.

Targets use `PUT` and `DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}` with statuses `target`, `priority`, `watch`, or `avoid`; writes require the expected session version. An unchanged target `PUT` is a no-op. A changed target advances the session version and records a snapshot so target annotations remain tied to the corresponding room revision; it retains the existing recommendation recalculation behavior. Snapshots preserve the input state, ordered pick/source evidence, target annotations, and calculation response. On reads, survival and dependent wait-cost fields are marked unavailable once the stored ADP retrieval time exceeds the freshness limit; the historical snapshot itself is not changed. Process assessment and realized player outcomes are not yet evaluated.

For player A, the wait model uses the top five other scored candidates by `wait_utility_now` (roster utility plus mode adjustment, excluding the direct positional-run bonus). It estimates the fallback as the expected highest-utility alternative available at the next turn, assuming independent survival estimates. If alternatives are utility-ordered, `E_fallback = Σ_i [p_i × Π_{j<i}(1-p_j)] × U_i`; the probability no listed fallback survives contributes zero. Then `E_wait = P(A survives) × U(A) + P(A gone) × E_fallback`, and `expected_wait_cost = U(A) - E_wait`. Positive cost yields `draft_now`, zero/negative yields `wait`, and missing player/fallback survival yields `insufficient_evidence`. Run pressure affects pick ranking and survival but is excluded from `wait_utility_now`, so it is not added twice to wait value. Utility is held constant through intervening picks. These estimates are low-confidence, uncalibrated heuristics; no frequency or correlation data is available. The wait action does not apply the old 50% survival threshold. See [ADR 0006](docs/adr/0006-draft-survival-and-wait-method.md).

### Yahoo Mock Practice

This browser-observed practice flow is separate from the internal Mock Live
Draft simulator below. Install and pair the Windows observer once. For each
practice draft, join the Yahoo mock yourself, copy its draft URL, paste it into
Court IQ, and choose **Connect**. The read-only observer uses a dedicated Chrome
profile and loopback-only CDP on Windows; it reads authoritative
`.ys-player[data-id]` entries from Yahoo Picks and sends observations over
trusted HTTPS. Court IQ runs them through the existing normalization and
reconciliation path into a disposable Yahoo Mock Practice session.

Normal operation is windowless/background after pairing: no per-draft
PowerShell, Python commands, session UUID handoff, full opponent mapping, or
observer-secret re-entry. Missing evidence fails closed and asks only for the
single slot value when needed. The observer never selects players in Yahoo.
Keep CDP bound to Windows `127.0.0.1`; never expose it on the LAN. See the
[Windows observer workflow](scripts/yahoo-observer/README.md).

### Internal Mock Live Draft

The setup page explicitly separates **Mock Live Draft** from **Live Draft**. A mock session uses the selected imported Yahoo league, manager team, explicit team-slot order, rounds, roster/scoring settings, internal Yahoo player IDs, and the existing persisted v2 board and utility engine. It is stored as `session_type: "mock"` using the existing `draft_source: "internal_mock"` discriminator; it is excluded from the live-session list and never writes to Yahoo roster/source-of-truth data.

In the mock room, **Auto Pick Next** simulates one opponent pick, **Auto Pick Until My Turn** stops before the manager's slot, and the manager selects their own player from the available board. Pause/resume, latest-pick undo, reset, start-new-mock, and removal are available. Reset starts a new attempt with the same league/slot/rules and retains the prior session; removal deletes only a standalone mock. Batch-managed runs cannot be individually removed.

Opponent selection uses fresh stored ADP when available, positional need/scarcity from the existing board and seeded randomness. If ADP is missing, no ADP is invented: the backend uses its scored board ranking when available and marks that fallback in pick evidence and the room. If there is no ADP or scored board row, the available-pool fallback is separately labeled. Picks use the same sequential v2 persistence, unique-player checks, version checks, roster construction, recommendations, run detection, and snapshots. Existing mock-batch APIs/workers remain available separately.

An opt-in single-run **Mock Sync Rehearsal** creates virtual opponent picks without first writing them as local picks. It serializes Yahoo-shaped snapshots through the production normalizer and sequential reconciler, and can hold/release delivery to exercise delayed source catch-up. The rehearsal does not contact Yahoo or modify Yahoo roster/source-of-truth data.

### Live Draft

Choose **Live Draft** explicitly to create a persisted v2 live room (`POST /api/v2/draft/live-sessions`). The shared room displays the current pick/round/team on clock, next manager turn, recommendations, available board, roster, targets, recent picks, and corrections/undo. Record actual picks manually as they happen; each write remains sequential and requires the current `expected_version`, with HTTP 409 conflicts preserved.

Authenticated Yahoo `draftresults` polling and sequential reconciliation are implemented for linked live sessions. Polling uses `LIVE_DRAFT_POLL_INTERVAL_MS` at frontend image build time, with a conservative 60-second default and bounded backoff after request/source failures. This interval is an application default, not a Yahoo-approved cadence. The room provides Sync Now and pause/resume controls; reconciliation confirms matching local picks, appends only contiguous source picks through the existing v2 event/version/snapshot pipeline, and stops on conflicts. This is polling, not push streaming. No active Yahoo draft or `draftresults` response has been exercised, so automatic production synchronization remains unverified. Production Live retains the official `draftresults` path, Sync Now, Quick Record/manual entry, and conflict protection. Yahoo Mock Practice does not verify production `draftresults`; Live browser observation is not a browser-write path.

Opponent names are not required to start a Live Draft. Unknown positions remain visibly pending; round-one source picks fill order slots progressively, while the manager confirms their position before turn timing is shown. A full manual order editor is available for explicit conflict resolution.

The Live Draft Quick Record field is focused when a live room opens. Search ignores case, punctuation, and accents; Up/Down select a match, Enter records it, and Escape clears or exits. It displays the next pick/team and keeps recommendations visible. Latest-pick undo and corrections remain in Recent Picks.

See the executable [draft-day checklist](docs/draft-day-checklist.md) before the live event. Changing `LIVE_DRAFT_POLL_INTERVAL_MS` in `.env` requires rebuilding/recreating the frontend image. No faster cadence should be described as provider-approved without direct supporting evidence.

### PostgreSQL Migrations

The v2 draft tables are versioned separately from the legacy metadata bootstrap. Startup creates the established legacy tables, then applies pending migration revisions transactionally. Apply manually with:

```bash
docker compose run --build --rm --no-deps api python -m app.core.migrations upgrade
```

On a disposable database only, rollback the new draft tables with `docker compose run --rm --no-deps api python -m app.core.migrations downgrade base`; the next app startup reapplies pending migrations. This downgrade deletes draft sessions, picks, audit events, snapshots, and targets. Existing pre-v2 schema still uses the legacy bootstrap and is not covered by a baseline migration. See [ADR 0005](docs/adr/0005-draft-state-persistence.md).

The Yahoo player payloads currently do not contain market ADP, draft rank, XRank, or ownership fields. Supply ADP values for available internal player IDs in `adp_by_player_id`; players without ADP or draft timing have null next-pick survival estimates. Survival compares ADP with your next snake-draft pick and adjusts for league size, an available draft-frequency value, and active positional runs. Fantrax does not supply draft frequency, so that input remains null and does not alter its estimates. These are heuristic, uncalibrated estimates. Modes are `balanced`, `upside`, and `safe`.

### Draft-market sync and diagnostics

Fantrax's documented public REST API is the selected personal-use ADP source. Sync current NBA ADP without a manual file:

```bash
docker compose run --build --no-deps --rm api python -m app.services.draft.market_sync --season 2026-27
docker compose run --no-deps --rm api python -m app.services.draft.market_diagnostics --season 2026-27
```

The sync uses Fantrax's published `getAdp?sport=NBA` and `getPlayerIds?sport=NBA` JSON interfaces. It joins only on unique normalized name, current team, and position; no-team and ambiguous records are left unmatched. The player-ID endpoint supplies Fantrax ID, name, team, and position; the ADP endpoint supplies ADP, name, ID, and position. Neither endpoint supplies a source update timestamp, sample size, draft frequency, draft rank, or XRank. Data fetched more than 48 hours ago is treated as stale for survival. The provider's `ADP` field remains distinct from ranks and projections.

Fantrax's terms prohibit scraping and direct use through unpublished interfaces; this sync calls the two endpoints explicitly documented on Fantrax's developer page. The app is private and personal-use, not commercial, and the feed is not redistributed. The terms do not state a numeric API rate limit or an explicit data redistribution license; the implementation uses two sequential GETs, bounded retries, and no sharing. For any broader/commercial use, obtain written permission. The legacy manual CSV importer remains available but is not required for normal operation.

```csv
player_id,adp,draft_rank,draft_frequency
10001,24.5,20,82
10002,37.0,34,65
```

```bash
docker compose exec -T api python -m app.services.draft.market_import --season 2026-27 --source manual < draft-market.csv
```

Rows upsert by internal player, season, and source. Use a distinct `--source` label for each feed; imports never modify `player_identity`. This command requires a manually supplied file and is not the requested automatic solution.

Other candidates remain excluded: Yahoo's verified player pool has no ADP; ESPN publishes rankings/editorial draft material but its terms prohibit automated extraction absent express written permission; Sleeper's official docs did not establish an NBA ADP feed; Hashtag Basketball's public ADP is HTML and automated-use permission/stable feed were not verified; FantasyPros' free API tier is non-production; RotoWire prohibits automated extraction absent written consent; and the GitHub candidate has no declared license and predicts rather than reports ADP. No second free, documented, permitted machine-readable source has been verified. See [ADR 0004](docs/adr/0004-draft-market-source-selection.md).

Draft utility is a transparent heuristic based on Yahoo-weighted historical per-game production, replacement value, positional scarcity and need, durability, risk, upside, and roster-slot fit. It is not a projection or general player ranking.

Position need considers unfilled starting positions (including G/F), not open
UTIL or bench slots. Roster matching prioritizes starters before UTIL/bench and
credits newly filled slots even when an existing player moves through an
augmenting path. UTIL and bench retain bounded construction credit (30/100 and
10/100). Need does not force a center or any other position to rank first.
Current boards recalculate legacy roster-fit results read-only; historical
recommendation snapshots are not rewritten.

Survival uses request ADP overrides first on v1; persisted v2 sessions use fresh stored Fantrax ADP. Both use snake pick distance and recent positional runs. Fantrax supplies no draft frequency, and the survival curve has not been calibrated against an evaluation dataset. Survival confidence is `heuristic_unvalidated`; missing or stale ADP stays unknown. v1 remains stateless and exposes survival independently; v2 action semantics use expected fallback loss.

Historical engine-vs-ranking outperformance is not established. Evaluation
requires authorized historical draft state, contemporaneous ADP snapshots, and
season outcomes; local draft history does not establish Yahoo's current roster
or whether the real league has completed its draft.

## API

- `GET /api/v1/health`
- `GET /api/v1/yahoo/oauth/authorize`
- `GET /api/v1/league?league_key=...`
- `GET /api/v1/leagues`
- `POST /api/v1/players/import?league_key=...`
- `GET /api/v1/players`
- `GET /api/v1/player/{id}`
- `GET /api/v1/rosters`
- `POST /api/v1/nba/import`
- `POST /api/v1/draft/metrics`
- `POST /api/v1/draft/utility`
- `POST /api/v2/draft/sessions`
- `POST /api/v2/draft/live-sessions`
- `GET /api/v2/draft/sessions`
- `POST /api/v2/draft/mock-sessions`
- `GET /api/v2/draft/mock-sessions`
- `DELETE /api/v2/draft/mock-sessions/{session_id}` (standalone mock only)
- `POST|GET /api/v2/draft/mock-batches`
- `GET /api/v2/draft/mock-batches/{batch_id}`
- `POST /api/v2/draft/mock-batches/{batch_id}/run`
- `GET /api/v2/draft/sessions/{session_id}`
- `GET /api/v2/draft/sessions/{session_id}/board`
- `PUT /api/v2/draft/sessions/{session_id}/order`
- `POST /api/v2/draft/sessions/{session_id}/mock-action`
- `GET|POST /api/v2/draft/sessions/{session_id}/sync`
- `POST /api/v2/draft/sessions/{session_id}/sync/{pause,resume}`
- `POST /api/v2/draft/sessions/{session_id}/mock-rehearsal`
- `POST /api/v2/draft/sessions/{session_id}/mock/{pause,resume,reset}`
- `GET /api/v2/draft/sessions/{session_id}/replay?version=...`
- `POST|PUT /api/v2/draft/sessions/{session_id}/picks/{overall_pick}`
- `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}/undo`
- `PUT|DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}`

NBA provider calls happen only during imports. Player and league reads use PostgreSQL.

## Draft Room UI

The React/TypeScript Draft Room is served at `/` through Caddy and the frontend Nginx container. Nginx proxies `/api/*` and `/docs` to FastAPI on the private Compose network; the browser uses same-origin API requests. Run it with the existing `docker compose up --build` command. The Vite development proxy targets `https://localhost:18002`.

### Routes and Components

- `/` prioritizes the paired Yahoo observer URL/Connect workflow. First use
  presents observer setup; missing Mock/Real or slot evidence prompts a small
  follow-up question. Saved rooms and advanced setup remain available, and
  internal practice is a secondary action. Internal mocks use an explicit or
  previewed seeded order; Live Draft permits pending manager position and
  incomplete team mapping.
- `/draft/:sessionId` is the shared mock/live room: `DraftRoomPage` composes the decision card, roster, timing window, server-ranked board, recent picks, explanations, fallback alternatives, and data-quality panel. Mock rooms add opponent auto-pick-next, auto-pick-until-manager-turn, pause/resume, manager-selected picks, latest-pick undo, reset/new-mock, and standalone removal controls. Live rooms support sequential manual picks, correction, undo, and targets.
- Internal session setup is split into league/team selection, order/mode selection, and session creation. No team order or manager identity is guessed from Yahoo data.

### State and API Contracts

The client uses route-local React state as a cache of backend view models. The room refreshes the board every five seconds and after each successful mutation. Pick and target writes send the observed session version; HTTP 409 pauses writes and presents a reload action. Internal mock batch picks run in a serialized background worker; the room polls the same session board and displays the same backend decision view. Replay is read-only. The client never calculates utility, survival, scarcity, wait cost, roster fit, snake timing, opponent picks, or player rank.

Backend additions for the UI include explicit live-session creation, separate live/mock session lists, source-checked mock actions and standalone mock removal, server-owned timing on session state, and `GET /api/v2/draft/sessions/{session_id}/board` for the latest snapshot-backed recommendation, current server-sorted candidates, data-quality statuses, and the manager's matched roster slots. Board sort modes are `decision`, `value`, `survival`, and `name`; search and simple filters do not alter recommendations. Snapshots retain compact ranked display rows, not per-player full explanations or fallback models. Both pick flows retain session-version checks; stale writes return HTTP 409.

Loading, empty league/player-pool, API errors, draft conflicts, unavailable recommendation evidence, and unknown/stale survival have separate UI states. Yahoo OAuth is linked when no imported league is available. Recent picks, corrections, undo, and target changes are written through the existing v2 endpoints.

### Mobile and Accessibility

The desktop room uses a two-column decision/board layout; below tablet width it stacks the decision first and keeps the player table horizontally scrollable. Controls have labels, icon-only actions have accessible names, decision/status is not color-only, the correction dialog has dialog semantics, and keyboard focus/reduced-motion preferences are supported.

### Calculation Boundaries

Category fit is displayed as unavailable because no category engine exists. Survival remains `heuristic_unvalidated`; market ADP coverage is partial. Rule-based opponent selection and a mock sync rehearsal are implemented; no Monte Carlo or calibrated simulation, opponent-demand model, alerts, category calculations, or transaction automation was added.

## Scope

The draft module remains supported and preserved; this baseline does not add
post-draft features. Category/team identity, schedule utilization, projections,
Start/Sit, waivers, opponent/trade/league intelligence, a Decision Journal, and
playoff/championship planning follow the [Championship HQ roadmap](docs/status/next-actions.md).
Calibrated probabilities require historical validation first. Existing mock
simulation is not a calibrated forecast, and Production Live acceptance remains
unverified. No external provider is called by v2 session reads or calculations.
See [current state](docs/status/current-state.md),
[project memory](docs/project-memory.md), and
[draft persistence ADR](docs/adr/0005-draft-state-persistence.md).

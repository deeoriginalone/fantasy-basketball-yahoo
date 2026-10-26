# Waiver Source Integrity & Coverage — 2026-10-26

**STATUS: VALIDATED LOCALLY / NOT DEPLOYED**

The local changes add backend-owned coverage, grouped DATA GAPS, root-cause
diagnostics, a non-mutating identity worklist, schedule/status source
diagnostics, source-aware reconciliation, Waiver Center evidence presentation
and explicit fail-closed status/identity eligibility. They change local API and
view-model behavior but do not change persisted data or the deployed production
behavior. The separate Phase-3 baseline below remains deployed as recorded in
its historical recheck.

### Closeout summary

- **Implemented:** local coverage and DATA GAP diagnostics, non-mutating
  identity review, explicit status/schedule source quality, and overlapping-
  field-only reconciliation. Recommendation mathematics and persisted rows
  were not changed.
- **Validated:** automated backend, frontend, build, browser and accessibility
  checks passed. Guarded persisted acceptance exercised current local
  status/identity/root-cause logic inside the existing API application boundary
  and matched source hashes and in-memory module provenance.
- **Read-only acceptance:** the existing configured database boundary retained
  its credentials; SELECTs ran in explicit READ ONLY transactions and rolled
  back. Provider calls, persisted writes and commits were zero. Invariants and
  exact optimizer/replacements/impact equality passed.
- **Authority and limits:** Yahoo remains authoritative for fantasy identity,
  configuration, roster and status; persisted NBA sources supply basketball
  inputs. Unknown status, unresolved identity, partial/unknown schedules,
  unsupported game-level usage/starts, and unverified Yahoo matchup/
  acquisition/transaction context remain explicit limitations. A lack of
  overlapping Yahoo/NBA statistics means CROSS-SOURCE COMPARISON UNAVAILABLE.
- **Deployment:** the Source Integrity changes remain local and NOT DEPLOYED;
  the separately recorded Phase-3 baseline remains the deployed application.
- **Next evidence slice:** Slice 1 in [next actions](next-actions.md) covers
  stable identity reconciliation, existing NBA source capability, and schedule
  completeness, with no new provider.

### Source authority and comparison meaning

Yahoo is authoritative for fantasy player identity, league configuration,
scoring rules, roster state, Yahoo player status and fantasy availability.
Yahoo matchup, acquisition and waiver facts require separate verification.
Persisted NBA sources are authoritative for basketball inputs: PTS, REB, AST,
STL, BLK, TOV, MIN, game logs, NBA schedule and supported aggregate usage and
starts. A Yahoo player payload without basketball stats does not imply missing
NBA production, a missing fantasy PPG formula or an incorrect Yahoo points
formula. **CROSS-SOURCE COMPARISON UNAVAILABLE** means there is no second
persisted Yahoo statistical dataset with overlapping basketball fields for
independent cross-source value comparison.

### Dated read-only audit observations

These are observations from the previously inspected persisted snapshot, not a
new query; counts may age and must not be treated as current after the snapshot:

- Yahoo pool: **744** observations; **45** lacked NBA IDs and **2 additional
  linked identities** had Yahoo/NBA team conflicts. No mapping or team change
  was justified.
- The broader earlier audit found that 14 of the 45 unmapped records had
  same-normalized-name NBA candidates with conflicting team evidence; 31 had
  no such record in the inspected NBA player table. These observations are not
  mapping fixes.
- Existing NBA imports include `nba_games`, `player_schedule` and
  player/game identity relationships; prior foundation imports contained tens
  of thousands of player schedule rows. In the inspected waiver snapshot,
  candidates had season schedule rows even when no row applied to the selected
  Rest-of-Week window.
- `NO_PLAYER_SCHEDULE_ROWS` is distinct from an empty requested window. A
  `NO_GAMES_IN_WINDOW` result is not a verified zero without proven source
  completeness. Rows present are PARTIAL; no player rows or an unverified
  empty window are UNKNOWN; stale data is STALE. COMPLETE remains forbidden
  until an explicit completeness manifest/contract is verified. Row counts,
  all 30 teams, date span and opponent presence do not prove completeness.
- A Yahoo-supplied blank status is legitimate UNKNOWN evidence, not healthy,
  an automatic import defect, stale or injured. O/NA remain excluded, Q/P
  uncertain and blank UNKNOWN. Status diagnostics distinguish
  YAHOO_EXPLICIT_STATUS (`STATUS_PRESENT`), YAHOO_SUPPLIED_BLANK,
  STALE_YAHOO_IMPORT (`STALE_PLAYER_POOL_IMPORT`),
  PLAYER_OBSERVATION_MISSING (`MISSING_PLAYER_OBSERVATION`),
  IDENTITY_MAPPING_PROBLEM (`MAPPING_ISSUE`) and NORMALIZATION_DEFECT. Blank
  itself is not a recoverable data issue; stale/missing/mapping/normalization
  causes may indicate one.
- Persisted game logs do not establish supported game-level `USG_PCT`, `GS`
  or `START_POSITION`. Season usage and season starter-filter evidence do not
  substitute for game-level usage or recent starts; minutes do not imply starts.
  Phase 3 remains delivered: qualified minutes can support descriptive role
  while optional usage and starts retain independent unavailable states.
- The historical “0 comparable Yahoo/NBA stat pairs” result means
  **CROSS-SOURCE COMPARISON UNAVAILABLE**, not missing required Yahoo stats or
  NBA production. The earlier `MISSING_REQUIRED_STAT` wording is superseded
  where it implied a production defect.

### Durable safety and implementation status

Mapping requires stable supported evidence, such as EXACT_ID,
EXACT_NAME_TEAM, NORMALIZED_NAME_TEAM, a known alias plus team, or a supported
team change. Never fuzzy-map on name alone, overwrite Yahoo identity fields,
or auto-correct a team. Unresolved states remain reviewable with reasons.

Every UNKNOWN/UNAVAILABLE should carry the most specific supported root cause:
RESOLVABLE_INTERNAL_DEFECT, STALE_EXISTING_SOURCE, MISSING_MAPPING,
MISSING_EXISTING_SOURCE_FIELD, SOURCE_DOES_NOT_SUPPLY,
SOURCE_CONTRACT_UNVERIFIED, REQUIRES_MORE_GAMES, REQUIRES_NEW_SOURCE or
INTENTIONALLY_UNSUPPORTED. Do not label legitimate source absence as an
application bug. Source Integrity preserves the `waiver-evidence-phase3`
scoring formula, Phase-1 sample gates, Phase-2 ADD × DROP optimizer, Phase-3
role method, weights, and optimizer/replacements/impact equality. Unknown
status and unresolved identity now block strong advice and supported PASS
without changing the existing HOLD/WATCH/PASS meaning for eligible pairs.

No additional reviewed source met the current evidence, usefulness and
permission threshold for implementation; this is not a claim that every
possible public API is unusable. Yahoo remains the fantasy source, persisted
NBA data the basketball source, and Fantrax a documented ADP niche only. No new
provider was approved or implemented.

### Validation and deployment status

- Source Integrity automated validation passed locally: focused waiver and
  reconciliation tests **176 passed**; full backend **336 passed**; focused
  frontend **15 passed**; full frontend **39 passed**; strict TypeScript/Vite
  build passed; desktop/mobile Playwright plus axe **18 passed**. Backend
  results include one existing Starlette/httpx deprecation warning. The
  additional root-cause regression passed in an offline container with both
  database URLs set to an unreachable placeholder.
- Final guarded read-only persisted acceptance ran **2026-10-26 09:40:56 UTC
  / 02:40:56 PDT** against the existing persisted database. Current local
  backend source was imported in memory inside a temporary Python child of the
  existing API container; its configured database environment stayed inside
  that boundary. No app lifespan/startup ran. Every SQL statement was guarded,
  the transaction used REPEATABLE READ + READ ONLY and rolled back, and
  provider entry points and HTTP clients were blocked.
- The snapshot contained **744** Yahoo pool observations, **309** eligible
  candidates and **13** configured-roster players. Identity was resolved for
  **697/744**, unresolved for **47/744** (16 AMBIGUOUS, 31 NO_MATCH), including
  **14** same-name candidate team disagreements and **2** linked Yahoo/NBA team
  conflicts. No identity or team row was changed.
- Among eligible candidates, recent production was available for **227/309**
  and missing for **82/309**; Season Evidence was available for **287/309** and
  missing for **22/309**. Neither window had stale records. All **309/309**
  candidates had PARTIAL schedule coverage; no completeness manifest exists.
  Status was explicit for **14/309** and Yahoo-blank for **295/309**. In the
  full pool, the status observations were O **60**, NA **222**, Q **15**, P
  **6**, blank **439**, and **2** unrecognized observations representing one
  distinct token. Blank/unrecognized status remained UNKNOWN.
- Returned DATA GAPS were validated field-by-field for category, cause,
  count, denominator, percentage and reason. They reported identity
  `MISSING_MAPPING` **47/744**; recent production `REQUIRES_MORE_GAMES`
  **82/309**; Season Evidence `REQUIRES_MORE_GAMES` **22/309**; unrecognized
  status `SOURCE_CONTRACT_UNVERIFIED` **2/744**; game-level usage and recent
  game-level starts each `SOURCE_CONTRACT_UNVERIFIED` **744/744**; acquisition/
  matchup context `SOURCE_CONTRACT_UNVERIFIED` **1/1**; and free-agent versus
  waiver-claim state `SOURCE_CONTRACT_UNVERIFIED` **309/309**. Blank status was
  not labeled a defect. Empty/unverified schedule windows were not treated as
  zero games.
- All modes assessed **7,527** pairs and supported **0**. Rest of Week and
  Next 7 Days each returned **186 WATCH** pairs; Season Evidence returned
  **117 WATCH** pairs. Each mode excluded 7,527 pairs, returned HOLD and had
  `best_transaction = null`. Exclusion-reason counts overlap. Across each mode,
  the 26 pairs touching unrecognized status had zero supported actions, zero
  ADD/STREAM actions; unresolved identity had zero supported ADD/STREAM/PASS.
  Unsupported positive comparisons were WATCH or insufficient evidence.
- Exact comparison equality passed for **15** returned top-WATCH pairs (five
  per mode): optimizer == selected-drop replacements == impact, including
  pair identity, decision, blockers, all comparison fields and evidence.
  Reconciliation scanned **744** rows: **0** comparable, **697**
  `NO_COMPARABLE_STAT_FIELDS`, **45** identity mismatches and **2** team
  mismatches; `MISSING_REQUIRED_STAT` was **0**. No Yahoo basketball stat field
  overlapped the persisted NBA fields, so the result is **CROSS-SOURCE
  COMPARISON UNAVAILABLE**, not missing NBA production or fantasy PPG.
- Final safety counters: **47 SELECT**, two `SET TRANSACTION READ ONLY`, one
  repeatable-read setting, zero blocked/non-read statements, zero provider
  calls (Yahoo/NBA/Fantrax/OAuth/HTTP), zero writes, zero commits and two
  rollbacks. Selected-drop/impact equality checks issued no per-pair SQL.
- No deployment, service rebuild/recreation, restart, migration, provider
  request, OAuth action, write, Yahoo transaction action, commit or push
  occurred. The changes remain local and **NOT DEPLOYED**.

## Historical: Waiver Evidence Reliability Recheck - 2026-10-26

The Phase-3 source implementation is now deployed. The API and frontend were
rebuilt and recreated with the existing no-lifespan override; PostgreSQL and
Caddy were not restarted or recreated. Public `/waivers`, the board GET and
`GET /api/v1/waivers/transactions` returned HTTP 200. The board and transaction
contract report `waiver-evidence-phase3`; the transaction result is HOLD with
7,527 assessed pairs, zero supported pairs and six WATCH pairs. The stale-model
warning is absent. Read-only browser acceptance confirmed the persisted roster
and selected-drop comparison flow; selecting a different roster player updated
the replacement context. No ADD was forced or submitted.

The read-only board snapshot contained 309 candidates: 139 had persisted
schedule rows (PARTIAL) and 170 had no schedule rows in the selected window
(UNKNOWN, not zero); 227 had complete player identity mappings and 82 were
missing game logs. Yahoo status was present for 14 candidates and blank in the
persisted pool for 295, which remains UNKNOWN rather than healthy. Live mobile
viewport acceptance at 390 CSS pixels showed no horizontal overflow.

The then-current read-only reconciliation report was run against persisted league
`478.l.50505` inside a transaction explicitly set READ ONLY. It scanned 744
persisted Yahoo pool observations: **0 comparable**, **697 missing required
Yahoo stats** (the old report classification), **45 identity-mapping
mismatches**, and **2 team-mapping mismatches**. The zero-comparable result
means **CROSS-SOURCE COMPARISON UNAVAILABLE**: persisted Yahoo player-pool
payloads did not provide a second statistical dataset with overlapping
basketball fields. It does not indicate missing NBA production, a missing
formula, or an incorrect formula. All four acceptance-name fixtures (Keegan Murray, Bilal
Coulibaly, Kris Dunn and Jrue Holiday) were absent from the persisted candidate
set. Yahoo player-pool observations were imported at 2026-10-25 18:20:50 UTC;
NBA player rows range from 2026-10-09 10:37:52 to 2026-10-25 19:04 UTC; the
persisted NBA stats import is 2026-10-25 19:04 UTC. This was not a completed
cross-source stat-value comparison. No Yahoo/NBA provider call, OAuth action,
database write, migration, or transaction execution occurred.

Validation on this recheck: **321 backend tests passed** (one existing
Starlette/httpx deprecation warning), **12 desktop/mobile Playwright + axe
tests passed**, **35 frontend unit tests passed**, and the strict
TypeScript/Vite build passed. The report and these current counts supersede any earlier deployment or
reconciliation status below; prior player-level snapshots remain historical.

## Waiver Source Integrity & Coverage Follow-up - 2026-10-26

This section records the local worktree implementation and the final guarded
read-only acceptance below the deployed Phase-3 reliability recheck above.
**The follow-up is not deployed.** Acceptance queried existing persisted
records only and did not alter the persisted snapshot.

### Final persisted baseline and unresolved causes

- Acceptance timestamp: **2026-10-26 09:40:56 UTC / 02:40:56 PDT**. The
  independently queried Yahoo pool denominator was **744**; the service
  returned **309** eligible candidates and **13** configured-roster players.
- Identity: **697/744 resolved**, **47/744 unresolved** (16 AMBIGUOUS, 31
  NO_MATCH). Fourteen unmapped same-name candidates have conflicting team
  evidence; two additional linked records have Yahoo/NBA team conflicts.
  Direct read-only SQL evidence reproduced the linked and unlinked conflict
  counts. No name-only mapping or team correction is supported; all remain
  review items. Team disagreement is not evidence of a trade.
- Production: **227/309** candidates have recent production inputs and
  **82/309** do not; **287/309** have Season Evidence and **22/309** do not.
  No production inputs were stale. These are NBA production inputs, not Yahoo
  payload requirements.
- Status: **14/309** candidates have explicit status and **295/309** have a
  Yahoo-supplied blank. Across all **744** observations, O=60, NA=222, Q=15,
  P=6, blank=439, and two unrecognized-status observations represented one
  distinct token. Blank and unrecognized values remain UNKNOWN; O/NA are
  excluded and Q/P uncertain.
- Schedule: **309/309** eligible candidates had in-window schedule rows for
  this snapshot; each is PARTIAL because no completeness manifest exists.
  Across the full pool, 699/744 had PARTIAL rows and 45/744 had UNKNOWN
  coverage. No schedule state was COMPLETE or STALE. An empty/unverified
  window remains UNKNOWN, not verified zero.
- Role: eligible candidates had role quality **227 partial / 82 unavailable**
  (zero available or stale); game-level usage and recent starts were
  unsupported. Season-start evidence existed for 27/309, but is not
  substituted for game-level role evidence. Acquisition context was missing
  (0/1 supported).

### Local implementation and source review

The local board contract now carries backend-owned coverage with explicit
counts/denominators and percentages, separate Yahoo/NBA teams and raw Yahoo
status, identity-only mapping state/reason, a non-mutating mapping worklist,
schedule source-row counts, and grouped DATA GAPS. The Advanced Evidence UI
renders the five required categories and keeps missing values distinct from
zero, blank status distinct from healthy, and incomplete schedules distinct
from confirmed no games. No recommendation gate, scoring formula, model
version, ranking weight, sample threshold, optimizer rule or Yahoo action was
changed.

The local reconciliation utility compares only persisted fields present on
both sides. The final report used **NO_COMPARABLE_STAT_FIELDS** for **697/744**
records and kept **PARTIAL_STAT_OVERLAP** separate; the remaining 45 records
were identity mismatches and two team mismatches. `MISSING_REQUIRED_STAT` was
zero. No Yahoo stat field overlapped the persisted NBA stats, so this is
**CROSS-SOURCE COMPARISON UNAVAILABLE**, not missing NBA production, fantasy
PPG, or the scoring formula.

Source scorecard (documentation review only; no provider probes):

- Yahoo Fantasy Sports: application/OAuth and policy requirements apply;
  persisted evidence does not verify matchup, manager identity or transaction
  semantics. No new authorization/request was made.
- `nba_api` game-level usage/start endpoints: useful fields are documented in
  community-maintained materials, but the endpoint notes are old and official
  NBA terms were not verified. Research lead only.
- BALLDONTLIE free tier: does not include the required player stats, advanced
  stats, injuries or lineups; relevant features are paid.
- SportsDataIO free trial: reviewed access did not include NBA.
- API-Sports current NBA terms/free limits could not be verified; Sleeper's
  official docs cover NFL, not NBA. Kaggle licenses and coverage are
  dataset-specific and do not establish a current source.

No new source is selected. The final acceptance executed current local source
inside an isolated Python child of the existing API container, with no app
lifespan. Provider entry points and HTTP clients were blocked; SQL allowed only
SELECT and read-only/safe transaction settings. It recorded 47 SELECTs, two
read-only transactions, zero blocked statements, provider calls, writes or
commits, and two rollbacks. The 15 returned top-WATCH pairs matched exactly
across optimizer, selected-drop replacements and impact. No per-pair SQL was
issued; each mode loaded one context (15/12/12 SELECTs for This Week/Next 7
Days/Season Evidence; independent validation and reconciliation reads account
for the remainder).

Automated validation passed: focused backend waiver/reconciliation tests
**176 passed**, full backend **336 passed**, focused/full frontend **15/39
passed**, strict TypeScript/Vite build passed, and desktop/mobile Playwright
plus axe **18 passed**. The additional root-cause regression passed offline.
No provider calls/OAuth, database write, migration, deployment, Yahoo
transaction, commit or push occurred. The changes remain local and **NOT
DEPLOYED**.

## Dated Historical Implementation and Acceptance Records

Sections below record the implementation and observations as they stood on
their dates. The current Source Integrity status and final acceptance are
above; earlier snapshots, contracts and validation counts must not be read as
current evidence where a later closeout supersedes them.

### Historical Waiver Accuracy Phase 3 - Evidence Intelligence - 2026-10-25

Implemented on existing persisted inputs, with no schema/provider change.
This section supersedes the older opportunity method and numerical snapshots
below; Phase-1 scoring/sample gates and the Phase-2 optimizer remain intact.
Phase 2 remains the delivered/current optimization foundation, not obsolete.
The acceptance and suite results below are the completed Phase-3 implementation
verification, rechecked against saved output during the docs-only closeout.
They are dated observations, not a new production query or application rerun.

- Model `waiver-evidence-phase3`: all four existing GETs expose CURRENT ROLE,
  independent minutes/usage/starts/status/schedule quality, supported/missing/
  stale game IDs, dates, counts, source time and schedule coverage.
  Role is derived once per player during bulk context loading, never per pair.
- Method: latest three vs preceding three regular-season games in the existing
  Pacific 14-day lookback; each side requires three valid fresh observations.
  Both mean and median deltas >=+3.0 minutes or >=+0.02 fractional usage
  (two percentage points) give rising direction; both <=-3.0 or <=-0.02
  give falling direction. Boundaries are inclusive, applied after six-decimal
  rounding. Both strictly inside the metric's thresholds give stable direction.
  Mean/median band disagreement or opposing supported metric directions is
  insufficient, preventing a single-game spike from establishing RISING.
  With qualified minutes and no conflict, either metric rising gives RISING,
  either falling gives FALLING, otherwise STABLE. Minutes establish support; optional
  unavailable usage/starts remain independent limitations. No future role.
- Invalid/missing/stale inputs are not zero-filled or backfilled. Seven-day
  log-import/latest-game freshness, 24-hour Yahoo status freshness and existing
  critical evidence gates remain. Explicit season starter-filter GP must match
  saved starts; missing starter rows are not zero starts. Recent starts are
  unavailable; season usage is context only, never recent-window usage.
  Exactly seven days of import age, latest game exactly Pacific today minus
  seven days and exactly 24 hours of Yahoo status age remain within their
  respective boundaries; older evidence is stale. Phase-3 field states are
  `available`/`partial`/`unavailable`/`stale`; the shared contract still retains
  `missing`/`unknown`/`unsupported` for other fields.
- Opportunity is unavailable without qualified role. Qualified score parts
  count minutes level once, optional supported usage change and optional
  explicit fresh season start rate. The old extra minutes-change score is
  removed; default component weights, Yahoo formula and fixed comparison mask
  are unchanged. Missing opportunity is omitted, not replaced with neutral
  value. Opportunity-led ADD and STREAM require qualified fresh role on both
  sides; STREAM also needs fresh schedule and available opportunity. Role
  cannot bypass either player's production sample gate.
- Yahoo O/NA remain excluded, Q/P uncertain and blank UNKNOWN, not healthy.
  Schedule coverage is PARTIAL with rows, UNKNOWN without; no completeness
  manifest supports COMPLETE. No rows is not zero games. Opponents remain
  identities, not matchup difficulty. Existing cards/dialogs expose compact
  role/schedule evidence, with source calculations in expandable details.
- Read-only audit: 812 regular-season game logs in the current lookback have
  MIN 0-44, median 23, and only 1-3 games/player. No game-level USG_PCT or
  starters are persisted. Aggregate usage and some explicit season starts
  exist but cannot manufacture recent comparisons.
- Real acceptance: **HOLD in all modes**, **7,527 assessed / 0 supported /
  7,527 excluded** per mode. Positive WATCH totals are **6 Rest of Week /
  176 Next 7 Days / 183 Season Evidence**. Changed short-window descriptive
  rankings follow removal of unsupported opportunity, not weight tuning.
  Every returned WATCH add has two games and insufficient role comparison.
  Top pairs: Jrue Holiday / Dillon Brooks **+0.218907** Rest of Week;
  Keegan Murray / Dillon Brooks **+1.143485** Next 7 Days;
  Kris Dunn / P.J. Washington **+0.935267** Season Evidence.
  Murray/Coulibaly/Dunn have 2/3/2 games and cannot be ADD/STREAM/MUST ADD.
  Leading WATCH details: Holiday/Murray/Dunn recent minutes are **23.5/27/30.5**;
  each has two recent observations and zero preceding observations, so
  comparison minutes/delta and recent usage/delta remain unavailable, with
  role **INSUFFICIENT EVIDENCE**. Holiday starts are unavailable; Murray/Dunn
  have partial explicit season starts **2/2**. Murray is Q, Holiday/Dunn
  UNKNOWN. Holiday's one-day schedule is UNKNOWN; Murray's Next-7-Days
  **4 games / 2 off-days / 0 back-to-back pairs** and Dunn's season
  **78 / 5 / 13** are PARTIAL, not completeness claims or forecasts.
- Selected persisted roster player Luka Doncic: **HOLD** in all modes.
  Yahoo fantasy PPG **41.9** = 25.5 + 1.2*7 + 1.5*7 + 3*0.5 +
  3*1.5 - 8.5; two current games, 33.5 recent minutes, no preceding
  comparison/usage trend, partial schedule. Highest descriptive replacement
  nets **-0.710415 / -0.726937 / -0.283732** across the three modes,
  never a least-negative Best Add.
- **All 15 returned WATCH pairs** had exact optimizer == replacements ==
  impact comparisons and role evidence. Guarded acceptance: **363 SELECTs,
  one read-only SET, zero provider calls/writes**.
- Final validation: **139 focused / 299 full backend**, **11 focused / 35 full
  frontend**, strict TypeScript/Vite production build and **12 desktop/mobile
  Playwright + axe** tests passed. One existing backend Starlette/httpx
  deprecation warning. Initial axe heading-order regression was corrected in
  the reusable role section; all final axe checks pass.
  Full real WATCH details and audit/validation provenance are in the
  [Phase-3 session record](../sessions/2026-10-25.md#waiver-accuracy-phase-3-evidence-intelligence).
- Remaining gaps: adequate current-season comparison/production samples,
  game-level usage/starts, unknown Yahoo status, schedule completeness, richer
  authorized injury inputs, Yahoo matchup periods/ownership, current priority,
  weekly usage/remaining and claim-clear times. No FAAB, projections, numeric
  confidence, injury-return forecasts, opponent demand, history/calibration or
  execution. No refresh, OAuth, Yahoo writes, migration, deployment, commit/push.

### Historical Waiver Accuracy Phase 2 - Best Supported Transaction - 2026-10-25

This section extends Phase 1 without changing its formula, weights or evidence
gates. Earlier selected-player-only primary-workflow descriptions are superseded
by the global summary; the exact selected-drop workflow remains supported.
Phase-2 acceptance/validation numbers below are historical snapshots; the
Phase-3 evidence method and current observations above supersede them.

- Implemented read-only `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`,
  configured only for **Box Score Bully**, team **478.l.50505.t.9**, league
  **478.l.50505**. This is application configuration, **not verified
  Yahoo-authenticated ownership**. This is hypothetical add/drop analysis,
  **not Yahoo transaction history or execution**.
- One context load, in-memory pairs using the same `enrich` / `compare` engine,
  fixed percentiles, common evidence mask and bounded coverage as replacements/
  impact. Supported eligibility precedes optimization. Positive 1-6-game pairs
  remain WATCH; prior history cannot bypass gates. Supported negative/zero pairs
  are PASS; no supported positive means HOLD and null best transaction.
  MUST ADD remains unused, with no validated stronger threshold.
- HOLD is a successful decision: **HOLD -- no supported waiver transaction
  currently improves Box Score Bully**; `best_transaction=null`. It is not an
  error or optimizer failure. Positive WATCH/unsupported pairs and least-negative
  pairs cannot become the supported winner. Missing/stale mandatory evidence
  fails closed; WATCH remains separate from actionable ADD/STREAM.
- All four waiver endpoints are database-only and default to `this_week`:
  - `GET /api/v1/waivers?mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...&mode=this_week|next_7_days|ros`
  No Yahoo/NBA provider calls or writes occur during analysis.
- UI modes: **Rest of Week** (`this_week`), **Next 7 Days** (`next_7_days`),
  **Season Evidence** (`ros`). Dates use `America/Los_Angeles`, PST/PDT
  automatically. Short windows are not Yahoo matchup periods; Season Evidence
  is historical/stat-based, not a projection. Points rules and unavailable
  acquisition inputs remain as documented in the Phase-1 foundation below.
- Response: exact best pair or null, top five supported pairs, top five WATCH
  pairs, full counts, overlapping exclusion reasons, quality and factual
  acquisition context. Each pair includes both players' production, sample,
  status, opportunity/schedule evidence and exact before/after/component/
  coverage comparison. Ordering is net descending, add ID then drop ID.
- Global summary above the preserved selected-player workflow: HOLD or exact
  ADD/DROP, reasons/risks, separate WATCHLIST and VIEW ANALYSIS. The dialog
  displays the exact returned optimizer comparison; it cannot change the
  selected workflow's drop. Errors are visible, not manufactured HOLD results.
  No category objectives, acquisition cost, FAAB, forecasts or numeric confidence.
- Real saved-data acceptance: **7,527 assessed / 7,527 excluded / 0 supported**
  pairs per mode (579 non-rostered pool observations x 13 roster players;
  includes pre-excluded O/NA adds). All three modes: **HOLD**, no best transaction
  and no top supported transactions. Positive WATCH counts:
  Rest of Week **10**, Next 7 Days **45**, Season Evidence **183**.
  WATCH is excluded from the supported pool, not a recommended transaction.
- Highest WATCH comparisons: Keegan Murray / DeMar DeRozan **+0.744339**
  Rest of Week; same pair **+1.219951** Next 7 Days; Kris Dunn /
  P.J. Washington **+0.935267** Season Evidence. All add/drop samples are two
  or three games; statuses and schedules have further gaps. They are not winners.
  Murray/Coulibaly/Dunn remain subject to Phase-1 gates without player-specific rules.
- Other verified WATCH examples: Rest of Week Bilal Coulibaly / DeMar DeRozan
  **+0.618263**, Kris Dunn / DeMar DeRozan **+0.468874**; Next 7 Days Keegan
  Murray / Dillon Brooks **+0.890583**. These are descriptive WATCH
  comparisons, **not supported transaction recommendations**.
- Each mode's checked optimizer comparison exactly equals selected-drop and
  impact output. Specifically, Next 7 Days Murray / DeRozan is
  **84.970762 -> 86.190713**, net **+1.219951**, in all three surfaces.
  Read-only acceptance rejects provider calls and non-read SQL:
  **94 SQL statements, zero provider calls, zero writes**.
  The analysis used 10-13 SELECTs per optimizer context, not per pair.
- Final validation: **93 focused / 253 full backend**, **10 focused / 34 full
  frontend**, strict TypeScript/Vite build, **12 desktop/mobile Playwright/axe**
  browser tests passed. See the [session record](../sessions/2026-10-25.md#waiver-accuracy-phase-2-best-supported-transaction).
  Implementation-run documentation links and `git diff --check` passed.
  These are completed Phase-2 validation results, not tests rerun for this
  documentation closeout.
  No production deploy, provider refresh, OAuth, Yahoo writes, migrations,
  formula/weight tuning, commit or push.
- Remaining limitations: current-season samples, role/status evidence,
  incomplete/stale production for some players, partial/missing schedules,
  unverified Yahoo matchup-week semantics, current priority, weekly acquisition
  usage/remaining and exact claim-clear time. No projections, numeric confidence,
  opponent bidding/demand, injury-return forecasts or execution are established.

### Historical Waiver Accuracy Phase 1 Foundation - 2026-10-25

The scoring, league and evidence foundation remains current under Phase 2;
this section's Phase-1 acceptance results are historical, not a new recheck.
All lower dated v1/v2 observations,
including old sample labels, action wording and rankings, are historical.
Older FAAB statements are obsolete/general exploration, not this league's roadmap.

- Persisted **Driveway Dudes / 478.l.50505** settings match: **Head-to-Head
  Points, 12 teams**, roster `PG SG G SF PF F C C UTIL UTIL BN BN BN IL IL IL`.
  Saved raw Yahoo settings and normalized settings are checked on every read;
  any disagreement returns explicit **409** mismatches, never a hard-coded fallback.
- Actual persisted Yahoo formula: **PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL
  - TO**. NBA TO input is `TOV`. Missing any required input makes value
  unavailable. API and UI expose per-game stats, modifiers and contributions.
- **No FAAB**, no bidding/cost substitute, no future FAAB feature for this
  league. Factual Command Center rules: continual rolling list, Standard,
  two-day waiver period, four adds/week, no season limit, Daily - Today,
  post-draft waiver rules, direct injury-slot additions. Current priority,
  remaining weekly adds and exact clear time are not verified or claimed.
  Acquisition value stays unavailable and excluded from scores.
- `mode=ros` remains API-compatible; its label is **Season Evidence**:
  historical/stat-based evidence, not a projection. Rest of Week and Next
  7 Days retain Pacific calendar windows, not inferred Yahoo matchup weeks.
- Backend evidence quality: **20+ EXCELLENT; 10-19 GOOD; 7-9 LIMITED;
  4-6 VERY LIMITED; 1-3 INSUFFICIENT FOR STRONG RECOMMENDATION;
  zero NO CURRENT-SEASON EVIDENCE**. This is not probability.
  Prior-season shrinkage remains descriptive and cannot bypass the current
  season gate, including in Season Evidence mode.
- Backend owns MUST ADD / ADD / STREAM / WATCH / PASS / INSUFFICIENT EVIDENCE.
  No forced MUST ADD, AVOID or confidence percentages. Positive 1-6-game
  candidates may be WATCH, never Best Add. ADD needs positive supported impact
  and sufficient current evidence for add/drop. Critical stale/missing evidence
  blocks strong decisions, not just warnings; unknown/stale Yahoo status also
  blocks them. O/NA exclusion and Q/P/blank eligibility behavior are preserved.
  STREAM requires fresh schedule and opportunity evidence. Partial schedule
  coverage is disclosed, never interpreted as guaranteed lineup starts.
- Selected-drop workflow and bounded/common-weight roster-index model are
  preserved. If every measured replacement is nonpositive: **HOLD [selected
  player]** is primary; the least-negative option is not Best Add.
- Real persisted-only acceptance: P.J. Washington selected, Next 7 Days,
  **WATCH** (not ADD): Keegan Murray **+0.393275**, 2 games, **13.85 fantasy
  PPG**; selected player 3 games, **26.4 fantasy PPG**. Keegan's four persisted
  games have partial coverage. Bilal Coulibaly (3 games, 23.3 fantasy PPG)
  and Kris Dunn (2 games, 30.0 fantasy PPG) cannot become strong recommendations.
  Selecting Luka Dončić produces HOLD in all three modes. See the
  [session record](../sessions/2026-10-25.md#waiver-accuracy-phase-1) for historical evidence
  and final validation.
- No provider refresh, Yahoo writes, OAuth, production migration, deployment,
  weight tuning, commit or push. Existing dirty unrelated work is preserved.

## Historical: Contract Reconciliation - 2026-10-25 3:06 PM PDT

Verified against current code/contracts/tests and trusted-TLS read-only runtime
checks. This section and the v2 correction immediately below were then current;
the explicitly marked historical snapshots further below are not current advice.

- `/waivers` is configured for **Box Score Bully**, team
  **478.l.50505.t.9**, league **478.l.50505**. This is application configuration,
  **not verified Yahoo-authenticated ownership**. Primary flow: configured
  roster -> select one player to replace -> ranked waiver alternatives.
  Selected drop controls every comparison and modal; Best Overall is secondary.
  Negative replacement values mean no measured improvement: hold is preferable
  under the model, not guaranteed future performance.
- Actual UI modes are **Rest of Week** (`this_week`, default), **Next 7 Days**
  (`next_7_days`) and **ROS** (`ros`). Rest of Week always has that label;
  fewer than two inclusive dates adds a **limited days remaining** warning.
  Pacific `America/Los_Angeles` today-through-Sunday remains the actual window;
  Next 7 Days includes today plus six dates. Neither is a verified Yahoo matchup
  period. ROS is historical/stat-based, not a projection.
- All three endpoints default `mode=this_week` and accept
  `this_week|next_7_days|ros`:
  - `GET /api/v1/waivers`
  - `GET /api/v1/waivers/replacements?drop_player_id=...` (required integer)
  - `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...` (optional drop)
  Player/drop IDs are internal identities; non-manager drops are rejected.
  All reuse PostgreSQL-only calculations, with no provider calls or writes.
- The **3:06 PM PDT** runtime recheck reproduced every P.J. Rest of Week
  top-five value and the Next 7 Days Keegan **+0.393275** checkpoint below.
  P.J. selected ID **10184** remained fixed in every result and matched the
  impact endpoint. Curry selected ID **10022** produced Keegan **-0.443761**,
  rather than P.J.'s **-0.247672**. Thirteen roster players were returned.
  All five P.J. alternatives remain VERY LOW SAMPLE; missing schedule rows
  for Bilal/Christie are unknown, not zero. Keegan's Next 7 Days schedule is
  four games with **partial** coverage, from October 25 through October 31.
- Reproduced old v1 arithmetic in memory from persisted data, in a read-only
  transaction: marginal fit **0 -> 200**, slot coverage **10 -> 10**, obsolete
  net **+95.080661**. Current API instead returns fit **100 -> 100**, delta
  **0**, net **-0.523137** for Dunn/P.J. Old positive output is superseded.
- Yahoo fantasy identity/settings/roster/state and persisted NBA basketball
  inputs retain separate authority. Freshness/missing gates remain; O/NA
  excluded, Q/P uncertain, blank unknown, roster absence only `unrostered`
  without proven claim timing. No FAAB, ownership percentages, opponent demand,
  injury-return forecasts, matchup difficulty, calibrated confidence/probability,
  category-aware waiver impact, authenticated ownership, transaction execution
  or predictive accuracy is established.
- Validation numbers below belong only to the completed replacement
  implementation run: backend **31 focused / 191 full**, frontend
  **7 focused / 31 full / 8 browser**, production build passed, plus the
  **8 final targeted backend assertions**. No full suite or application build
  was rerun for this documentation reconciliation. Health GET returned **200**.
  No runtime changes, provider refresh, Yahoo writes, OAuth, migration,
  rebuild/deployment, commit or push in this docs-only pass.

## Historical: Replacement Quality Correction - 2026-10-25

This supersedes the old v1 recommendation results below; those dated results
remain historical evidence, not current advice.

- Audited the real old Dunn/P.J. calculation read-only. Removing P.J. made
  Jarrett Allen and Pascal Siakam individually indispensable to slot matching,
  changing each marginal fit from 0 to 100 even though both complete rosters
  cover **10/10** starting slots. Summing those marginal scores invented a
  **+200** fit gain. With common effective weights fit **0.466667**, value
  **0.333333**, opportunity **0.2**, old net was
  `200*.466667 + 7.603093*.333333 - 3.935185*.2 = 95.080661`.
  Dunn's displayed fit was zero because he was not individually indispensable;
  that mismatch was semantic, not an intended quality advantage.
- Version **waiver-evidence-v2** measures whole-roster starting-slot coverage
  once, 0-100, and uses roster means for all other components. Before/after
  use the same scale, common mask, effective weights and fixed league
  percentiles. Every component delta is bounded -100 to +100; covered-to-covered
  reassignment yields zero fit gain. Weights stayed **35/25/15/15/10**.
- Recent/Next 7 Days player value blends supported fresh prior-season PPG with
  recent PPG using recent weight `n/(n+10)`; no independent prior history means
  raw recent limited evidence. Missing/stale recent data still cannot score.
  Samples 1-3 are VERY LOW SAMPLE, 4-6 LOW SAMPLE, >=7 LARGER SAMPLE,
  zero is NO SAMPLE, never
  calibrated confidence. A single best-team result requires a supported impact
  and >=7 fresh production games for add and drop in that mode.
- Corrected real Dunn/P.J. comparison: coverage **100 -> 100**, production
  percentile roster mean **83.604282 -> 82.216495**, opportunity mean
  **89.440883 -> 89.138177**. Same effective weights give
  `0*.466667 - 1.387787*.333333 - .302707*.2 = -0.523137`.
  Overall roster index **92.422937 -> 91.899800**. Dunn's ranking PPG is
  `30*(2/12) + 20.66*(10/12) = 22.216667`, with two recent games and 82
  independent prior-season games. This is not a projection or drop recommendation.
- Explicit-drop endpoint
  `GET /api/v1/waivers/replacements?drop_player_id=...&mode=...` reuses the
  same loader/scorer as board and impact. It rejects non-manager drops and
  ranks only eligible unrostered/available players for that exact drop.
  Board responses include the full configured roster; detailed impact keeps
  the explicit drop even if capacity is open or another drop scores better.
- Read-only real **P.J. Washington / Rest of Week** top five:
  Keegan Murray **-0.247672**, Bilal Coulibaly **-0.373748**,
  Kris Dunn **-0.523137**, Derrick Jones Jr. **-0.529745**,
  Max Christie **-0.723925**. All are negative; no measured improvement.
  Each has only two or three recent games. For **Stephen Curry**, top three
  are Keegan **-0.443761**, Bilal **-0.569837**, Dunn **-0.719226**;
  same ordering happens to hold, but the exact drop and values differ.
- This Sunday Rest of Week remains **October 25 only**. **Next 7 Days**
  separately ranks schedule evidence for **October 25-31**, Pacific today
  plus six days. P.J.'s top next-seven result is Keegan **+0.393275**, with
  four persisted games and VERY LOW SAMPLE production, not confident advice.
  Neither date window claims Yahoo matchup-week semantics. ROS stays historical.
- Focused backend **31 passed**; full backend **191 passed** on disposable,
  internal-network-only PostgreSQL, with one existing Starlette/httpx warning.
  No provider calls during analysis/validation, Yahoo writes, NBA/Yahoo/Fantrax
  refresh, OAuth, migrations, fabricated production data, commits or pushes.
- Frontend **7 focused**, **31 full**, **8 desktop/mobile browser/accessibility**
  tests passed; strict TypeScript/Vite production build passed. Primary page
  order is configured-team header, full roster-player selector, selected-drop
  top three, date controls, secondary Best Overall, full table, data quality.
  Nonpositive results explicitly say no measured improvement. Modal keeps
  the selected drop; sample labels and risks are prominent.
- Rebuilt/recreated only local API/frontend with API lifespan disabled;
  database/Caddy unchanged. Reloaded frontend upstream DNS after recreation.
  Trusted-TLS health **200**. Real browser verified **13 selectable roster
  players**, P.J./Curry-specific responses, fixed P.J. modal comparison,
  Rest of Week default, Next7 October25-31, ROS, no visible API alerts,
  no blocking desktop/mobile overflow and **zero write requests**.

## Historical Snapshots - Superseded by the Phase-1/Phase-2 Contracts Above

The remaining sections preserve observations at earlier stages. Old endpoint
lists, UTC windows, selectors, best-fit results, v1 scores and test counts
describe those stages only. In particular the old positive Dunn/P.J. and
Jrue/P.J. outputs are not current recommendations. Earlier authorization and
missing-NBA blockers were resolved in later dated work.

## Historical: Weekly Evidence Restored - 2026-10-25 12:04 PM PDT

This supersedes the earlier missing-current-season-NBA blocker below. After
explicit user authorization, the existing NBA import endpoint ran for season
2026-27 with `recent_days=30`. It returned 30 teams, 521 players, 1,547 season
statistics rows across its existing periods, 1,274 games, 2,803 game logs,
56,332 player schedule entries, eight identity mappings and one unresolved
schedule-team reference. Independent read-only SQL verified **812 recent
current-season regular-season logs**, **388 current-season regular-season
statistics rows**, and **1,274 season games**, persisted **12:04:00.394622 PM
PDT**. Schedule coverage remains partial, not certified complete.

- Real This Week: **309 eligible rows**, **227 scored**, **184 analyze-add**,
  **43 watch**, **82 insufficient-evidence**. Both Best Overall and Best Fit
  selected **Kris Dunn** at that time; the v1 top drop was **P.J. Washington**.
  Before **570.432894**, after **665.513555**, net **+95.080661** descriptive
  model-index change. Component changes: roster fit **+200**, player value
  **+7.603093**, opportunity **-3.935185**; schedule is not a common measured
  component of this swap. This is not a predicted points/wins gain.
- Pacific Sunday October 25's today-through-Sunday window is **October 25
  only**, not the following week or verified Yahoo matchup semantics. Dunn's
  recent input has only **two games**, Yahoo status is unknown, and his one
  persisted remaining game is partial schedule evidence, not a guaranteed start.
- Read-only live browser verified This Week default, visible real drop/reasons,
  Analyze Add opening/closing, ROS switch and no blocking 1440px/390px overflow.
  No application code, scoring, freshness gates, Yahoo state, migrations or
  services changed. Only the explicitly authorized existing NBA import wrote
  basketball data; no Yahoo/provider refresh beyond that NBA workflow.

## Historical: Upfront Drop Explanation - 2026-10-25

The Best Fit card now surfaces the existing top positive modeled drop option,
its before/after roster indices, measured component changes and existing model
reasons. No new calculation or API was added. The suggestion is conditional on
needing a drop; open-slot additions are not presented as requiring one. Missing
or nonpositive swap evidence produces an explicit unavailable comparison.
The full Analyze Add dialog retains the other supported drop options.

- Validation: **7 focused frontend**, **31 full frontend**, **6 desktop/mobile
  browser/accessibility tests passed**; production TypeScript/Vite build passed.
  The first browser run had two 60-second axe/browser timeouts during the
  concurrent image build; the unchanged suite passed on rerun in **33.8s**.
- Rebuilt/recreated only local frontend. Read-only real browser verification
  shows ROS **add Jrue Holiday / top drop P.J. Washington**, with roster-fit
  **+200.0**, player-value **+3.2**, schedule **+50.0** component-index changes
  and net weighted roster-index change **+104.4**. These are aggregate model
  changes, not projected player points or a claim of uncovered roster slots.
  This Week remains the default; no selectors or 1440px/390px blocking overflow.
- Trusted-TLS health check returned **200**. No new provider import/refresh,
  Yahoo write, migration, scoring/gate change, commit or push for this UI change.

## Historical: Fresh OAuth Recovery and Yahoo Import - 2026-10-25 11:25 AM PDT

This runtime evidence supersedes the stale-Yahoo/authorization blockers recorded
earlier below, without changing those historical observations.

- Fresh callback credential metadata: row exists, both encrypted credential
  presence flags true, updated **11:14:23 AM PDT**, expires **12:14:23 PM PDT**.
  The credential commit precedes automatic league import; its later 502 did not
  roll back authorization. No secret values or provider payloads were displayed.
- Exactly one normal-auth/client canary, `league/478.l.50505/teams`, with
  `max_attempts=1`, returned **HTTP 200**. Authorization was restored as of
  this check; no additional OAuth flow or token refresh was performed.
- Callback failure was the league persistence transaction: deleting existing
  `teams` conflicted with preserved draft-pick references
  (`draft_picks_team_key_fkey`). It was not an OAuth exchange, league discovery,
  normalization, settings-source or schema defect.
  Changed only team persistence to upsert by stable team key, preserving
  referenced/historical rows rather than deleting them. Existing rows absent
  from a new response are retained without a new import timestamp.
  Persistence errors retain their sanitized 502 boundary and log only error
  class/event context, not SQL parameters/provider payloads.
- Existing supported league/settings import committed at
  **11:20:26.039906 AM PDT**, all **12 teams** in that snapshot. Existing
  player/all-roster import committed at **11:20:50.816210 AM PDT**:
  **744 player/status rows**, **12/12 fresh roster snapshots**, and
  **13 Box Score Bully roster players**. Separate read-only database queries
  verified timestamps/counts after each import; HTTP success alone was not used.
- Real `/waivers` now has **309 eligible candidate rows**, **270 O/NA
  exclusions**, **zero unknown-availability players** and available Yahoo
  league/settings/roster/availability quality. Q/P retain uncertainty; blank
  status remains unknown. All 12 rosters supply league-wide availability;
  all actionable calculations remain bound to Box Score Bully.
- This Week: **0 actionable/scored candidates**, Best Overall/Fit unavailable:
  there are **zero persisted 2026-27 recent regular-season NBA game logs**.
  No NBA import/call was performed under this task's explicit restriction.
  Calendar window is Pacific **October 25 through October 25** (Sunday).
- ROS: **252 scored**, **200 actionable** among 309 eligible candidates;
  Best Overall **Nikola Vučević**, Best Fit **Jrue Holiday**. Top supported
  drop **P.J. Washington**: descriptive roster index **535.823450 → 640.222502**,
  change **104.399052**, not predicted points/wins. All three drop options
  were independently verified inside Box Score Bully's roster. Historical ROS
  value is not a projection; missing recent opportunity/schedule evidence and
  all previously unsupported analytics remain explicitly unavailable.
- Real browser verified direct team opening/no selectors, This Week default,
  ROS switch, candidate table, Best Overall/Fit, roster needs, impact dialog
  open/close, Pacific timestamps and no blocking 1440px/390px overflow.
  Alternate-team requests still return 422.
- Focused persistence/Yahoo/player/waiver regressions: **43 passed**, one
  existing Starlette/httpx warning, on disposable PostgreSQL. This includes
  idempotent refresh, preserved draft history, and all-or-nothing rollback with
  sanitized errors. Preserved real history counts remained **18 sessions,
  2,022 picks, 2,022 events, 2,040 snapshots** before/after.
- Only the local API was rebuilt/recreated for this fix, retaining disabled
  lifespan startup; local frontend Nginx reloaded upstream DNS. No migration,
  scoring/freshness/target/timezone/UI change, Yahoo write, speculative endpoint,
  NBA/Fantrax call, commit or push occurred.

## Historical: Waiver Center Closeout - 2026-10-25

The read-only Waiver Center is an implemented post-draft capability alongside
the Championship HQ foundation/category baseline and preserved Draft module.
This section supersedes earlier future-scope wording about generic waivers;
older dated evidence below remains historical, not fresh runtime validation.

### Verified implementation and UX

- `/waivers` opens directly for **Box Score Bully**, without league/team
  selectors, default **This Week**, and retains **ROS**. The subheader uses the
  persisted team name. **Box Score Bully is the configured manager analysis team
  for the personal application; this configuration is not Yahoo-authenticated
  ownership evidence.**
- API setting `WAIVER_MANAGER_TEAM_KEY` defaults to `478.l.50505.t.9`;
  the persisted team association supplies league `478.l.50505`. Both existing
  routes enforce that target. Optional legacy `league_key`/`team_key` inputs
  must match or return 422. Missing configured team returns 404, never a
  different roster. Frontend URL/saved-state targets cannot select another team.
- `GET /api/v1/waivers` accepts
  `mode=this_week|ros` (default `this_week`). It returns candidates, separate
  best-overall/best-fit IDs, roster needs, configured weights, limitations,
  excluded/unknown-availability counts, persisted team name, resolved target
  keys and source quality/timestamps. The frontend sends no team-selection keys;
  the backend resolves the configured league/team for every board/impact read.
- `GET /api/v1/waivers/{player_id}/impact` uses the internal player ID and the
  same context, with optional `drop_player_id`. Drop IDs must belong to the
  selected roster (422); already-rostered adds return 409; missing
  league/team/player returns 404. Mode validation returns 422.
- Best Overall uses the mode's measured production percentile alone. Best Fit
  chooses scored actionable candidates by net add/drop model improvement,
  then weighted overall score and internal ID. The candidate table itself
  ranks weighted overall score. Up to three drop options come from the
  selected roster only; imported open non-injury capacity supports no-drop
  analysis. No transaction eligibility or roster-lock guarantee is implied.
- The analysis dialog exposes before/after scores, component deltas, drop
  options, historical values/sample sizes, schedule window, evidence and
  limitations. Loading, errors, empty/unscored results, keyboard modal focus,
  and responsive table overflow have synthetic test coverage. Reload only
  rereads persisted data.

### Data boundaries and scoring semantics

- Yahoo remains authoritative for league/player identity, settings, roster and
  state evidence. Persisted NBA season statistics, regular-season game logs,
  teams and games provide basketball inputs. Both waiver routes are
  database-only; guarded tests reject Yahoo/NBA provider calls.
- Availability needs fresh affirmative persisted Yahoo ownership or absence
  from every fresh league roster. Absence is `unrostered`, not verified
  free-agent/waiver-claim timing. Unknown availability is withheld.
  O/NA are excluded; Q/P stay eligible with uncertainty; blank status is unknown.
- Waiver roster/settings/availability freshness uses a 24-hour import cutoff.
  Roster snapshots predating later league/team/settings imports cannot establish
  current absence. Stale settings cannot supply scoring or positional fit.
  This age gate is waiver-specific; the foundation roster API retains its
  source-order-based stale semantics.
- Recent value uses persisted regular-season logs in the league's NBA season
  from Pacific today minus 14 days through today, inclusive, under supported
  Yahoo points modifiers. The oldest selected log import and latest selected
  game date must each be within seven days. ROS selects each player's latest
  eligible regular-season history, no later than the league season (current
  Pacific year cutoff if absent), **not a projection**. Seven-day-stale historical
  imports remain visible but cannot score or supply hold-label evidence.
- This Week counts persisted scheduled games from today through Sunday Pacific Time.
  ROS counts through June 30 after the league season start year, or today if
  that date has passed. Neither is a verified Yahoo matchup period.
  Final/cancelled/postponed games are omitted; no rows means unknown, not zero.
  Schedule coverage is partial, off-days mean at most five persisted games
  that date, and imports older than seven days cannot supply a schedule score.
- Displayed timestamps, recent-log calendar boundaries and schedule date windows
  use `America/Los_Angeles` (PST/PDT automatically), per the explicit follow-up
  request. Stored timestamp instants remain UTC and freshness uses unchanged
  elapsed-time limits. NBA dates remain persisted date-only inputs; neither
  tip-off times nor Yahoo matchup periods were newly established.
- `waiver-evidence-v1` uses deterministic midrank production/schedule
  percentiles, positional maximum-slot matching and measured minutes/trends.
  Hold labels are descriptive heuristics, not future roles or injury forecasts.
  API environment `WAIVER_WEIGHTS` configures fit/value/opportunity/schedule/
  acquisition components; defaults are 35/25/15/15/10 percent. Finite,
  nonnegative weights with a positive sum and all five keys are required.
  Missing components are omitted and measured weights renormalized; supported
  player value and roster fit remain mandatory for an overall score.
- Add/drop recomputes entire-roster positional fit on both sides using fixed
  value percentiles and the same common measured components/weights. Missing
  roster values leave numeric impact unavailable. Improvement is a descriptive
  model-index change, **not predicted fantasy points or wins**.

### Configured-team/Pacific follow-up validation

- Focused backend waiver suite: **17 passed**, one existing Starlette/httpx
  deprecation warning, no skips. It verifies server-bound target/default mode,
  rejection of other teams/leagues on board and impact routes, missing-target
  errors, stale-data gates, and Pacific Sunday boundaries in PST and PDT.
- Focused frontend: **6 passed**; full frontend: **30 passed**.
  Strict TypeScript/Vite production build passed. Desktop/mobile Playwright:
  **6 passed**, including axe, candidates, Best Fit, modal open/close/focus,
  drop comparison, mode toggle, error/stale empty states, URL/saved-target
  rejection and GET-only analysis. Timestamp tests verify PST/PDT independently
  of the browser zone.
- Test resources were disposable and network-isolated. Rebuilt/recreated only
  local API/frontend through existing Caddy, retaining the no-lifespan browser
  override so schema initialization/migrations and the draft worker do not run.
  Database/Caddy were not restarted or modified.
- Running-stack health returned 200. `/waivers` opens directly for persisted
  **Box Score Bully**, league `478.l.50505`, team `478.l.50505.t.9`, without
  selectors; This Week/ROS return the same configured target. Other-team board
  and impact requests return 422. Pacific timestamps and desktop/mobile layout
  were verified against real data.
- Real recommendations remain unavailable: league/settings are dated October 9,
  rosters October 18, and **744 players have unknown availability**. Both modes
  show the real empty state, not fabricated candidates or bypassed gates.
  No production migrations, provider refresh/import, OAuth or Yahoo write
  occurred. Existing unrelated dirty work was preserved.

### Earlier closeout validation and limitations

- Backend focused: **44 passed**, including **12 waiver tests**, category
  baseline, player-read/import, Yahoo-client and token-storage regressions.
  Full backend: **171 passed**. Each final run emitted one existing
  Starlette/httpx deprecation warning; no skips or failures.
- Frontend focused waiver rendering/contracts: **5 passed**; full frontend:
  **29 passed**. Strict TypeScript/Vite production build passed.
  Playwright 1.56.1: **4 passed**, desktop/mobile synthetic API fixtures,
  including axe, modal focus, mode changes, error/empty states and GET-only
  analysis.
- Validation used disposable PostgreSQL on a new internal Docker network,
  read-only source mounts, and temporary frontend storage in a network-disabled
  Playwright container. The full run exposed a category test's cross-event-loop
  pool reuse; a test-local NullPool engine/dependency override fixed isolation.
  Stale ROS/settings scoring and stale hold-label evidence were corrected;
  existing unrelated dirty work was preserved.
- Still unavailable: acquisition value/FAAB, ownership percentages, opponent
  bidding/demand, injury-return forecasts, validated projections, matchup
  difficulty, calibrated confidence/probabilities, category-aware waiver impact,
  What Changed/history, and transaction execution. Existing category baselines
  are not waiver impact. No Yahoo transaction, scoreboard, current-week, or
  authenticated ownership source contract was newly verified.
- No new migration was required. Existing schema/migration tests ran only on
  disposable databases. No production mutation, provider refresh/call, OAuth
  attempt, deployment, commit or push occurred.

See the [2026-10-25 session record](../sessions/2026-10-25.md) for exact commands
and initial validation/setup failures as well as final passing results.

## Final Draft-Era Baseline - 2026-10-19

The draft system is preserved as an implemented module and historical record.
The primary development direction is now post-draft **Championship HQ**.
This closeout does not implement post-draft features or establish that a Yahoo
league has completed its draft.

## Implemented and Tested

- Persisted v2 draft sessions, sequential picks, correction/latest-pick undo,
  targets, session locking, optimistic versions, audit events, recommendation
  snapshots, and read-only internal-mock replay. The stateless v1 utility API
  remains available.
- Separate internal mock, mock batch/practice, synthetic Mock Sync Rehearsal,
  Yahoo Mock Practice, and Production Live workflows. Internal opponent selection
  is rule-based and seeded, not a calibrated simulation.
- Official authenticated Yahoo `draftresults` retrieval, Yahoo-ID normalization,
  and the existing sequential reconciler. Matching local picks are confirmed;
  only contiguous source picks are appended; conflicts stop reconciliation.
  Production Live retains Sync Now, pause/resume, and Quick Record/manual entry.
- Progressive Live order discovery from first-round source picks, partial
  opponent mappings, explicit manager-slot confirmation, and manual conflict
  resolution. Unknown team slots are not invented.
- React Draft Room with backend-ranked board, manager roster, timing, targets,
  explanations, separate BEST PICK NOW / WAIT ANALYSIS, and version-conflict UX.
  The front door prioritizes Yahoo URL connection after one-time Windows
  observer pairing; internal practice and saved rooms remain available.
- Browser observation is read-only in Yahoo. Mock observations pass through
  the canonical normalization/reconciliation path into disposable practice
  sessions; browser-based Production Live writes are not enabled.
  The current Yahoo practice bridge supports 12-team mocks and requires verified
  rounds and manager slot before initialization.
- Migrations through `0006_observer_connections` are implemented; isolated
  PostgreSQL migration tests pass. The latest session records production
  application of 0006; production schema was not rechecked in this closeout.
- The exact NBA-import proxy route has a 600-second timeout; other API routes
  retain their existing timeout behavior.

## Recommendation Semantics and Limits

BEST PICK NOW is the highest current adjusted roster value under the historical
production heuristic. WAIT ANALYSIS is a separate ADP/survival/fallback
decision; ADP does not directly determine BEST PICK NOW. Only manager picks
populate manager-roster inputs; all league picks affect availability and run
context. Roster matching prioritizes starters before UTIL/bench and handles
incumbent reassignment. Why this rank explains roster-driven score/rank effects,
not predictive accuracy.

- Yahoo O/Out and NA/Not Active are excluded from normal recommendations,
  best value at risk, and wait/fallback candidates. Q/P remain eligible with
  uncertainty. Blank/unrecognized status is unknown, not evidence of health.
- Yahoo status is refreshed by player-pool import, not continuous monitoring.
  Historical values remain visible; no injury penalty or recovery forecast is
  inferred.
- Historical production is not a future-season projection. Small internal
  score differences do not prove objective real-world player superiority.
- Survival/wait estimates remain `heuristic_unvalidated`. No calibrated
  probability, Monte Carlo forecast, opponent roster-demand model, category
  engine, or historical outperformance is established.
- Missing/stale provider data stays unavailable; no fabricated ADP, source
  timestamps, injury forecasts, or player metrics.

## Last Recorded Runtime Evidence - 2026-10-18

These are dated observations from the latest session, not fresh production
checks or guarantees of current freshness. No provider import or production
mutation was performed for this closeout.

- Actual Yahoo Mock Practice smoke: 23 real picks and 24 recommendation
  snapshots, manager selections at picks 7 and 18, manager-only roster inputs,
  recalculation after manager picks, O-status exclusion, and no extra
  picks/events on duplicate reads. This is practice evidence only.
- Windows owner accepted background/windowless startup, tracking, and reconnect.
  Dedicated Chrome CDP stays on Windows `127.0.0.1`; observations use trusted
  HTTPS. One-time pairing avoids per-draft commands or credential handoff;
  missing slot evidence requires only the verified slot fallback.
- Yahoo pool: 744 identities, 691 NBA mappings. Persisted NBA inputs:
  738 players and 1,159 season-stat rows. Draft metrics: 682 scored
  (563 regular-season, 119 preseason samples); 62 unscored
  (53 unmapped, 9 mapped without eligible stats).
- Yahoo status population: 436 blank, 217 NA, 28 O, 62 Q, 1 P.
- Fantrax diagnostics: 396 fetched, 364 matched, 32 unresolved, 0 ambiguous.
  Stored ADP: 366 rows, then 364 fresh and 2 stale; then-fresh usable coverage
  48.92%, stored coverage 49.19%. These freshness labels age with retrieval.
  Draft rank, XRank, draft frequency, sample size, and upstream source-updated
  timestamp are not supplied.
- The session records persisted NBA/stat refresh and preservation of prior
  Live/session/pick/event/snapshot state and identity associations. This
  closeout does not independently repeat those runtime checks.

## Closeout Validation - 2026-10-19

- **146 backend tests passed**, with one existing Starlette/httpx deprecation
  warning, against a disposable PostgreSQL database isolated from production.
- **23 frontend tests passed**; strict TypeScript/Vite production build passed.
- Observer Results-reader tests and Picks DOM contract fixtures are separate
  synthetic checks: **4 Results-reader tests passed** and the Picks DOM fixtures
  passed. These are not new Yahoo or Windows acceptance.
- Canonical Markdown links/fences, Python syntax, observer export shell syntax,
  Compose configuration, and whitespace checks passed. Intended source was
  scanned for accidental credentials/private artifacts; generated dependencies
  and frontend build output are excluded from the commit.

See the [final session record](../sessions/2026-10-18.md) for closeout checks and
the distinction between recorded runtime acceptance and local test evidence.

## Remaining Draft Boundaries

Official Production Live active-draft `draftresults`, source mapping/cadence,
and full manual fallback/correction/recovery browser acceptance remain
unverified. The earlier integrated-browser certificate blocker is not proof
that these checks passed; later Windows mock acceptance does not replace them.
Retain official-source/manual fallback and conflict protection.

Partial mappings/ADP, preseason samples, snapshot-based status, and uncalibrated
heuristics remain material limitations. Post-draft roster/matchup/projection
and championship behavior is not validated by this draft baseline.

See [next actions](next-actions.md), [project memory](../project-memory.md),
the [recommendation audit](../recommendation-audit-2026-10-18.md), and the
[operator checklist](../draft-day-checklist.md).

## Championship Foundation Slice - 2026-10-19

- The home page has a Championship HQ foundation panel using persisted Yahoo
  league settings and team rosters. Its explicit refresh action uses the
  existing league import followed by the existing player/roster import.
- League and settings reads expose their persisted import timestamps.
  `GET /api/v1/rosters` now includes each persisted Yahoo team, including teams
  without a roster snapshot, with source, snapshot time, and
  `available` / `stale` / `not_imported` status.
- `stale` means a later league/team/settings import is known to postdate that
  roster snapshot; there is no age-based cutoff. A successfully imported empty
  roster remains distinct from a roster never imported. Reads use stored data
  and do not call Yahoo.
- Scoring settings remain Yahoo-authoritative. A database-only category
  baseline now returns one result per persisted team and configured category.
  It reports raw supported category output, category status, contributors,
  missing/unmapped players, selected source season/type, and source import
  timestamps. Unsupported categories return no value.
- The engine selects the latest eligible regular-season source season among
  persisted stats for mapped rostered players, no later than the Yahoo league
  season when known. This is not a season intersection across every player:
  players without a row in the selected season remain missing, with no
  fallback to an older season. The regular-season stat type is selected
  deterministically and reported with the season.
- Counting categories sum persisted per-game player rates. FG% and FT% are
  computed from season makes/attempts, derived from persisted per-game
  components × games played. A missing/zero denominator yields no percentage
  value. Category direction follows Yahoo negative modifiers and turnover
  semantics without changing raw category totals.
- Missing Yahoo-to-NBA mappings, source rows, stat fields, and required
  percentage components remain visible. Empty imported rosters and rosters
  not imported are distinct; stale roster snapshots remain identified.
  Matchup/transaction context and actual league draft completion are not
  established by this slice.
- Validation for this slice: 5 backend tests passed against a newly created
  disposable PostgreSQL container (2 category-baseline tests, player-read API,
  and 2 draft-readiness regressions); both Yahoo and NBA provider calls were
  guarded against use by the read route. All 24 frontend tests passed,
  including the focused rendering test. Strict TypeScript/Vite production
  build passed in a disposable Node container. The existing
  Starlette/httpx deprecation warning was emitted. No production database or
  live provider was used.

## Category + Team Identity Relative View - 2026-10-19

- Audited the prior baseline contract and corrected its source-season meaning:
  the selected season is the latest eligible regular season with mapped
  rostered-player statistics across the league, not a season shared by every
  roster player. Per-player older-season fallback remains disabled. Selected
  source-season and stat-type API names and UI wording now match this behavior.
- Category identifiers and names cover the Yahoo fixture-backed PTS, REB, AST,
  ST, BLK, and TO categories; FG% and FT% use their supported Yahoo IDs and
  season-weighted makes/attempts. Counting output is explicitly labelled as
  the sum of player per-game rates. Percentage denominators are preserved.
- The database-only category endpoint now includes versioned league-relative
  results. Comparisons are isolated by league, configured category, selected
  source season/stat type, calculation type/direction, and method version.
  Teams count as comparable only when both the roster snapshot and category
  data are available; partial, stale, unavailable, and unsupported values are
  excluded with reasons. At least three comparable teams are required.
- Ranks use competition ties; min, max, median, and 0–100 min-max position are
  returned. Higher/lower direction follows the category contract; equal values
  map to 50. Backend versioned thresholds classify sufficient results as
  strength (≥75), weakness (≤25), or neutral. Insufficient results are not
  ranked. No authenticated manager team is inferred.
- Championship HQ allows selection of any persisted Yahoo team, shows rank,
  comparable-team count, normalized position, descriptive label/meaning,
  coverage and exclusion reasons, and retains raw category evidence and
  missing contributors. The panel expressly disclaims projections,
  percentiles, matchup advantages, recommendations, and championship
  probabilities.
- Validation: 10 focused backend tests passed against isolated disposable
  PostgreSQL, including provider-call guards, source-season behavior,
  persisted Yahoo category recognition, counting and weighted percentage
  calculations, missing denominator and mapping handling, empty/unimported
  rosters, same-league comparison boundaries, directions, ties, thresholds,
  normalized positions, and exclusions. All 24 frontend tests passed and the
  strict TypeScript/Vite production build passed in a disposable Node
  container. The existing Starlette/httpx deprecation warning was emitted.
  `git diff --check` passed. No production database or provider was used.
- Validation: 15 Yahoo player/service unit tests passed (the PostgreSQL-only
  API test was skipped in that invocation); the player read API and player
  import persistence tests then passed (2 tests) against a disposable
  PostgreSQL container. A follow-up focused run of 25 Yahoo/roster/API tests
  passed against disposable PostgreSQL. All 24 frontend tests passed; strict
  TypeScript and Vite production build passed in a disposable Node container.
  No live Yahoo requests or production database mutations were performed.

See the [2026-10-19 session record](../sessions/2026-10-19.md) for the precise
implementation and validation scope.

## Yahoo Matchup/Transaction Source Review - 2026-10-19

- Existing authenticated Yahoo adapters request NBA games, user leagues, league
  settings/teams/players, team rosters, and draft results. Existing fixtures
  and contracts cover those shapes; there is no scoreboard/matchup or
  transaction adapter/fixture/contract, nor a verified current-login-team or
  current-week contract.
- The client can send a path, but no verified payload or semantics establish
  that a new source path is supported for this account. No matchup or
  transaction source model/import was added. Current-team identity and draft
  completion remain unknown unless explicit Yahoo evidence establishes them.
- Validation after source review: 25 focused backend tests passed against
  disposable PostgreSQL (including database-only reads, roster missing/stale/
  available states, empty roster import, malformed-import preservation, and
  existing Yahoo fixtures); 24 frontend tests and the production build passed.
  Existing Starlette/httpx deprecation warning only. No production mutation or
  live Yahoo request was made.

## Yahoo Source Evidence Gate Attempt - 2026-10-19

- **No new source passed the evidence gate.** A read-only database preflight
  found an existing credential whose access token is expired and an imported
  league selection that is not uniquely resolvable automatically. No keys,
  tokens, callback data, or raw private provider data were printed.
- Executed the ignored local capture command for `identity`. It exited 2 with
  `authorization_expired_no_refresh_attempted`, `requests: 0`,
  `http_status: null`, `resource_path: null`, and
  `contract_verified: false`. This is local preflight evidence, **not a Yahoo
  401/403 response**. No OAuth refresh, Yahoo request, or production database
  mutation was performed. Scoreboard and transaction requests were not
  attempted after the authorization blocker.
- Exact candidate path templates, in evaluation order:
  1. `league/{already_imported_league_key}/teams`: existing adapter path;
     authenticated ownership fields and their meaning remain unverified.
  2. `league/{already_imported_league_key}/scoreboard`: unverified candidate.
  3. `league/{already_imported_league_key}/transactions`: unverified candidate.
  No path was issued in this attempt. For all three, HTTP authorization,
  top-level source collection shape, missing/explicit-empty semantics,
  pagination, stable source identifiers, week/date meaning, update/correction
  behavior, and authenticated-team attribution remain unverified.
- Added `backend/.local-yahoo-evidence/capture.py` and synthetic safety tests,
  locally excluded using `.git/info/exclude`. The utility invokes only the
  existing Yahoo client for a single exact GET with `max_attempts=1`; its
  transport retains actual HTTP status without logging headers or bodies,
  rejects other routes/methods/repeated requests, and bounds response size.
  It emits only redacted structural evidence to owner-only ignored files.
  Counts, field/container types, observed nullability, and structural
  missing/empty/malformed/ambiguous states are preserved. No pagination is
  followed; 401/403/429 stop the attempt. Successful structural capture still
  exits 2 pending authorized semantic review.
- No source model, migration, fixture, import path, API, or frontend change
  was added by this attempt. Completed Category + Team Identity work and
  explicit team selection remain unchanged; no "My Team" attribution,
  current-week inference, strategy, or recommendations were added.
- Validation: **58 focused capture/Yahoo/player tests passed** against
  disposable PostgreSQL; **10 Category + Team Identity regression tests
  passed** in a separate disposable database/process. This includes existing
  database-only read/provider-call guards. Local capture tests use synthetic
  transport/schema data, not Yahoo representative fixtures, and cover
  redaction, nullability/counts, malformed/missing/empty distinctions, limits,
  exact single requests, actual error status, no retry on 401/403/429/503,
  expired-token refusal, read-only DB enforcement, and non-verification.
  Python compilation and `git diff --check` passed. No UI changed in this
  attempt, so frontend tests/build were not rerun. Existing Starlette/httpx
  deprecation warning only. Combined API/category execution exposed an
  existing cross-event-loop pool limitation; isolated runs passed without
  changing application code.

## OAuth Reconnection Attempt - 2026-10-19 07:17 UTC

- Rechecked only credential metadata in a PostgreSQL read-only transaction:
  a stored credential exists, but its access token is expired. No token value
  was read/decrypted or displayed. Automatic imported-league selection remains
  non-unique; an intended league has not been explicitly selected.
- The existing `/api/v1/yahoo/oauth/authorize` route returned HTTP 307 to
  Yahoo's `/oauth2/request_auth`. State and the callback cookie were present;
  the redirect URI matched the configured HTTPS callback origin and
  `/api/v1/yahoo/oauth/callback` path. No OAuth configuration was changed.
- Opened the existing authorization workflow in the integrated browser. It
  reached Yahoo's **Sign in** page, requiring the owner's interactive login
  and consent. No callback completion or usable access token was verified.
  Stopped at this interactive boundary; no source captures were run.
- The owner must finish Yahoo sign-in/consent in the opened browser, or start
  `/api/v1/yahoo/oauth/authorize` on the trusted application origin in their
  own browser and finish the redirect to the configured callback. Do not
  share credentials, callback query parameters, or provider JSON. After
  callback success, verify credential usability and explicitly select the
  intended already imported league before any source capture.
- No source contract passed. No capture infrastructure, source persistence,
  OAuth configuration, Category + Team Identity code, or UI was changed.
  Only status/session documentation changed. `git diff --check` passed;
  backend/frontend tests and Python compilation were not rerun because the
  task stopped at authorization and no executable code changed. Earlier
  disposable-PostgreSQL test results remain dated evidence, not a new run.

## Post-Sign-in Identity Capture - 2026-10-19 07:20 UTC

- After the owner completed sign-in, read-only credential metadata showed an
  existing stored credential with an unexpired access token. No token value
  was inspected. The callback page did not expose the expected success JSON;
  full callback/import completion was not independently established, and the
  one-time callback was not replayed.
- Explicitly selected the already persisted real Yahoo league, excluding local
  mock-practice keys. Initiated exactly one existing-client request:
  `league/478.l.50505/teams`. Actual HTTP status **401**; authorization outcome
  `rejected_stop`, request count 1, command exit 2. Unexpired local metadata
  therefore did not establish provider token usability.
- Stopped immediately. No scoreboard or transaction invocation followed.
  No response collection, count, identifier/ownership fields, week/date,
  pagination, or correction structure was available. All semantic gates
  remain closed; the HTTP rejection is not evidence of endpoint shape.
- Reviewed only a bounded summary from the redacted ignored report; the
  report was owner-only (0600). No tokens, headers, callback parameters, or
  private provider payloads were displayed or committed.
- No executable code, OAuth configuration, capture infrastructure, persistence,
  API, or UI changed. Category + Team Identity remains preserved. Only status
  and session documentation changed; whitespace validation passed. Tests were
  not rerun for this authorization-blocked, documentation-only follow-up.

## Normal-Path Authorization Diagnosis - 2026-10-19

- Traced callback -> existing auth service -> encrypted credential persistence
  -> expiry selection -> existing refresh service -> Yahoo client. Callback
  stores credentials before importing leagues, so stored unexpired metadata
  can coexist with a failed callback import. Normal acquisition and capture
  use the same stored access token/decryption when expiry is unexpired.
  Capture intentionally refuses refresh; normal acquisition refreshes only
  within 60 seconds of expiry. The HTTP client does not refresh on 401.
- Verified source and running-client header expression structurally: both
  reference the supplied access token with a bearer prefix. No header or
  token value was displayed. A redacted source rendering is not evidence
  that a literal redaction placeholder is sent.
- **Normal authorization gate failed:** exactly one existing-service/client
  GET `league/478.l.50505/teams` returned actual HTTP **401**. No capture
  command was involved; this is not an isolated capture failure.
- **Outcome C:** attempted the existing OAuth service's supported refresh
  exactly once. A stored encrypted refresh credential was present; Yahoo's
  `/oauth2/get_token` returned actual HTTP **400**, mapped by the existing
  service to application 401. No known-good GET retry followed a failed
  refresh, and no identity/scoreboard/transaction capture was initiated.
- To invoke the expiry-based service after a provider rejection, marked expiry
  eligible only in the loaded in-memory ORM object with autoflush disabled.
  On refresh rejection, rolled the session back. No expiry invalidation,
  replacement token, or credential change was persisted; no second refresh
  implementation or OAuth configuration change was introduced.
- Proven failure boundary: provider rejection of normal stored access and
  rejection of refresh. **Exact provider reason is not established**: no safe
  error category was retained from the failed refresh response. Do not infer
  revoked/invalid grant, client configuration error, or repair a presumed
  capture/header defect. No further provider calls or repeated sign-in.
- Added three synthetic regressions: unexpired normal acquisition returns the
  same decrypted stored credential without refresh; rejected refresh attempts
  once and preserves encrypted credentials/expiry; client 401 stops without
  retry or leaking provider detail. No runtime or capture code changed.
- Validation on disposable PostgreSQL: **59 capture/OAuth/token/client/Yahoo
  tests passed**, plus **2 player read/import regressions passed** in a
  separate process (database-only provider guard, idempotence and malformed
  refresh preservation). Python compilation and `git diff --check` passed.
  Existing Starlette/httpx deprecation warning only. No frontend changes;
  frontend tests/build not rerun. All post-draft semantic gates remain closed,
  Category + Team Identity preserved, no commit/push.

## Sanitized Refresh Classification - 2026-10-19

- After synthetic tests passed, performed exactly one separately authorized
  refresh diagnostic through the existing `YahooAuthService`/`YahooOAuth`
  path and existing configuration. **HTTP 400, OAuth category
  `invalid_grant`, error_description present (value never retained), content
  type category `json`, refresh requests 1, credential_changed false,
  fantasy_resource_requests 0.** Process exited 2 and stopped.
- The stored authorization grant was rejected. This does not distinguish
  revocation, expiry, or another underlying reason. One fresh normal OAuth
  authorization/consent flow is the permitted next action; no configuration,
  callback, endpoint, scopes, client credentials, or production code changed.
  No reauthorization or fantasy-resource request occurred in this task.
- Added only ignored local diagnostic code/tests under the existing private
  evidence directory. The diagnostic intercepts the existing service's one
  exact token POST, disables retries/redirects, bounds the body to 8 KiB,
  permits only strict allowlisted top-level error codes, rejects duplicate-key
  JSON, and discards descriptions, headers, tokens, and provider text before
  returning a synthetic failure to the existing service. Non-JSON, nested,
  malformed, unknown and oversized error values classify as `unknown`.
- Database access uses read-only transactions. Expiry eligibility was selected
  only in memory with autoflush disabled; rollback ran on every service exit.
  Even unexpected provider success cannot reach token persistence. An
  independent post-rollback comparison confirmed encrypted credentials,
  expiry, and update timestamp unchanged. Owner-only ignored reports contain
  only allowed status/category/presence/count/timestamp/configuration booleans.
- Validation: **55 diagnostic/OAuth/callback/token-storage/security/client/
  draft-results tests passed** on disposable PostgreSQL, including 35 local
  synthetic diagnostic tests. Covered every allowlisted error, unknown/
  malformed/ambiguous/oversized input, description redaction, one POST,
  no fantasy GET, credential preservation after 400 and unexpected 200,
  and absence of synthetic secrets/provider text from reports/logs.
  Python compilation and `git diff --check` passed. Initial run reached the
  database before readiness; rerun after `pg_isready` passed. Existing
  Starlette/httpx deprecation warning only. No frontend change/tests/build.
- Authorization is **not restored**. Identity, scoreboard, and transaction
  semantic gates remain closed. Category + Team Identity preserved; no commit
  or push.

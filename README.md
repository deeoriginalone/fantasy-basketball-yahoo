# Fantasy Basketball GM

Docker-first Yahoo Fantasy Basketball application with a React Draft Room,
a Championship HQ foundation view and read-only Waiver Center, FastAPI services, and PostgreSQL
persistence. Yahoo is authoritative for fantasy-league/player identity,
configuration, and state; persisted NBA and authorized external data provide
basketball inputs.

## Current Product Behavior

The final draft-era baseline preserves the draft module and its history.
**Championship HQ** is the post-draft product direction. Its initial Yahoo
foundation/category baseline and Waiver Center are implemented post-draft
capabilities, not a complete championship or predictive analytics system.
See the [gated follow-ups](docs/status/next-actions.md).

- **Championship HQ foundation:** the home page reads persisted Yahoo league
  settings and team rosters. **Refresh Yahoo baseline** imports league
  metadata/settings, then the player pool and team rosters, using existing
  authorized Yahoo import paths. League, settings, and roster import times are
  shown. A roster is `not imported` when no saved snapshot exists and `stale`
  only when a later league/team/settings import is known to postdate that
  snapshot; snapshot age alone has no stale cutoff. An imported empty roster
  differs from unknown data. Matchup and transaction context are not included,
  and the view does not calculate decisions or projections.
- **Waiver Center:** `/waivers` opens directly for Box Score Bully and presents
  Best Supported Transaction or a successful HOLD decision, separate WATCH
  opportunities, then the exact selected-player replacement workflow.
  Best Overall Available remains secondary player-value context.
  The app-configured analysis team is not authenticated "My Team" identity.
  Rest of Week, Next 7 Days and Season Evidence use persisted historical basketball
  inputs and schedule evidence, not verified Yahoo matchup weeks or projections.
  Unrecognized status or unresolved Yahoo-to-NBA identity blocks strong advice
  and cannot produce a supported PASS. Incompatible model versions are not
  decision-ready; structured HTTP 409 contract failures remain visible errors,
  never HOLD or empty-success fallbacks.
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
  value at risk, and wait fallbacks. Q/P remain eligible with uncertainty.
  Blank and unrecognized nonblank Yahoo statuses are UNKNOWN, never confirmed
  healthy; unrecognized status fails closed. Unresolved, ambiguous or
  team-conflicting identity cannot support strong waiver advice. Refresh is
  import-based, not continuous injury monitoring. Historical metrics remain
  visible. Missing/stale inputs, unmapped/unscored players, partial ADP, and
  preseason samples remain explicit limitations; no values or recovery
  forecasts are invented.

The Windows observer runs windowless/background with loopback-only CDP on the
dedicated Chrome PC and bounded sanitized logs. Never expose CDP on the LAN.
See the [observer workflow](scripts/yahoo-observer/README.md),
[dated current-state evidence](docs/status/current-state.md), and
[draft-day checklist](docs/draft-day-checklist.md).

The backend owns calculations and decisions; the frontend prioritizes actions
and explanations; decision history supports audit and learning.
**Never surface a statistic as a primary result without explaining why it
matters to this roster/matchup and what decision it informs.**

## Championship HQ Foundation

After connecting Yahoo, use **Refresh Yahoo baseline** on the home page to
refresh persisted league/settings and player/roster inputs. The panel shows
Yahoo scoring rules, roster eligibility, team roster snapshots, and their
import times. Page reads use saved data without importing. Unknown, stale, and
valid empty rosters are distinguished. Matchup and transaction context are not
yet available in this view.

### Local Yahoo source evidence capture

This working tree has a **local-only, ignored** capture command at
`backend/.local-yahoo-evidence/capture.py`; it is not distributed by a fresh
checkout. Its reports and synthetic safety tests stay in the same directory,
excluded through `.git/info/exclude`. No matchup/transaction importer is enabled.

Use the normal Yahoo connection workflow to restore expired authorization
first. Never paste tokens or private provider JSON into chat. From the repository
root, explicitly initiate one source read, replacing the placeholder with an
already persisted Yahoo league key:

```sh
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  --entrypoint python -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/backend/.local-yahoo-evidence:/evidence" \
  api /evidence/capture.py --source identity \
  --league-key ALREADY_IMPORTED_YAHOO_LEAGUE_KEY
```

Evaluate `identity` first (the existing `league/{league_key}/teams` resource),
then explicitly run `scoreboard`, then `transactions` by changing only
`--source`. The latter two resource paths are candidates, not verified contracts.
**Stop after an authorization or rate-limit rejection; do not continue the
sequence.** The command never refreshes OAuth, writes to Yahoo, follows pages,
retries, or imports data. Database access uses a read-only transaction and
requires an existing, unexpired stored credential and an already imported league.

Reports contain actual HTTP status (or null when no request was sent), exact
requested path, redacted field/container structure, collection counts, observed
nullability, and explicit structural failure states. Unknown field names and
all scalar values except bounded collection/pagination counts are redacted.
Bodies over 1 MiB, excessive nesting/nodes, and summaries over 256 KiB fail
closed. Reports are owner-only files in the ignored directory, never raw payloads.
Exit **2** means the source contract remains unverified, even after a structurally
successful response; it is not an import-success signal. An authorized contract
review must still establish identity, stable IDs, week/date, pagination, and
correction semantics before any persistence implementation.

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

### Waiver Center

Open `/waivers` from the existing navigation: it loads directly for
**Box Score Bully**, defaulting to **Rest of Week** (`mode=this_week`), with
**Next 7 Days** and **Season Evidence** (`mode=ros`) alternatives and no
league/team selectors. The subheader uses the persisted team name when available.
**Box Score Bully is the configured manager analysis team for the personal
application; this configuration is not Yahoo-authenticated ownership evidence.**

API environment `WAIVER_MANAGER_TEAM_KEY` is the single analysis-target setting,
default `478.l.50505.t.9`. Compose passes it to the API. The league
`478.l.50505` is resolved from that persisted team's league association, never
from browser selection, URL parameters or saved frontend state.
**Analyze option** opens analysis only;
no Yahoo transaction is executed. **Best Supported Transaction** now answers
the global add/drop question above the preserved **Who should I
replace?**: select one player from the full configured roster, then compare
waiver players specifically against that player. Negative replacement values
mean no measured improvement: holding the selected player is preferable under
this descriptive model, not a guarantee of future performance.
The selected drop remains fixed when opening the
detailed analysis; a preferred alternative drop cannot silently replace it.
Best Overall Available is secondary context and ranks player production, not
replacement fit. Model-index changes are not predicted fantasy points, wins
or probabilities; no predictive accuracy is claimed.

Current page order:

1. Configured **Box Score Bully** header.
2. **BEST SUPPORTED TRANSACTION** or **HOLD**.
3. Separate **WATCHLIST** opportunities when measured evidence supports them.
4. **Who should I replace?** selected roster player and exact-drop alternatives
   (with factual WAIVER RULES above the roster picker).
5. **Rest of Week / Next 7 Days / Season Evidence** mode controls.
6. Secondary **Best Overall Available** and player-value context.
7. Candidate comparisons, detailed analysis and data-quality evidence.

The primary question is "What is the best supported ADD + DROP transaction
for Box Score Bully?" The secondary question remains "If I drop this exact
roster player, who is best?" Best Overall does not answer either swap question.
Analyze option, VIEW ANALYSIS and watch analysis are read-only.

Read-only contracts:

- `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers?mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...&mode=this_week|next_7_days|ros` (`player_id` is the internal identity ID)

All four default `mode` to `this_week`. The replacements endpoint requires
an integer `drop_player_id`; impact accepts it optionally. Both player IDs
refer to internal identities, not Yahoo IDs. Replacement responses include the
full roster, `selected_drop_player_id`, and each candidate's exact comparison.

**Phase 2: Best Supported Transaction** analyzes hypothetical swaps, not
Yahoo transaction history or execution. It loads the existing context once
and evaluates the saved waiver pool against every persisted manager roster
drop in memory through the same `enrich` / `compare` functions used by
replacements and impact. No second formula, percentiles, component mask or
weight tuning is introduced. Positional coverage remains bounded whole-roster
coverage; REB/BLK/STL contribute only through Yahoo points, not category needs.

**Phase 3: Evidence Intelligence** extends the same four response models with
backend-owned CURRENT ROLE, independent minutes/usage/starts quality, normalized
Yahoo status evidence and schedule coverage/import time. It derives role once
per player during the bulk context load, never per transaction pair. The
existing optimizer, exact-pair comparison invariant, points formula, production
sample gates and component weights are unchanged. Current role is descriptive,
not future minutes, usage, a starting assignment or injury-return prediction.
Cards and analysis retain the selected-drop workflow; WATCH details explain
both measured role and the evidence blocking ADD. Model version:
`waiver-evidence-phase3`.

CURRENT ROLE displays recent/comparison minutes and usage, measured deltas,
window counts/dates, supported season starts, role trend and independent quality.
Expandable source details expose medians, exact contributing/missing/stale game
IDs, source timestamps, reasons and limitations. Yahoo status remains visible
with freshness and uncertainty. SCHEDULE displays persisted games, opponents,
off-days, back-to-back pairs, calendar window, import time and coverage.
WATCH shows why a measured swap is interesting (positive descriptive index and
available evidence) separately from what prevents ADD; unsupported role is not
described as rising or projected opportunity.

Schedule resolution uses saved per-player `player_schedule` rows and the
persisted identity/team mapping; it does not infer a player's schedule from a
Yahoo team abbreviation and the general NBA daily-game table. No applicable
rows means UNKNOWN/null counts; in-window rows mean PARTIAL, never COMPLETE.
Mapping, status-source, schedule-coverage and freshness diagnostics are exposed
separately so unknown evidence is not presented as zero or healthy.
The frontend warns when the deployed model version differs from
`waiver-evidence-phase3`; do not use a stale board for a decision.

#### Source integrity, coverage and DATA GAPS

Source Integrity & Coverage is **validated locally / not deployed**. It changes
evidence/view-model diagnostics and adds explicit fail-closed status/identity
eligibility. It preserves the `waiver-evidence-phase3` scoring mathematics,
sample thresholds, ranking weights and optimizer mechanics. Every
UNKNOWN/UNAVAILABLE result should expose its most specific supported reason.
Missing, explicit zero, explicit empty, stale, unsupported and unverified are
distinct evidence states.

Source authority is split: Yahoo is authoritative for fantasy identity, league
configuration, scoring rules, roster, Yahoo status and fantasy availability.
Yahoo matchup/acquisition/waiver facts require separate verification. Persisted
NBA sources supply basketball inputs such as PTS, REB, AST, STL, BLK, TOV, MIN,
game logs, schedules and supported aggregate usage/starts. A Yahoo player
payload without basketball stats is not evidence that NBA production or
fantasy PPG is missing.

The board response includes backend-owned `coverage` and `data_gaps` in
Advanced Evidence. Coverage reports the full persisted Yahoo-pool denominator,
eligible candidate and configured roster counts, plus supported/missing/stale
production, identity mapping, schedule, status, role and acquisition coverage.
Each percentage is paired with its count and denominator; acquisition coverage
is league-context scoped. `data_gaps` groups exact counts and an evidence-based
reason under **FIXABLE DATA ISSUE**, **WAITING FOR MORE GAMES**, **SOURCE DOES
NOT SUPPLY**, **NEW SOURCE REQUIRED** and **UNVERIFIED YAHOO CONTEXT**.
An empty group is shown explicitly rather than implying a verified source.

Candidate evidence preserves raw Yahoo status, Yahoo team and NBA team
separately. Identity mapping state/reason is independent of the legacy
downstream mapping diagnostic. Only normalized-name/team-consistent persisted
links are classified as resolved; no identity is automatically created or
rewritten. Unresolved records include exact normalized-name NBA candidates
when present and a review reason. A team conflict is not evidence of a trade.
NBA ID presence alone does not override unresolved identity quality.
Stable mapping evidence may include exact ID, exact name/team, normalized
name/team, a known alias plus team, or a supported team change. Fuzzy name
alone never establishes identity, and Yahoo identity is never overwritten by
another provider. Status reasons distinguish explicit Yahoo status,
Yahoo-supplied blank, stale player-pool import, missing observation, identity
mapping issue and normalization defect (the response uses corresponding
`STATUS_PRESENT`, `YAHOO_SUPPLIED_BLANK`, `STALE_PLAYER_POOL_IMPORT`,
`MISSING_PLAYER_OBSERVATION`, `MAPPING_ISSUE` and `NORMALIZATION_DEFECT`
labels). A Yahoo-supplied blank is legitimate UNKNOWN, not healthy; only
stale/missing/mapping/normalization conditions may indicate a recoverable data
issue. Model-version mismatches make the affected surface non-decision-ready.
Structured HTTP 409 contract errors remain visible errors, never HOLD or
empty-success fallbacks.
Schedule records expose their persisted source-row count and timestamp; rows
outside the requested window produce `SCHEDULE_SOURCE_INCOMPLETE` and null
window counts when no completeness manifest exists. `NO_PLAYER_SCHEDULE_ROWS`
remains a separate root cause. Rows present mean PARTIAL; without player rows,
or with an empty requested window whose completeness is unverified, coverage
is UNKNOWN. Stale inputs remain STALE. COMPLETE is forbidden until a
completeness manifest/contract is verified. An empty window is not a verified
zero.

Persisted game logs do not currently establish supported game-level
`USG_PCT`, `GS` or `START_POSITION`. Season usage, season starter-filter
evidence and minutes are not substitutes for game-level usage or recent starts.
These are source gaps, not a reason to call the delivered descriptive Phase-3
role feature incomplete: qualified minutes can establish role while optional
usage/starts remain independently unavailable.

#### Read-only persisted-stats reconciliation

To compare saved Yahoo player-pool observations with saved NBA statistics
without contacting either provider, run:

```sh
docker compose exec -T api python -m app.features.waivers.reconciliation \
  --league-key 478.l.50505
```

The command runs a read-only database transaction and reports comparable and
non-comparable inputs, mapping/mismatch classifications, source timestamps and
the presence of named acceptance fixtures. It compares only fields present on
both sides; absent Yahoo player-pool stat fields are classified as
`NO_COMPARABLE_STAT_FIELDS` (**CROSS-SOURCE COMPARISON UNAVAILABLE**), not as
missing required Yahoo stats, missing NBA production, an absent fantasy PPG
formula or a Court IQ defect. Zero comparable Yahoo/NBA stat pairs means there
is no second persisted Yahoo statistical dataset with overlapping basketball
fields for independent cross-source value comparison. Partial overlap is
reported separately from a complete six-stat comparison. Treat the per-player
report as private. The command does not fetch from either provider or claim a
comparison succeeded when no comparable fields exist.

#### Reviewed source options (no provider calls)

No additional reviewed source met the current evidence, usefulness and
permission threshold for implementation. This does not establish that every
possible public API is unusable:

| Candidate | Documented evidence | Decision |
|---|---|---|
| [Yahoo Fantasy Sports API](https://developer.yahoo.com/fantasysports/guide/) | Official API access is application/OAuth based and subject to Yahoo policy requirements, including throttling and attribution/data-use conditions; current matchup, manager identity, transaction and acquisition semantics were not established in persisted evidence. | Existing authorized source only; no new call or scope requested. |
| [`nba_api` BoxScoreAdvancedV3 / BoxScoreTraditionalV2](https://github.com/swar/nba_api) | Community-maintained endpoint documentation describes game-level usage and starter-position fields, but the relevant docs are old and official NBA terms were not verified. | Research lead only; not cleared for implementation. |
| [BALLDONTLIE NBA API](https://docs.balldontlie.io/) | The documented free tier does not include player stats, advanced stats, injuries or lineups and is limited to 5 requests/minute; relevant coverage requires a paid tier. | Does not fill the identified free-tier gap. |
| [SportsDataIO NBA API](https://sportsdata.io/developers/api-documentation/nba) | The reviewed free trial did not include NBA access. | No eligible free NBA source established. |
| [API-Sports NBA](https://www.api-sports.io/documentation/nba/v2) | Official documentation was inaccessible during review; current terms, limits and free coverage remain unverified. | Not cleared. |
| [Sleeper API](https://docs.sleeper.com/) | Official docs describe NFL support, not NBA; the documented API is free for non-commercial use. | Not applicable. |
| Kaggle datasets | Dataset-level licenses and historical coverage vary; no current-state completeness/refresh contract was established. | Not a verified current source. |

These findings are a documentation review, not a provider probe or legal
opinion. No new provider was approved or implemented. Keep Yahoo for fantasy
identity/configuration/state and persisted NBA sources for basketball
production, schedules, logs and season stats; Fantrax remains a documented ADP
niche only. Source research is separate from implementation. Obtain explicit
authorization and verify the applicable terms before any future provider
request.

The evidence contract preserves availability, freshness, production sample
qualification, Yahoo points, current role and schedule evidence, exact ADD/DROP
comparison and supported eligibility before an actionable winner is selected.
Phase 3 enriches that existing engine, not a second recommendation path.
ADD/STREAM/WATCH/PASS retain their meanings; missing mandatory evidence yields
INSUFFICIENT EVIDENCE. No supported positive transaction means successful HOLD,
not an obligation to produce an ADD.

The transaction response contains:

- `best_transaction` or null; overall `decision` (ADD/STREAM/MUST ADD or HOLD).
- Up to five `top_supported_transactions` and five `watch_transactions`,
  ordered by descending net roster-index improvement, then ascending add ID
  and drop ID. Each pair includes add/drop evidence, mode, decision, the exact
  comparison with before/after/deltas/coverage, reasons and limitations.
- `evaluated_pair_count`, `supported_pair_count`, `watch_pair_count`,
  `excluded_pair_count` and overlapping `excluded_pair_reasons`. Counts cover
  the full assessed Cartesian product, including pre-ineligible O/NA and
  unknown-availability adds; excluded means excluded from the supported pool,
  not omitted from the assessed count. WATCH is a separate excluded subset.
- Field-level `data_quality`, limitations and factual `acquisition_context`.
  Current priority, weekly adds used/remaining and exact claim-clear time stay
  null/unverified, with no acquisition penalty.

Evidence eligibility precedes supported optimization: both add and drop need
Phase-1 current-season sample, production, status and freshness support.
Positive low-sample pairs remain WATCH, never a supported winner; unsupported
negative pairs are not presented as supported PASS. Supported nonpositive
pairs are PASS. If no supported positive pair exists, **HOLD -- no supported
waiver transaction currently improves Box Score Bully**, with
`best_transaction=null`. No least-negative or WATCH substitute. MUST ADD
remains unused without a validated stronger threshold.

HOLD is a successful evidence-based decision, not an error, optimizer failure
or missing ranking. WATCH means a positive measured comparison is blocked
from strong recommendation by evidence quality. ADD/STREAM require eligible
evidence and positive supported impact; a positive delta alone is not enough.
Missing/stale mandatory evidence fails closed. For identical add/drop/mode,
the optimizer comparison equals the selected-drop replacement comparison and
the impact comparison. No Yahoo/NBA provider calls or writes occur during
analysis; pair evaluation reuses the one loaded context in memory.

VIEW ANALYSIS displays the optimizer's exact returned pair/comparison without
silently changing the selected drop or invoking another formula. The original
selected-player workflow remains independent below the global summary. A
transaction-read failure is a visible error, not a manufactured HOLD.

All routes always resolve the configured manager team. Optional legacy
`league_key`/`team_key` query parameters must match that target or return 422;
they cannot retarget analysis. The frontend sends only mode and optional drop
ID, never arbitrary team keys. Board responses expose resolved league/team keys
and the persisted team name. A missing configured team is a visible 404 error,
not a fallback to another roster. Generic calculation services remain reusable
internally; other teams supply only the existing league-wide model context.

All read PostgreSQL only, using the existing internal identity, Yahoo payloads,
rosters/settings, NBA season statistics, game logs and NBA games. No migration
is needed. A drop ID outside the selected manager roster returns 422; an
already-rostered add returns 409. Missing league/team/player returns 404.
Configuration does not establish the current Yahoo login's team.
No transaction/scoreboard/current-week source contract is established.

Availability requires fresh explicit Yahoo ownership evidence or absence from
**every** freshly imported league team roster. The latter is labeled
`unrostered`, not a verified free agent: waiver-claim timing remains unknown.
Yahoo imports older than 24 hours or predating a newer league/team/settings
snapshot cannot establish absence. O/NA are excluded, Q/P remain uncertain,
and blank status is unknown, never healthy.

Model version `waiver-evidence-phase3`, preserving the Phase-1 scoring contract:

- **Driveway Dudes / 478.l.50505 is Head-to-Head Points, 12 teams, not a
  category league.** Persisted normalized settings and the saved Yahoo source
  must match the verified contract before analysis; disagreement returns 409
  with mismatches, never a hard-coded override. Roster:
  `PG SG G SF PF F C C UTIL UTIL BN BN BN IL IL IL`.
- Fantasy PPG is exactly `PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO`,
  using persisted modifiers and NBA `PTS/REB/AST/BLK/STL/TOV` (`TO` maps to
  `TOV`). Every required field must be present; never zero-fill. Responses
  expose per-game inputs, scoring weights and individual contributions; the
  UI shows the calculation, separately from the descriptive ranking blend.
- League rules: **continual rolling list, Standard, 2-day waiver period,
  4 adds/week, no season acquisition limit, Daily - Today, post-draft players
  follow waiver rules, injured available players may enter an injury slot**.
  **No FAAB: it is neither an acquisition assumption nor a planned feature for
  this league.** Current priority, remaining adds and exact claim-clear time
  are unverified. Acquisition value remains unavailable and excluded from ranking.

- Recent: regular-season NBA per-game production from Pacific dates today minus
  14 days through today, inclusive, in the imported league's NBA season,
  scored only with supported persisted Yahoo points modifiers. Missing required
  stats are not zero-filled. The oldest selected log import must be within seven
  days and the latest selected game date within seven days.
- Weekly and Next 7 Days player value use recent PPG blended with independent
  prior-season regular-season PPG when fresh supported history exists:
  recent weight `n/(n+10)`, historical weight `10/(n+10)`. This is descriptive
  shrinkage, not a projection or calibrated confidence. Prior-season history
  does not substitute for missing/stale recent logs. Without supported prior
  history, raw recent value remains explicitly limited evidence.
  Current-season evidence quality is backend-owned: **20+ EXCELLENT,
  10-19 GOOD, 7-9 LIMITED, 4-6 VERY LIMITED, 1-3 INSUFFICIENT FOR STRONG
  RECOMMENDATION, 0 NO CURRENT-SEASON EVIDENCE**. This is not probability.
  Prior-season history never bypasses the current-season sample gate.
- Season Evidence (`ros`): latest eligible persisted regular-season per-game history, **not a
  projection**. Each mapped player uses their latest season no later than the
  imported league season; missing league season uses the current Pacific year as
  cutoff. Imports older than seven days cannot supply scored value or hold-label
  evidence; historical values can remain visible with stale quality.
- Yahoo scoring settings and roster slots must be imported within 24 hours to
  supply scoring/fit. The selected roster must also be fresh within 24 hours
  and not predate later league/team/settings imports.
- Value scores use deterministic midrank percentiles of the imported league
  pool, with ties equal. Role compares the latest three and preceding three
  regular-season games inside the existing 14-day lookback. Both sides require
  three valid fresh inputs; windows are fixed by date/game ID, not backfilled
  after missing/invalid/stale observations. MIN must be finite and nonnegative;
  game-level `USG_PCT` must be finite and in [0,1]. Imports and latest game must
  be within seven days. Missing fields are unavailable, never zero.
  For each supported metric, both mean and median deltas **>= +3.0 minutes**
  (usage **>= +0.02**, two percentage points) establish rising direction;
  both **<= -3.0 minutes** (usage **<= -0.02**) establish falling direction.
  Boundaries are inclusive; deltas are rounded to six decimal places before
  classification. Both strictly between the negative and positive threshold
  establish stable direction; disagreement is insufficient, not STABLE.
  This prevents a single outlier establishing direction.
  Disagreeing mean/median directions, opposing supported minutes/usage
  directions or inadequate minutes windows yield INSUFFICIENT EVIDENCE.
  Qualified minutes can establish role without optional usage/starts; those
  inputs retain their independent unavailable/partial/stale states.
  With qualified minutes and no conflict, either supported metric rising
  gives RISING, either falling gives FALLING, otherwise STABLE.
  Import age exactly seven days and latest game exactly Pacific today minus
  seven days remain within the implemented boundary; older evidence is stale.
- Opportunity exposes its raw `score` and `score_parts`. Only qualified role
  can supply a score: recent minutes/36*100, optional measured usage change
  `50 + delta*100`, and optional fresh explicit season start rate*100, each
  bounded 0-100 and averaged once. Minutes level and minutes change are **not**
  separate scored parts. Unqualified role supplies no neutral/average score.
  Season starts require explicit current-season `starter_filter.GP` matching
  saved starts, positive games, valid bounds, >=3 season games and a fresh
  import to score. An absent starter row is not zero starts. Smaller supported
  season samples remain partial context. Season usage is context only, not a
  substitute for missing game-level usage or a usage delta. Recent starts
  remain unavailable without a supported game-level source.
- Schedule counts persisted non-final/non-cancelled/non-postponed games,
  off-days (at most five persisted NBA games), back-to-back pairs and opponents.
  Coverage is PARTIAL with rows and UNKNOWN without rows; COMPLETE is never
  asserted without a completeness manifest. No rows means unknown, not zero.
  Import timestamp and freshness are separate from coverage. The UI always
  calls `this_week` **Rest of Week**: Pacific
  today through Sunday inclusive. With fewer than two inclusive dates remaining,
  it additionally warns **limited days remaining**; Sunday is a one-day window.
  Next 7 Days includes Pacific today and the following six dates, using that
  separate schedule window for its ranking. Neither is a verified Yahoo week.
  Season Evidence's schedule ends June 30
  after the imported season start year (or today if that date has passed).
  Imports older than seven days do not supply a schedule score. These are not
  verified Yahoo periods, lineup starts, or complete future coverage.
- Waiver timestamps and date-window boundaries use `America/Los_Angeles`
  (PST/PDT automatically), independent of browser/server local time.
  Stored timestamp instants remain UTC and freshness uses the same elapsed
  24-hour/seven-day limits; changing the display/calendar zone does not extend
  evidence freshness. NBA persisted game dates are date-only inputs, not
  newly verified tip-off times or Yahoo matchup boundaries.
- Positional fit is bounded 0-100: the percentage of required starting slots
  coverable from Yahoo eligibility. For a player it describes roster coverage
  with that player, not player quality. The swap measures coverage **once** per
  roster, not a sum of marginal matching contributions; two fully covered
  rosters have zero fit delta regardless of reassignment/UTIL flexibility.
- Before/after impact is a 0-100 roster index: non-fit components are roster
  means, fit is whole-roster coverage. Each component delta is bounded -100
  to +100. Both sides and all compared replacements use identical weights,
  fixed league production percentiles and a fixed common measured-component
  mask across the manager roster and eligible scored pool. Optional evidence
  missing anywhere in that comparison population is omitted, not zero-filled.
  Responses expose component before/after/deltas, effective weights and
  matched starting slots. Missing roster values prevent numeric impact.
  Explicit drop IDs override open-slot/preferred-drop logic. Generic no-drop
  analysis remains available internally when imported capacity has room.
- Replacement lists rank supported net improvement descending, then stable
  internal ID, with unavailable comparisons last. Without a selected drop the
  generic board retains weighted-overall ordering. A single best-team ID
  requires positive impact, fresh critical evidence and at least seven
  current-season games for both add and drop; short windows also require
  seven recent games. Backend decisions are MUST ADD, ADD, STREAM, WATCH,
  PASS and INSUFFICIENT EVIDENCE. No MUST ADD is forced. Positive 1-6-game
  results are WATCH, never Best Add, even with strong prior history.
  Supported nonpositive swaps are PASS; if all measured replacements are
  nonpositive the primary answer is **HOLD [selected player]**, not a
  least-negative Best Add. Top alternatives remain available for comparison.
  Missing/stale settings, roster, availability, production or unverified
  Yahoo status blocks strong recommendations, not merely warnings.
  Opportunity-led ADD (opportunity exceeds all other weighted positive gains
  combined) requires qualified fresh role for both players. Schedule/opportunity-led
  short-term swaps require fresh measured schedule, available opportunity and
  qualified fresh role for both players for STREAM; partial coverage is disclosed.
  Role never bypasses either player's seven-game production gate.
  Role/minutes/usage/starts/status/schedule quality exposes available, partial,
  unavailable or stale states, counts and source time/reason. O/NA are excluded,
  Q/P remain uncertain and blank Yahoo status remains UNKNOWN, not healthy.
  The shared quality contract also retains `missing`, `unknown` and
  `unsupported` for other evidence fields; these are not new Phase-3 labels.
  Yahoo status age exactly 24 hours remains within the boundary; older status
  cannot support a strong action. No recovery/severity forecast, expected
  availability date or injured-teammate replacement permanence is established.
- Defaults: fit 35%, player value 25%, opportunity 15%, schedule 15%,
  acquisition value 10%. Set API environment `WAIVER_WEIGHTS` to a JSON object
  with keys `roster_fit`, `player_value`, `opportunity`, `schedule`,
  `acquisition_value` (for Compose, inject it through a deployment override).
  Nonnegative finite values with a positive sum are required. Missing
  components are omitted with explicit effective-weight renormalization;
  player value and roster fit are mandatory for an overall score.
- Hold labels are cautious heuristics: longer-term hold requires at least 20
  historical games, sufficient current-season evidence, a historical value percentile of at least 60 and at least
  24 recent minutes/game; streamer requires rising minutes, measured recent
  value and a weekly/Next 7 Days schedule percentile of at least 60. Otherwise undetermined.

Unavailable: category waiver scoring/impact (existing Championship HQ category
baselines remain unchanged), acquisition value, ownership percentages,
opponent bidding/demand, matchup difficulty, injury-return forecasts, validated
projections, calibrated confidence/probabilities, and What Changed/history.
Yahoo transactions are not executed. No predictive accuracy is claimed. Refresh Yahoo and NBA data
through the existing import workflow; Reload only rereads persisted evidence.
Field-level quality, sample sizes, limitations and source timestamps are
included in the API and analysis modal.

Focused tests: `python -m pytest -q tests/test_waivers.py` in the backend
(set both `DATABASE_URL` and `TEST_DATABASE_URL` to a disposable PostgreSQL
database), `npm test`, `npm run build`, and
`npm run test:waivers:browser` in the frontend. Browser tests require Playwright
Chromium (`npx playwright install --with-deps chromium` or the matching
Playwright 1.56.1 container) and exercise desktop/mobile layouts, keyboard
modal focus, API errors, mode changes, zero transaction writes and axe
accessibility checks against synthetic API fixtures, not live Yahoo.

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
- `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros` (hypothetical supported add/drop analysis, configured manager team)
- `GET /api/v1/waivers?mode=this_week|next_7_days|ros` (configured manager team)
- `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/{player_id}/impact?mode=this_week|next_7_days|ros&drop_player_id=...` (configured manager team)
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

- `/` presents the Championship HQ foundation/category baseline and Yahoo
  connection alongside the preserved observer/practice setup. The observer
  workflow uses Yahoo URL/Connect after pairing; missing Mock/Real or slot
  evidence prompts a follow-up. Saved rooms and advanced setup remain available.
  Internal mocks use an explicit or
  previewed seeded order; Live Draft permits pending manager position and
  incomplete team mapping.
- `/draft/:sessionId` is the shared mock/live room: `DraftRoomPage` composes the decision card, roster, timing window, server-ranked board, recent picks, explanations, fallback alternatives, and data-quality panel. Mock rooms add opponent auto-pick-next, auto-pick-until-manager-turn, pause/resume, manager-selected picks, latest-pick undo, reset/new-mock, and standalone removal controls. Live rooms support sequential manual picks, correction, undo, and targets.
- `/waivers` is the decision-first read-only Waiver Center described above:
  configured Box Score Bully, Best Supported Transaction or HOLD, separate
  WATCHLIST, preserved exact-drop replacements, Rest of Week, Next 7 Days,
  Season Evidence, secondary Best Overall and detailed comparison/data quality.
  Global detail uses the returned optimizer pair. Reload rereads saved data;
  it does not refresh a provider or execute a transaction.
- Internal session setup is split into league/team selection, order/mode selection, and session creation. No team order or manager identity is guessed from Yahoo data.

### State and API Contracts

The client uses route-local React state as a cache of backend view models. The room refreshes the board every five seconds and after each successful mutation. Pick and target writes send the observed session version; HTTP 409 pauses writes and presents a reload action. Internal mock batch picks run in a serialized background worker; the room polls the same session board and displays the same backend decision view. Replay is read-only. The client never calculates utility, survival, scarcity, wait cost, roster fit, snake timing, opponent picks, or player rank.

Backend additions for the UI include explicit live-session creation, separate live/mock session lists, source-checked mock actions and standalone mock removal, server-owned timing on session state, and `GET /api/v2/draft/sessions/{session_id}/board` for the latest snapshot-backed recommendation, current server-sorted candidates, data-quality statuses, and the manager's matched roster slots. Board sort modes are `decision`, `value`, `survival`, and `name`; search and simple filters do not alter recommendations. Snapshots retain compact ranked display rows, not per-player full explanations or fallback models. Both pick flows retain session-version checks; stale writes return HTTP 409.

Loading, empty league/player-pool, API errors, draft conflicts, unavailable recommendation evidence, and unknown/stale survival have separate UI states. Yahoo OAuth is linked when no imported league is available. Recent picks, corrections, undo, and target changes are written through the existing v2 endpoints.

### Mobile and Accessibility

The desktop room uses a two-column decision/board layout; below tablet width it stacks the decision first and keeps the player table horizontally scrollable. Controls have labels, icon-only actions have accessible names, decision/status is not color-only, the correction dialog has dialog semantics, and keyboard focus/reduced-motion preferences are supported.

### Calculation Boundaries

Draft category fit remains unavailable; Championship HQ's separate factual
category baseline does not establish category-aware waiver impact. Survival
remains `heuristic_unvalidated`; market ADP coverage is partial. Rule-based
opponent selection and a mock sync rehearsal are implemented; no Monte Carlo or
calibrated simulation, opponent-demand model, alerts, or transaction automation
is established.

## Scope

The draft module remains supported and preserved. Championship HQ category/team
baselines and the read-only Waiver Center are implemented post-draft capabilities.
The baseline is descriptive, not authenticated team ownership. Persisted
descriptive role/status/schedule intelligence is implemented; richer authorized
game-level usage/starts and injury-source evidence, verified Yahoo source semantics, validated forward projections,
opponent demand, What Changed/history, outcome calibration and transaction execution
remain evidence-gated follow-ups in [next actions](docs/status/next-actions.md).
Category-weakness optimization is not a priority for this Head-to-Head Points
league; the Championship HQ category baseline remains descriptive only.
Start/Sit, broader trade/league intelligence, a Decision Journal, and
playoff/championship planning remain outside the implemented waiver contract.
Calibrated probabilities require historical validation first. Existing mock
simulation is not a calibrated forecast. Production Live source cadence/mapping
and full manual fallback/correction/recovery acceptance remain unverified; Yahoo
Mock Practice does not validate Production Live. No external provider is called
by v2 session reads or calculations.
See [current state](docs/status/current-state.md),
[project memory](docs/project-memory.md), and
[draft persistence ADR](docs/adr/0005-draft-state-persistence.md).

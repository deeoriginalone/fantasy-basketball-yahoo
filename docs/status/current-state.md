# Current State

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

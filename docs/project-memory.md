# Project Memory

## Product Boundaries

- Yahoo is authoritative for fantasy-league/player identity, configuration,
  and state. `player_identity.id` is the internal cross-feature key; market
  feeds never overwrite Yahoo identity fields.
- Persisted NBA and authorized external data provide basketball inputs.
  Persist inputs before calculations; a gateway HTTP result alone is not
  evidence of successful persistence. Missing/stale data stays unavailable.
- The backend owns deterministic calculations, projections, simulation, and
  decisions. The frontend presents prioritized actions and explanations, not
  duplicate calculation logic. Future projections/simulation require explicit
  methods and validation; draft heuristics do not establish those capabilities.
- Decision history is the audit/learning layer. Preserve input/source evidence,
  versions, alternatives, and uncertainty; do not equate an audit trail with
  proven decision accuracy.
- Never surface a statistic as a primary result without explaining why it
  matters to this roster/matchup and what decision it informs.
- Draft functionality and persisted history are preserved modules after the
  final draft-era baseline. Championship HQ is the post-draft direction, not
  an already implemented or validated product.

## Canonical Draft Architecture

- Reuse normalization/reconciliation, session row locks, sequential pick
  handling, optimistic versions, conflicts, audit events, and recommendation
  snapshots. No parallel reconciler or "fastest source wins" behavior.
- v1 utility is stateless. v2 persists sessions/picks/targets and calculation
  snapshots; mutation/version contracts remain canonical. Corrections and
  latest-pick undo use the existing event/snapshot pipeline.
- Global picks determine availability/run context; only manager selections
  populate manager-roster inputs. Opponent selections are not manager demand.
- Ordinary session creation requires a complete explicit team-slot map.
  Live creation permits pending manager position and partial mapping;
  first-round authoritative picks discover order, later rounds validate known
  slots, and manager timing/recommendations require explicit slot confirmation.
  Unknown team identities are not invented. Order conflicts preserve evidence
  and stop automatic discovery until explicit resolution.
- Internal Mock Live Draft, synthetic Mock Sync Rehearsal, Yahoo Mock Practice,
  and Production Live are separate workflows. Internal mocks are seeded,
  rule-based practice; they do not mutate Yahoo state. Mock/practice evidence
  never validates Production Live.
- Production Live uses authenticated Yahoo `draftresults`, Sync Now,
  pause/resume, Quick Record/manual fallback, and conflict protection.
  Active-draft provider acceptance remains unverified; polling is not push
  streaming and the application interval is not a Yahoo-approved cadence.

## Read-Only Browser Observer

- One-time Windows install/pair; subsequent mocks use Yahoo draft URL + Connect.
  Dedicated Windows Chrome exposes CDP only on `127.0.0.1`, never the LAN.
  Do not assume Linux loopback reaches Windows.
- The observer reads authoritative Yahoo Picks player IDs and sends bounded
  observations over trusted HTTPS through the existing reconciler into
  disposable Yahoo Mock Practice. It never selects/submits Yahoo players.
  Browser-based Production Live writes are not enabled or verified.
- Missing/ambiguous evidence fails closed. Use a verified single-slot fallback
  when necessary; do not guess opponent mappings, rounds, or team count.
  The current practice bridge supports 12-team mocks and requires verified
  rounds and manager slot before initialization.
- Normal operation is windowless/background with bounded sanitized logs;
  diagnostics are not the normal operator workflow. After pairing, normal
  users do not hand off session IDs or re-enter credentials for every draft.

## Recommendation Invariants and Verified Limitations

- BEST PICK NOW ranks current adjusted roster value using historical
  Yahoo-weighted production, replacement value, scarcity/need, construction,
  durability, risk, upside, and recent run context. WAIT ANALYSIS is a separate
  ADP/survival/fallback decision; ADP does not directly determine BEST PICK NOW.
- Roster matching prioritizes starting positions before UTIL/bench and credits
  newly filled slots through incumbent reassignment. UTIL/bench credit is
  bounded; open UTIL/bench does not create positional need. Current board reads
  can recalculate legacy roster-fit results without rewriting old snapshots.
- Why this rank explains manager-roster score/rank contributions, not
  predictive accuracy. Historical production is not a future-season
  projection; small score differences do not prove real-world superiority.
- Yahoo O/Out and NA/Not Active are excluded from normal recommendations,
  best value at risk, and wait/fallback candidates. Q/P remain eligible with
  uncertainty. Blank/unrecognized status is unknown, never confirmed healthy.
  Historical metrics remain visible; no injury penalty or return forecast is
  inferred. Status refresh is player-pool-import-based, not continuous.
- Missing mappings/statistics leave players unscored; preseason samples remain
  explicitly distinguishable from regular-season inputs.
- Fantrax supplies partial ADP coverage, not draft rank, XRank, frequency,
  sample size, or an upstream source-updated timestamp. Retrieval age is the
  available freshness signal; the application stale threshold is 48 hours.
- Survival/wait estimates are uncalibrated heuristics. Opponent roster demand,
  category calculations, Monte Carlo forecasts, historical outperformance,
  and post-draft championship/projection accuracy are not established.
- Later Windows mock acceptance does not resolve unverified Production Live
  source or full manual fallback/recovery browser acceptance.

## Migrations and Operational Safety

- Draft tables have versioned transactional migrations through
  `0006_observer_connections`, separate from legacy metadata bootstrap.
  Migration up/down/up is tested only on isolated PostgreSQL.
- Production downgrade is destructive: it removes draft sessions, picks,
  events, snapshots, and targets. Never validate with a production downgrade.
  Take a fresh private backup and obtain change approval before deployment or
  migration; preserve pre-existing draft and identity state.
- NBA imports precede metric recomputation; ordinary reads/calculations use
  persisted inputs. The 600-second proxy timeout is scoped to the exact
  NBA-import route, not all APIs.
- Do not re-import providers or mutate production for documentation validation.
  Do not bypass TLS validation. The API has no general user authentication and
  must remain on a trusted network.
- Keep credentials, observer secrets, private backups, operational
  fingerprints, and sensitive runtime values out of source control and reports.

See [current state](status/current-state.md) for dated evidence,
[next actions](status/next-actions.md) for unresolved work, and the
[final draft-era session record](sessions/2026-10-18.md) for closeout history.

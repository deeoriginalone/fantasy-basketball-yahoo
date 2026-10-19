# Next Actions

Only unresolved work is listed. The draft-era baseline is closed; preserve the
draft module, persisted history, and fallback workflows rather than deleting
them. The primary roadmap is now **Championship HQ**. Everything below is
future work, not a claim of implemented post-draft capability.

## Championship HQ - Ordered Roadmap

1. **Championship foundation / Yahoo post-draft state.** Establish an
   authoritative, persisted current-season league/team/roster baseline from
   authorized Yahoo state, including scoring, roster eligibility, and available
   matchup/transaction context. Define refresh/freshness and missing-data
   contracts; verify source-to-storage-to-read behavior in isolation before
   product claims. Never substitute draft-session picks for Yahoo's actual
   post-draft roster. Confirm the real league's draft state rather than assuming
   completion from this baseline.
2. **Category + team identity engine.** Deterministically explain roster
   strengths, weaknesses, category direction, and constraints from verified
   settings and persisted inputs; support the league's actual scoring format
   without inventing category evidence.
3. **Schedule utilization.** Persist authorized schedules and explain playable
   games, congestion, off-night opportunities, and roster-slot constraints.
4. **What Changed? + Action Center.** Turn verified state/data changes into
   prioritized roster/matchup actions with source freshness, rationale, and
   explicit uncertainty; do not lead with disconnected statistics.
5. **Player projections + Start/Sit.** Define reproducible backend projection
   inputs/methods and lineup constraints; evaluate against held-out outcomes.
   Distinguish projections from historical averages and heuristic scores.
6. **Streaming + Waivers.** Rank feasible pickups/drops using roster needs,
   schedule, league rules, and known acquisition constraints; explain the
   decision and opportunity cost without fabricating availability.
7. **Opponent/matchup intelligence.** Use authoritative opponent rosters and
   matchup state to explain strengths, exploitable gaps, and counter-actions.
8. **Trade engine.** Evaluate both roster impacts, league constraints,
   alternatives, and uncertainty; no unsupported acceptance probabilities.
9. **League intelligence.** Explain league-wide trends, roster behavior, and
   competitive context using authorized persisted evidence.
10. **Decision Journal.** Productize an audit/learning layer recording action,
    alternatives, inputs, rationale, model version, and eventual outcomes.
    Existing draft events/snapshots remain intact; earlier decision surfaces
    must retain enough provenance for this journal.
11. **Playoff + Championship engine.** Combine verified format, schedule,
    roster, opponent, and decision inputs into explainable scenario planning.
12. **Calibrated probabilities only after historical validation.** Obtain
    suitable historical state/outcomes, prevent leakage, and evaluate held-out
    calibration before displaying probability claims. Until then label
    heuristics/scenarios explicitly; unknown remains unknown.

## Product and Decision Contracts

- **Yahoo:** fantasy-league truth for identities, configuration, and state.
- **Persisted NBA / authorized external data:** basketball inputs, with
  provenance, coverage, and freshness; reads/calculations do not silently import.
- **Backend:** deterministic calculations, projections, simulation, and
  decisions, with explicit method/version and uncertainty boundaries.
- **Frontend:** prioritized actions and explanations, not a second calculation
  engine.
- **Decision history:** audit and learning, not retrospective proof of accuracy.

**Hard rule:** Never surface a statistic as a primary result without explaining
why it matters to this roster/matchup and what decision it informs.

## Draft Follow-up

- At the next authorized active draft, separately accept official Yahoo
  `draftresults`, mapping/cadence, pause/resume, conflict and recovery behavior,
  plus Quick Record/correction/undo in a safe disposable browser session.
  Windows mock acceptance does not validate Production Live. Preserve official
  polling and manual fallback; do not enable browser-based Live writes without
  separate review/acceptance.
- Resolve unscored identities and improve partial ADP coverage only through
  authoritative mappings and permitted sources. Recheck stale/import-based
  inputs when the draft module is used; never fill gaps by inference.
- Historical draft evaluation/calibration remains blocked on contemporaneous
  picks, ADP, and outcomes. Keep wait/survival uncalibrated and opponent demand
  unavailable until supported by verified data and validation.

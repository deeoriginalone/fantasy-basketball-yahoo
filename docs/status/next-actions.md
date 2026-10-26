# Next Actions

The Waiver Center is implemented and closed out as a database-only, descriptive
post-draft capability; generic "waivers" is no longer future scope. Selected-
player replacement rankings, fixed-drop impact, bounded roster coverage,
small-sample labels, Next 7 Days, Phase-2 Best Supported Transaction, and
Phase-3 descriptive role are implemented. Hypothetical transaction analysis is
not Yahoo transaction history or execution.

Source Integrity & Coverage is **validated locally / not deployed**. Its final
guarded persisted acceptance and the dated snapshot are recorded in the
[current-state report](current-state.md) and
[2026-10-26 session record](../sessions/2026-10-26.md). There is no remaining
acceptance blocker. The follow-ups below require separate evidence and
authorization; they do not invalidate local validation. Dated acceptance
counts are not current population claims.

Driveway Dudes is Head-to-Head Points, not categories. Fantasy PPG uses
`PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO` from persisted Yahoo settings.
It uses a continual rolling waiver list, **not FAAB**. `ros` is labeled
**Season Evidence**, historical/stat-based and not a projection.

## Remaining Evidence Roadmap

### SLICE 1 — EXISTING EVIDENCE / NO NEW PROVIDER

1. **High-confidence Yahoo-to-NBA identity reconciliation**
   - Resolve only from stable persisted evidence.
   - Never fuzzy-map on name alone or infer trades/team changes from conflict.
   - Preserve ambiguous, no-match and team-conflict cases for review.
2. **Existing NBA source capability audit**
   - Determine whether the existing source can provide game-level `USG_PCT`,
     `GS`, and `START_POSITION`.
   - Distinguish available-but-not-imported fields from unsupported or
     unverified source capability.
3. **NBA schedule completeness**
   - Determine whether the existing source contract can establish COMPLETE.
   - Row counts, all teams, date span and opponents alone do not prove
     completeness; preserve PARTIAL/UNKNOWN unless a contract proves it.

Do not prioritize another generic NBA provider before this slice establishes
whether the existing NBA source can close these gaps.

### SLICE 2 — YAHOO AUTHENTICATED IDENTITY

4. Verify authenticated Yahoo manager/team identity using explicit source
   ownership evidence. Configured Box Score Bully, a team name, roster contents
   or draft selections are not ownership proof.

### SLICE 3 — YAHOO SCOREBOARD / PERIOD

5. Verify the Yahoo scoreboard/matchup source contract.
6. Verify matchup-week/current-week/date semantics.
7. Verify stable participating team keys.
8. Verify correction/update and completeness semantics.

Rest of Week and Next 7 Days remain local Pacific calendar windows until this
slice is proved.

### SLICE 4 — YAHOO TRANSACTION / ACQUISITION CONTEXT

9. Verify weekly acquisitions used.
10. Verify weekly acquisitions remaining.
11. Verify current rolling waiver priority.
12. Verify player waiver/free-agent state where supplied.
13. Verify exact claim-clear evidence where supplied.
14. Verify transaction stable IDs and type/status/date/team/player fields.
15. Verify pagination and correction/update semantics.

Do not infer these values from league rules: four adds per week is not
remaining adds; a continual rolling list is not current priority.

### SLICE 5 — REASSESS SOURCE GAPS

16. Evaluate richer injury/status evidence only if Yahoo status remains
    materially insufficient after preceding source work. Any new provider
    requires a documented contract, permitted use, stable identity, freshness
    and persistence semantics, failure preservation, tests, and a demonstrated
    material evidence gap.

### SLICE 6 — LATER MODEL / METHOD WORK

17. **Matchup quality:** require a verified source and validated method;
    opponent identity alone is not matchup difficulty.
18. **Validated forward projections:** Season Evidence remains historical;
    define inputs, method and error evaluation before prediction claims.
19. **Opponent demand:** do not infer intent or bidding from roster/draft
    behavior without validated evidence and method.
20. **What Changed / recommendation history:** define the persisted evidence
    snapshot, diff and version contract first; current waiver GETs remain
    non-writing.
21. **Outcome tracking/calibration:** define outcomes and sample coverage
    first. Evidence-quality labels are not probabilities; make no calibrated
    probability claims without validation.
22. **Yahoo transaction execution — LAST:** require a separately verified
    Yahoo write contract, authenticated ownership, state/rules/limits,
    idempotency/conflict behavior, explicit user confirmation and an audit
    trail. Hypothetical transaction analysis does not authorize execution.

## Early-Season Evidence Limit

Current-season samples may simply require more games. Legitimate early-season
small samples are not a source defect, and prior history never bypasses the
at-least-seven-current-season-game strong-action gate. Do not lower evidence
gates or tune weights to manufacture a winner.

## Secondary Draft-Era Leftovers

These remain secondary to Championship HQ/Waiver post-draft work and are not
the immediate development priority.

### Production Live

- Actual active-draft Yahoo `draftresults` behavior remains unverified.
- Source cadence and mapping remain unverified.
- Full manual fallback/correction/recovery browser acceptance remains
  unverified.
- Yahoo Mock Practice does not validate Production Live.

### Draft intelligence

- Fantrax ADP coverage remains partial; it does not establish draft rank,
  XRank, frequency, sample size or upstream update timestamp.
- Survival/wait remains heuristic and uncalibrated.
- Historical engine-versus-ranking outperformance remains unproven.

## Explicitly Unsupported / Non-Priority Work

- No FAAB for this configured league.
- Category-weakness waiver optimization is not a priority for this H2H Points
  league.
- No injury return-date forecasts or fabricated ownership percentages.
- No opponent bidding/demand claims or unsupported matchup difficulty.
- No inferred Yahoo matchup period.
- No calibrated confidence/probabilities or predictive-accuracy claim.
- No Yahoo transaction execution absent the final roadmap gate.
- No source gap may be converted to zero merely to score it.

## Historical Yahoo Source Authorization Notes

These notes preserve source-evidence chronology and safety boundaries; the
ordered roadmap above controls priority. They are not evidence that a new Yahoo
contract has passed, and they do not authorize a provider call.

- The 2026-10-19 source-evidence attempt found an expired stored access token;
  no Yahoo HTTP request was sent and no endpoint contract was established.
- On 2026-10-25, normal authorization recovery and a supported `teams` canary
  allowed existing imports. That did not establish manager ownership,
  scoreboard/matchup or transaction semantics.
- Candidate `league/{league_key}/teams`, `scoreboard` and `transactions`
  resources are not verified contracts merely because a path exists or a
  request succeeds. Explicit ownership, stable keys, week/date meaning,
  transaction fields, pagination and correction/update behavior require
  representative evidence.
- When separately authorized source work resumes, stop on authorization or
  rate-limit evidence. Never refresh OAuth or retry merely to reconcile these
  docs; do not alter credentials/scopes, probe unrelated leagues, replay
  callbacks, publish private payloads, scrape or use browser CDP as a source.
- Only after a source contract and permitted use are verified may a controlled,
  idempotent, failure-preserving persistence/import path be implemented.

All source work requires separate authorization. Do not refresh Yahoo or NBA,
start OAuth, call Fantrax, write database rows, migrate or execute Yahoo
transactions as a side effect of documentation or evidence review.

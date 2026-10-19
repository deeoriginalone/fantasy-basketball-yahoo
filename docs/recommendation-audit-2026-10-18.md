# Recommendation and data-quality audit - 2026-10-18

## Final status/Windows hardening acceptance - supersedes earlier readiness scope

Butler's ordinary recommendation exposed a genuine missing current-status gate.
Historical utility/risk is not current injury evidence. The deployed gate now
separates unchanged player value from normal recommendation eligibility.
No weights, Yahoo parsing, NBA metrics, Fantrax inputs, providers or projections
changed in this hardening release.

### Source evidence and eligibility

Existing authorized player import returned HTTP 200, 744 players, 11 new
authoritative Yahoo identities, 181 updated and 552 unchanged, committed at
2026-10-18 22:15:42.398009 UTC. Before refresh the pool was 733 players:
488 null, 127 NA, 20 O, 1 P, 97 Q. Fresh counts and literal persisted
Yahoo `status_full` meanings:

| Code | Count | Yahoo meaning | Normal recommendation policy |
|---|---:|---|---|
| O | 28 | Out (short-term injury) | Excluded |
| NA | 217 | Not Active | Excluded |
| P | 1 | Probable | Permitted with explicit status uncertainty |
| Q | 62 | Questionable | Permitted with explicit status uncertainty |
| null | 436 | No status supplied | Unknown; never labeled healthy |

Unrecognized future codes remain literal/unknown, not guessed or automatically
excluded. The source's wording is not an implemented recovery forecast.
All prior 733 internal/Yahoo/NBA identity associations match the pre-refresh
archive; no NBA/Fantrax identity substitution occurred.

O/NA players stay on the board with historical scores/metrics and a prominent
status/exclusion explanation. They cannot be BEST PICK NOW, best value at risk,
or any normal wait fallback; their wait/survival action signals are unavailable.
Value ranks in Why this rank include the board pool, including excluded players;
eligibility is separate. P/Q/null do not change historical rankings.
Status retrieval time comes from real pool observations, not copied mock
observation timestamps. There is no continuous injury/status feed or new
staleness prediction. Re-run the existing authorized import when needed.

Current boards detect missing policy evidence or changed statuses and recompute
their displayed result read-only. Saved snapshots and explicit historical replay
are not rewritten. The deployed prior Butler board now shows status O,
historical fantasy value 37.27, no wait/survival signals, and another best pick.
For blank-status Kawhi, "Unknown" means no Yahoo status reported, not an injury
finding and not confirmed health; he remains recommendation-eligible.

### Windows normal-launch behavior

The normal desktop entry is pythonw. The explicit console-producing helper
processes in this design are powershell.exe for listener verification and Chrome
recovery; legacy developer PowerShell entrypoints also intentionally use a
console. The original offending Windows PID/command line was not captured, so
which installed invocation caused the owner's old blue window is not proven.
Current-source CREATE_NO_WINDOW alone was not proof of the installed version.

Normal launches now use pythonw (including a windowless bootstrap for accidental
python.exe invocation), CREATE_NO_WINDOW plus STARTF_USESHOWWINDOW/SW_HIDE and
PowerShell WindowStyle Hidden. Reinstallation stops only the exact installed
pythonw/desktop.py agent before replacing files, preserves DPAPI configuration,
pairing and Chrome, and starts normally rather than forcing setup again.
An explicit Diagnostics shortcut remains separate. Type/event-only local logs
are bounded to 256 KiB plus two backups, without credentials/URLs/tracebacks.
Loopback-only CDP, read-only design, privileges and firewall behavior are unchanged.

The owner updated Windows without re-entering the secret and explicitly reported
no console/flash during startup, tracking and reconnect. This is actual owner
visual evidence, not Linux execution or an instrumented original-process trace.
The paired UI hides INSTALL OBSERVER; the existing direct installer URL was
provided for this one-time upgrade.

### One new actual mock

Safe room path `/draftclient/nba/2816651/7`, disposable session
`f62f5674-207b-407c-8206-8819b3a9aab1`, slot 7. Acceptance captured 23 contiguous
unique Yahoo-ID-mapped picks/events, 24 versioned snapshots and two identical
readbacks without extra events. All snapshots keep opponents out of manager
roster inputs and pass the status gate. The owner made all Yahoo selections.

| Manager selection | Before BEST PICK / decision | After BEST PICK / decision | Manager roster after |
|---|---|---|---|
| Luka Doncic, 7 | Luka, 83.2027 | Maxey, 67.6070 | Luka |
| Kawhi Leonard, 18 | Kawhi, 68.6451 | Brown, 66.3327 | Luka, Kawhi |

Before/after persisted responses equal deterministic recalculation. Utility,
mode/run and roster-impact additive arithmetic match exactly within numerical
tolerance. Selected players leave availability. Butler remains represented and
excluded throughout. The served browser displayed source-status indicators and
245 excluded board players, with BEST PICK NOW separate from WAIT ANALYSIS.
The new real pool has 682 existing scored metrics and 62 unscored players after
11 new identities; no metric evidence was fabricated or recomputed for this fix.

### Final release validation and remaining scope

Focused regressions include high-value O/NA eligibility, unchanged scores,
next eligible recommendation, no excluded fallback, P/Q/null/unrecognized codes,
legacy current-board refresh without historical rewrites, identity/status
reimport preservation, hidden process options/bootstrap and bounded logs.
Final validation ran once: 138 backend tests, 23 frontend tests, strict
production frontend build, 58 Python source compilations, Compose validation,
both affected images and git diff --check passed. Only the pre-existing
Starlette/httpx deprecation warning remains. Trusted API health, served installer
payload and actual status-gated board were checked after release. A verified
107,136,079-byte private archive (0600) preceded deployment.

All pre-existing session/pick/event/snapshot full-row hashes remain identical,
excluding only the single new practice. Intended Live session/version 1 remains
unchanged. This accepts the current-status gate and tested mock operation,
not injury forecasting, calibrated survival, upcoming-season projections,
automatic production draftresults or superior player advice.

## Final post-refresh acceptance - 22:00 UTC

Owner authorized release of the already-tested rank explanations and scoped
import timeout. A fresh private 98,647,803-byte archive backup (0600, archive
directory verified) preceded API/frontend-only deployment. All pre-existing
draft row hashes matched immediately afterward; migration remains 0006.
No recommendation weights, source architecture or objective changed.

Presentation now explicitly groups BEST PICK NOW / highest current adjusted
roster value / pre-adjustment roster utility / Why this rank separately from
WAIT ANALYSIS / action / reason / unvalidated survival and wait cost.

The released frontend image passed an isolated, exact-route
`POST /api/v1/nba/import?season=2026-27&recent_days=30` probe: HTTP 200 after
65 seconds, beyond the former premature 60-second timeout. The probe used a
private internal Docker network and delayed fake upstream, not production NBA
calls or writes. Helpers/network were removed. Active production Nginx confirms
600 seconds only for the exact NBA import path; other API timeouts unchanged.
Already fresh NBA data was not unnecessarily imported again.

New actual room `5f9b07d9-8790-4e2d-980a-08e531cfa546`, slot 5, was created
21:57:00 UTC, after the final NBA refresh/recompute. Acceptance captured 21
contiguous uniquely Yahoo-ID-mapped picks, 21 events, 14 identical rereads and
22 versioned snapshots. Every snapshot's manager roster input equals only its
manager picks; recommendations exclude drafted players.

| Manager turn/state | Roster | Recommendation | Utility | Run | Decision | Fresh ADP | Wait cost | Manager next |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Pick 5 before | Empty | Giannis Antetokounmpo |68.3996|0|68.3996|7.16|3.5230|5|
| Pick 5 after | Giannis | Tyrese Maxey |66.7047|0|66.7047|10.22|3.3294|20|
| Pick 20 before | Giannis | Kawhi Leonard |63.5666|4.5880|68.1546|29.56|0.8929|20|
| Pick 20 after | Giannis, Kawhi | Jaylen Brown |60.3777|5.4276|65.8053|41.35|5.2804|29|

All four wait actions are `draft_now`, confidence **low**. Yahoo selections were
owner-operated, never automated. Selected IDs leave availability and enter only
the manager roster. After Giannis, Maxey moves #2 -> #1 with roster score
change +0.3028: need +0.2191, scarcity-times-need +0.0838, construction 0.
After Kawhi, Brown's roster effect is -2.5049: need -0.1898,
scarcity-times-need -0.0537, construction -2.2615 (construction score 100 -> 0).
Need/construction/rank comparisons use the same available pool, mode and run
pressure; effects are not confounded by newly unavailable players.

Next five alternatives (adjusted scores):
- Before pick 5: Jalen 66.894, Maxey 66.402, Cade 65.841, Kawhi 63.680,
  Brown 62.883.
- After pick 5: Jalen 66.696, Cade 66.183, Kawhi 63.567, Brown 62.771,
  Embiid 61.146.
- Before pick 20: Brown 67.294, Avdija 62.780, Davis 61.440,
  Embiid 61.146, Murray 61.077.
- After pick 20: Davis 62.726, Embiid 61.500, Murray 61.392,
  Avdija 61.367, Harden 60.344.

Read-only recalculation of each before/after state is deterministic and matches
all persisted decision scores exactly. Every scored explanation's three deltas
sum to its actual roster-score change; normalized metric/fit terms are bounded.
Top-six candidate utility and final score were reconstructed from individual
base/durability/upside/risk/replacement/need/scarcity/construction/mode/run
terms. Each is included once in the documented formula. Missing/stale ADP has
no survival; draft rank/frequency remain null; candidate metric evidence exists.
The exact components, top recommendation plus next five alternatives, market
timestamps, confidence, roster and next-pick timing are saved in private
machine-readable acceptance evidence.

**Acceptance boundary:** recommendation-engine arithmetic and multi-turn roster
responsiveness pass. This is not proof that the advice is better than Yahoo's
projected rankings. The owner questioned Kawhi at 20: his 68.1546 model score
beat Brown 67.2942 by only 0.8604; historical production and a 4.588 run bonus
explain the result, not a current injury assessment or upcoming-season projection.
No weights were tuned in response to player reputation.

Data remains limited by 51 unscored players, 119 preseason metric samples,
unmatched ADP, older persisted Yahoo settings and uncalibrated survival.
Production automatic Yahoo draftresults was not verified by practice;
browser production input remains observe-only. Do not describe this acceptance
as validation of an unobserved production source.

Final release validation: **136 backend tests, 23 frontend tests**, strict
frontend production build, Python compilation, Compose, changed image builds,
Nginx config and whitespace checks passed. One existing Starlette/httpx
deprecation warning remains. Final post-mock full-row fingerprints of all
pre-existing sessions/picks/events/snapshots match the pre-release baseline.

GO decisions are scoped: engine **GO** for the unchanged documented model's
arithmetic and actual roster responsiveness; data **GO WITH LIMITATIONS**;
Yahoo mock tracking **GO** for observed contiguous/idempotent ingestion;
production Live **GO WITH FALLBACK** only as operator-reviewed manual/Quick
Record operation, not automatic Yahoo-source approval. Use **NO-GO** for
unattended/automatic production source claims until independently accepted.

## Final source refresh (supersedes intermediate coverage below)

The existing NBA HTTP import returned **504 at the frontend's 60-second proxy
limit**, but the importer continued and committed its atomic transaction.
Database verification, not the HTTP status, establishes the completed refresh:
all 1,159 season-stat rows have import timestamp
2026-10-18 21:22:30.372201 UTC (previously 1,054 rows imported October 9).
There are 582 regular-season and 577 preseason rows, and 738 NBA player records.
The existing conservative NBA-link workflow added one previously missing
mapping; existing Yahoo IDs/non-null NBA mappings were not replaced.

Approved metrics recomputation for Driveway Dudes and the current disposable
practice league completed at 21:24:37 UTC:

| Metric/input coverage | Before | Final |
|---|---:|---:|
| Yahoo identities |733|733|
| NBA mappings |690|691|
| Scored metrics |658|682|
| Missing NBA mapping |43|42|
| Mapped but missing eligible stats |32|9|
| Total unscored |75|51|
| Regular-season metric samples |563|563|
| Preseason metric samples |95|119|

All eight named candidates still use the same 2025-26 regular-season game counts
and fantasy values. Refreshed population distributions legitimately change
upside/scarcity/replacement slightly. No scoring weights or sample-selection
rules changed. Prior recommendation snapshots remain immutable.

Final Fantrax retrieval at **21:22:12.992064 UTC**: 396 records, 364 matched,
32 unresolved, zero ambiguous; 364 fresh usable rows, 2 retained stale rows.
Final equivalent early-draft top-20 coverage is 20/20; top-50 49/50, with
Amen Thompson still rejected for position mismatch. Source content has no
provider-updated timestamp. Retrieval time is not proof of source freshness.

### Fully refreshed equivalent early-draft top 10

Same original six unavailable IDs, empty manager roster, slot 10, 12 teams,
Balanced mode, current approved metric/market inputs. This is a read-only
calculation in the new practice namespace, not a rewritten historical snapshot.

| Player | F | D | U | R | V | N | SN | C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|Tyrese Maxey|48.82|85.3659|97.2279|10.2439|14.60|53.8462|76.4678|100|
|Jalen Johnson|48.11|87.8049|95.1476|8.5366|16.77|61.5385|56.5476|100|
|Kawhi Leonard|45.88|79.2683|96.9153|14.5122|14.54|76.9231|56.5476|100|
|Jaylen Brown|45.23|86.5854|98.9351|9.3902|13.89|76.9231|56.5476|100|
|Alperen Sengun|44.08|87.8049|93.0610|8.5366|13.75|69.2308|100|100|
|Joel Embiid|44.49|46.3415|96.6953|37.5610|14.16|53.8462|100|100|
|Donovan Mitchell|44.45|85.3659|97.6195|10.2439|10.64|61.5385|76.4678|100|
|Anthony Davis|44.22|24.3902|93.2398|52.9268|13.89|69.2308|100|100|
|Scottie Barnes|42.05|97.5610|87.2003|1.7073|11.72|76.9231|100|100|
|Deni Avdija|42.93|80.4878|95.5463|13.6585|11.59|76.9231|56.5476|100|

Mode adjustment is zero throughout. All listed ADPs are fresh matched Fantrax.

| Rank | Player | Roster utility | Run | Final decision | ADP | Survival | Wait cost | Wait action |
|---|---|---:|---:|---:|---:|---:|---:|---|
|1|Tyrese Maxey|66.4019|1.2205|67.6224|10.22|0.2040|1.3835|draft_now|
|2|Jalen Johnson|66.8938|0|66.8938|10.62|0.3252|1.8427|draft_now|
|3|Kawhi Leonard|63.6798|1.1470|64.8268|29.56|0.8913|-0.1058|wait|
|4|Jaylen Brown|62.8826|1.1308|64.0134|41.35|0.9834|-0.0339|wait|
|5|Alperen Sengun|61.5347|1.1020|62.6367|19.07|0.5722|-1.5037|wait|
|6|Joel Embiid|59.7342|1.1123|60.8465|57.60|0.9989|-0.0059|wait|
|7|Donovan Mitchell|59.6129|1.1113|60.7242|14.74|0.3781|-3.3664|wait|
|8|Anthony Davis|59.3987|1.1055|60.5042|28.44|0.8715|-0.7234|wait|
|9|Scottie Barnes|58.7131|1.0513|59.7644|12.30|0.2773|-4.5628|wait|
|10|Deni Avdija|58.5929|1.0733|59.6661|40.04|0.9794|-0.1323|wait|

Primary recommendation: Maxey, **low** heuristic confidence. Highest modeled
wait-loss candidate: Jalen. Survival/wait estimates remain unvalidated.

Final code validation: 136 backend tests, 23 frontend tests, strict production
build, Python compilation, Compose, whitespace, changed images and Nginx config
test pass. The original manager-roster correction/UI split is deployed. The
subsequent owner-selected rank explanations and an exact-route NBA import
600-second proxy timeout are implemented/tested/built but **not deployed**:
no approval was inferred from the renewed audit prompt. Other API proxy
timeouts remain unchanged.

The real mock smoke described below occurred after the first Fantrax refresh and
deployed roster fix, **before this final NBA refresh**. Tracking stopped at
21:15:53 with practice version 62. No post-21:24:37 actual manager-turn evidence
is available; the final refreshed state has equivalent-state verification only.
The intended Live session remains active version 1, and full-row hashes of all
pre-existing draft sessions/picks/events/snapshots still match.

The remainder preserves the original snapshot audit and intermediate refresh
results rather than silently replacing historical evidence with fresh inputs.

## Evidence and exact cause

The owner's 69.3 Jalen Johnson recommendation is reproduced exactly by practice
session `86fb9b29-41e7-48b2-b876-6841314fa199`, version/recommendation version 6,
2026-10-18 20:29:52 UTC: next overall pick 7, manager slot 10, empty manager
roster, 727 available players. Six opponent selections had already occurred.
Historical snapshots were preserved, not overwritten.

**Confirmed defect:** the session passed all six league-wide drafted IDs to
utility, which used that list as the manager's roster. The roster panel correctly
showed an empty manager roster, but recommendations fitted candidates around
opponents' two centers, three guards and a PF/C. This created seven open slots
instead of thirteen, inflated Jalen's need to 100, and assigned some alternatives
zero incremental construction fit. It explains the difference from the corrected
calculation without changing any scoring weights.

**Separate missing-evidence cause:** all 312 stored Fantrax rows were older than
48 hours. Their ADP was intentionally withheld from survival/wait calculations.
The displayed utility score did not require ADP; unavailable wait confidence did
not mean that fantasy value or roster utility was absent.

## Original score reconstruction

With value `V`, replacement `R`, and durability/upside/risk/need/scarcity/
construction expressed as fractions:

```
utility = V * (1 + .05*durability + .05*upside - .05*risk)
          + .5*R
          + max(abs(V),1) * (.10*need + .05*scarcity*need + .05*construction)
decision = utility + mode_adjustment + run_bonus
```

Balanced mode adjustment is zero for every candidate. ADP is not an additive
decision-score term. Run pressure enters this utility ranking once; its separate
effect on heuristic survival is not another utility-score addition.

| Original additive term | Jalen | Maxey | Kawhi | Brown | Sengun | Barnes | Tatum | Mitchell |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Base fantasy value |48.1100|48.8200|45.8800|45.2300|44.0800|42.0500|44.1500|44.4500|
| Durability contribution |2.1121|2.0838|1.8184|1.9581|1.9352|2.0512|0.4307|1.8973|
| Upside contribution |2.2819|2.3635|2.2161|2.2365|2.0409|1.8336|2.0924|2.1610|
| Risk contribution |-0.2053|-0.2501|-0.3329|-0.2124|-0.1881|-0.0359|-1.2437|-0.2277|
| Half replacement |8.3850|7.4050|7.2700|6.9450|6.8750|5.8600|6.4050|5.2200|
| Position need |4.8110|3.4871|4.5880|4.5230|3.7783|4.2050|4.4150|3.1750|
| Scarcity x need |1.3827|1.3721|1.3186|1.3000|1.8891|2.1025|1.2689|1.2493|
| Construction |2.4055|0|0|0|0|2.1025|2.2075|0|
| Mode |0|0|0|0|0|0|0|0|
| Run |0|1.2205|1.1470|1.1308|1.1020|1.0513|0|1.1112|
| Final decision |69.2830|66.5020|63.9052|63.1110|61.5124|61.2202|59.7258|59.0361|
| Jalen advantage |--|2.7810|5.3778|6.1720|7.7706|8.0628|9.5572|10.2468|

Thus Maxey's higher base value was outweighed particularly by Jalen's incorrect
need/construction advantage and greater replacement value. The other differences
are fully accounted for above, including Tatum's 16-game sample producing low
durability/high risk. These are model inputs, not a new injury prognosis.

## Candidate identity, sample and metric audit

All eight have an existing Yahoo/internal/NBA mapping and metric row. All use
**2025-26 Regular Season**, not preseason. Stats were imported
2026-10-09 11:05:42 UTC; metrics computed 2026-10-10 17:06:24 UTC.

| Player | Yahoo ID | Internal ID | NBA ID | GP | Replacement | Scarcity | Durability | Risk | Upside |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| Jalen Johnson |6562|10260|1630552|72|16.77|57.48|87.80|8.54|94.86|
| Tyrese Maxey |6413|10227|1630178|70|14.81|78.70|85.37|10.24|96.82|
| Kawhi Leonard |4896|10033|202695|65|14.54|57.48|79.27|14.51|96.60|
| Jaylen Brown |5602|10092|1627759|71|13.89|57.48|86.59|9.39|98.90|
| Alperen Sengun |6558|10257|1630578|72|13.75|100.00|87.80|8.54|92.60|
| Scottie Barnes |6515|10248|1630567|80|11.72|100.00|97.56|1.71|87.21|
| Jayson Tatum |5765|10113|1628369|16|12.81|57.48|19.51|56.34|94.79|
| Donovan Mitchell |5826|10120|1628378|70|10.44|78.70|85.37|10.24|97.23|

| Player | Old need | Correct need | Old construction | Correct construction | Old utility before run | Correct utility before run | Correct decision |
|---|---:|---:|---:|---:|---:|---:|---:|
| Jalen Johnson |100.00|61.54|100|100|69.2830|66.9008|66.9008|
| Tyrese Maxey |71.43|53.85|0|100|65.2815|66.5263|67.7468|
| Kawhi Leonard |100.00|76.92|0|100|62.7582|63.6891|64.8361|
| Jaylen Brown |100.00|76.92|0|100|61.9803|62.8980|64.0287|
| Alperen Sengun |85.71|69.23|0|100|60.4104|61.5245|62.6265|
| Scottie Barnes |100.00|76.92|100|100|60.1689|58.7134|59.7646|
| Jayson Tatum |100.00|61.54|100|100|59.7258|57.5397|57.5397|
| Donovan Mitchell |71.43|61.54|0|100|57.9249|59.5348|60.6460|

No weights were adjusted to force this ordering. Actual metric bounds across all
658 scored identities: durability 1.2195..100, risk 0..99.1463, upside
0.0533..99.7869, scarcity 50.2693..100. No out-of-range normalization was found.
Replacement is deliberately an additional value-over-replacement term; scarcity
uses supply/demand separately. This audit does not establish calibration or
optimality of those heuristic weights.

### Owner-observed strategic limitation

The main recommendation is, by design, the highest **current** adjusted roster
utility on the decision-sorted internal board. Market ADP informs the separate
wait analysis; it does not directly select a different primary player. There is
no multi-pick roster-building planner. Successful ingestion is not evidence that
this limited strategy is draft-ready.

At actual new-mock version 34 (pick 35), a read-only same-pool comparison proved
the board is not literally static:

| Candidate | Empty-roster score | Actual Maxey/Towns roster score |
|---|---:|---:|
| Jaylen Brown |67.4210|67.7060|
| Anthony Davis |63.8134|61.8338|
| Joel Embiid |63.0660|63.7194|
| Deni Avdija |62.8913|63.1619|

Brown's need changed from 76.9231 to 81.8182; he stayed first. Davis dropped
from second to fourth because the actual roster already held Towns. These are
real roster effects, but modest fit adjustments can still leave the same
high-base-value player on top for many picks. The owner's concern about deeper
roster-aware strategy remains open; no subjective reweighting or unapproved
lookahead model was added to hide it.

The owner explicitly chose to keep **best current roster value**, not add a
two-pick planner. Implemented a presentation/evidence follow-up:
`Why this rank?` on the recommendation and every scored board candidate shows
empty-roster rank -> actual-roster rank, score delta, need change, construction
change, and the exact need/scarcity/construction contributions to that delta.
The comparison holds the available pool, player metrics, mode and run pressure
fixed; ranks are among the same scored available candidates with the existing
tie-breaks. The three delta terms sum to the actual score difference. Unscored
players and older snapshots without this evidence explicitly remain unavailable.
No weight, primary objective, market/wait logic or source behavior changed.
Focused follow-up validation: 5 backend tests and 14 presentation tests passed;
strict frontend build passed. This follow-up is not deployed yet.

## Persisted Yahoo scoring and sample coverage

Raw Yahoo stat modifiers, normalized current persisted settings, and all 658
metric scoring-category inputs agree, with six unique weighted categories:
PTS/12 = 1, REB/15 = 1.2, AST/16 = 1.5, BLK/18 = 3,
STL/17 = 3, TOV/19 = -1. All eight fantasy values reproduce from their selected
persisted base stats using those weights. No missing/ignored weighted category,
duplicate modifier, stat-ID or sign defect was found.

Roster: PG, SG, G, SF, PF, F, C x2, Util x2, BN x3; IL x3 is excluded from
draftable slots. The manager roster panel and utility now both use only manager
picks. Replacement-demand calculation uses starting slots; roster fit includes
bench and excludes IL.

Settings were imported 2026-10-09 09:16:26 UTC. This proves consistency with the
**persisted** Yahoo configuration, not a fresh remote settings check. Practice
copies Driveway Dudes settings; it is not proof that the Yahoo mock uses identical
scoring.

Coverage: 733 Yahoo identities; 690 NBA mappings; 658 metrics; 43 missing mappings;
32 mapped without eligible production (75 total unscored). Of the 658 metrics,
563 use 2025-26 regular season and 95 use 2026-27 preseason. No metric uses
2026-27 regular season or game-log fallback here. The existing rule prefers the
latest regular season with >=10 games, then other regular production, then
target-season preseason, then target-season logs. A tiny preseason sample does
not displace mature regular production. No sample-selection rule or metric input
was changed, so no unnecessary metric recomputation was performed.

## Fantrax refresh and exact candidate market state

Existing documented NBA `getAdp` and `getPlayerIds` APIs were used, not HTML.
Successful retrieval: **2026-10-18 20:42:09.426447 UTC**. The provider supplies no
source-updated timestamp, so retrieval freshness is not source-content freshness.

| Measure | Before | After |
|---|---:|---:|
| Provider records |334|396|
| Unique matched identities |312|364|
| Unresolved records |22|32|
| Ambiguous matches |0|0|
| Stored ADP rows |312|366|
| Fresh usable rows |0|364|
| Stale retained rows |312|2|
| Stored coverage / 733 |42.56%|49.93%|
| Fresh usable coverage / 733 |0%|49.66%|
| Usable ADP in decision top 20 |0/20|20/20|
| Usable ADP in decision top 50 |0/50|49/50|

The two stale rows remain provenance, not usable ADP. The top-50 exception is
**Amen Thompson, corrected decision rank 26**, rejected for source/Yahoo position
conflict. All other corrected top-50 players have fresh matched Fantrax ADP.

All eight original candidate rows were retrieved 2026-10-10 01:25:48.739364 UTC,
about 8 days 19 hours before the snapshot; usable ADP, survival, miss risk and
wait cost were null, action `insufficient_evidence`, confidence `unavailable`.
Stored old ADP is listed only as stale provenance below. New rows share the
successful retrieval above and were evaluated immediately, with age seconds.

| Player | Old stored ADP (stale) | Fresh ADP | Heuristic survival | Miss-risk /100 | Expected wait cost | Action |
|---|---:|---:|---:|---:|---:|---|
| Jalen Johnson |10.40|10.62|0.3252|67.5|1.8256|draft_now|
| Tyrese Maxey |9.39|10.21|0.2037|79.6|1.4760|draft_now|
| Kawhi Leonard |29.00|29.55|0.8911|10.9|-0.1078|wait|
| Jaylen Brown |43.03|41.37|0.9835|1.7|-0.0339|wait|
| Alperen Sengun |20.26|19.08|0.5727|42.7|-1.5168|wait|
| Scottie Barnes |12.11|12.30|0.2773|72.3|-4.5801|wait|
| Jayson Tatum |7.81|7.61|0.2259|77.4|-5.8142|wait|
| Donovan Mitchell |14.60|14.73|0.3777|62.2|-3.4323|wait|

These wait actions consider available fallback utility, not survival alone.
They are unvalidated heuristics, not guarantees. Maxey is the corrected
highest-utility recommendation; Jalen is the highest positive wait-loss candidate.
Fresh market inputs do not directly change the utility ranking.

Unresolved records: 2 name misses (Nicolas Claxton, Ron Holland), 15 position
conflicts, 15 missing source teams. Current strict name/team/position checks were
retained. No mapping was forced, no identity overwritten, and no newly defensible
alias/position relaxation was established. No new provider was added.

## Equivalent-state top 20 after correction

All rows have fresh Fantrax ADP. Balanced roster utility is decision minus the
separately applied run bonus, as detailed above for the eight audited candidates.

| Rank | Player | Base value | Roster utility | Adjusted / decision | ADP | Expected wait cost |
|---|---|---:|---:|---:|---:|---:|
|1|Tyrese Maxey|48.82|66.5263|67.7468|10.21|1.4760|
|2|Jalen Johnson|48.11|66.9008|66.9008|10.62|1.8256|
|3|Kawhi Leonard|45.88|63.6891|64.8361|29.55|-0.1078|
|4|Jaylen Brown|45.23|62.8980|64.0287|41.37|-0.0339|
|5|Alperen Sengun|44.08|61.5245|62.6265|19.08|-1.5168|
|6|Joel Embiid|44.49|59.7293|60.8415|57.58|-0.0060|
|7|Donovan Mitchell|44.45|59.5348|60.6460|14.73|-3.4323|
|8|Anthony Davis|44.22|59.3909|60.4964|28.42|-0.7296|
|9|Scottie Barnes|42.05|58.7133|59.7646|12.30|-4.5801|
|10|Deni Avdija|42.93|58.5983|59.6716|40.05|-0.1325|
|11|Anthony Edwards|44.05|58.4396|59.5409|8.46|-5.5986|
|12|Kevin Durant|41.70|56.9840|58.0265|16.47|-4.3918|
|13|Jamal Murray|42.93|56.6429|57.7162|20.11|-3.2222|
|14|Jayson Tatum|44.15|57.5397|57.5397|7.61|-5.8142|
|15|Bam Adebayo|41.00|56.1596|57.1846|32.45|-0.6198|
|16|James Harden|42.36|55.9054|56.9644|31.01|-0.7972|
|17|Karl-Anthony Towns|40.58|55.4973|56.5118|16.48|-5.1969|
|18|Pascal Siakam|39.92|53.9314|54.9294|52.67|-0.0283|
|19|LeBron James|41.42|54.8657|54.8657|55.06|-0.0128|
|20|Josh Giddey|41.51|53.5694|54.6071|26.06|-2.0797|

Only rank 1 is the primary recommendation. Positive wait cost yields `draft_now`
for ranks 1 and 2; the other rows have `wait` in this equivalent state.

The private sanitized machine-readable audit contains exact top-50 values,
original top-20 ranking, original missing-metric IDs, selected stat fields and
all eight full component records; raw league source/auth information is excluded.

## Unavailable-field classification

| Field | Class | Outcome |
|---|---|---|
| ADP | A where stale; C without a defensible match | Refreshed real source; gaps stay null |
| Market delta | A / missing ADP dependency | Available with fresh ADP and timing |
| Survival / miss risk | A / missing ADP dependency | Enabled where sufficient inputs; explicitly unvalidated |
| Expected wait cost / best value at risk | A / fallback coverage dependency | Enabled for this early state; missing required fallbacks still block |
| Roster need / construction | B | Corrected manager-only roster pipeline |
| Draft rank / XRank | C | Fantrax does not supply it |
| Draft frequency | C | Fantrax does not supply it |
| Opponent demand | D | Not implemented; no guessing added |
| Recommendation confidence | A / C / D | Missing inputs => unavailable; populated inputs remain heuristic, not calibrated |

Saved recommendations are immutable per session version. Refresh does not rewrite
old snapshots: subsequent legitimate session events generate new recommendations.
The new manager-roster correction likewise applies at generation, not by silently
changing historical replay. UI distinguishes BEST PICK NOW from WAIT ANALYSIS
UNAVAILABLE, and missing ADP from stale ADP with the retrieval timestamp.

## Validation and release boundary

Focused readiness/session tests passed (4); actual-player regression passed (1);
focused presentation tests passed (14). Final validation ran once: **136 backend
tests**, **22 frontend tests**, strict TypeScript/Vite build, Python compilation,
Compose configuration, whitespace check, and both changed image builds passed.
One existing Starlette/httpx deprecation warning remains. Actual sample tests cover determinism,
drafted-player exclusion, unchanged utility ranking for stale/missing ADP, absent
survival/confidence for missing inputs, fresh wait evidence, bounds, and exactly
one utility run bonus. Existing session tests cover version-consistent snapshots.

Read-only equivalent-state evaluation reproduced every original decision score
and all eight fantasy values, then exercised the corrected manager roster.
After explicit approval, controlled API/frontend release followed a new private
93,646,545-byte PostgreSQL archive backup (0600; archive directory verified).
Migration remains 0006. Trusted HTTPS API health, frontend bundle and the
retrieval-timestamp API contract were verified. No database/Caddy recreation.

**New actual Yahoo smoke passed**, session
`1dea68b6-d413-4960-bc87-eb85e46de48a`, manager slot 11:

| State | Manager roster | Recommended | Roster utility | Run bonus | Decision | ADP | Wait cost |
|---|---|---|---:|---:|---:|---:|---:|
| Before pick 11 / v10 | Empty | Tyrese Maxey |66.5263|3.6615|70.1878|10.21|2.3888|
| After own pick 11 / v11 | Maxey | Kawhi Leonard |64.0677|4.5880|68.6557|29.55|2.2471|
| Before pick 14 / v13 | Maxey | Kawhi Leonard |64.0677|4.5880|68.6557|29.55|2.0458|
| After own pick 14 / v14 | Maxey, Towns | Kawhi Leonard |63.9782|5.5056|69.4838|29.55|3.2771|

All four states have fresh matched ADP, `draft_now` heuristic wait action, and
**low** confidence. No claims of calibrated confidence. Exact full best-pick
components, top-five alternatives and timestamps were captured per version.
Manager need for Kawhi was 83.3333 after Maxey and 81.8182 after Towns; construction
100. The changing run bonus is separate from unchanged per-roster utility.

Observed picks 1..15 were contiguous, uniquely Yahoo-ID mapped and stable across
six identical rereads: 15 picks, 15 events, no reread duplicates. Every snapshot
stored exactly the manager's own IDs in its roster input, excluded drafted
recommendations, and matched its session version. The user's selections were
Maxey at 11 and Towns at 14; no Yahoo selections were automated. A subsequent
served board at version 22 had 711 available players, matching recommendation
version 22, the same two-player roster, next overall 23 / manager next 35 /
YOUR TURN false. Actual DOM clock timing was not independently inspected.

Apart from the new disposable practice room's legitimate observer ingestion,
only global market tables were refreshed. Intended real session
`650df382-29ba-4b32-8ed2-2f87955be453` remains version 1 with its existing
pick/event/snapshots; no settings, identities, picks or historical recommendations
were rewritten. Full-row fingerprints of **every pre-existing session, pick,
event and recommendation snapshot** match both immediately after release and
after this new real mock. Yahoo parsing, observer architecture, reconciler, production
draftresults polling and source permissions are unchanged.

Code is deployed and the focused real-mock smoke above passed. This does not
establish projection accuracy, historical outperformance, production
draftresults acceptance, long-draft endurance, or draft-night readiness for
unscored players and unsupported source fields.

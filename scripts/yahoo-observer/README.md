# Court IQ Yahoo Observer

## Results-table reader compatibility

The reader also recognizes a selected Yahoo **Results** tab with exactly one
visible table whose columns are **Pick / Player / Team**. It sorts the actual
pick numbers ascending and retains the existing unique-ID, complete-history,
mapping and conflict checks. Team roster tables (**Slot / Player / Pick**) and
available-player tables are not pick history. This compatibility does not enable
Production Live browser writes: MOCK mode remains a separate disposable mirror.
Keep the league-wide Results view selected when using this layout.
Windows installations must receive the updated `picks.py`; server updates alone
do not change the installed reader.

Run the focused reader regressions with
`node --test scripts/yahoo-observer/results-reader.test.mjs`.

## Status and evidence

The Windows observer, pairing, URL-driven connection, and disposable Yahoo Mock
Practice integration are deployed and accepted for the tested practice path.
Migration 0006 is applied. The latest actual mock smoke observed 23 real Yahoo
picks and 24 recommendation snapshots; the owner selected Luka at pick 7 and
Kawhi at pick 18. Only manager selections entered the manager roster; opponent
picks affected availability. Butler remained excluded and recommendation
recalculation followed manager selections. Duplicate rereads did not create
extra picks/events. No Yahoo selection was automated.

The owner confirmed no console/flash during Windows startup, tracking, and
reconnect. The original offending PID/command line was not captured, so its
historical cause is unknown. Earlier supplied Windows samples independently
showed picks 1..4, four unique Yahoo-ID mappings, incremental detection and
duplicate suppression; measured local DOM detection delays were 92, 135, and
970 ms, not Yahoo/provider/network latency. Picks 30..41 also mapped 12/12 by
Yahoo ID read-only.

## One-time Windows setup

1. Open Court IQ on the Windows PC running Chrome, over trusted HTTPS.
2. Download **Install Court IQ Yahoo Observer**, extract the ZIP, and open
   `Install-CourtIQObserver.cmd`. Python 3 and Chrome must already be installed.
   The installer checks Python, installs the existing observer dependency in a
   dedicated environment and creates Start-menu/startup shortcuts.
3. In the setup window, configure the Court IQ HTTPS address, dedicated
   observer credential, and trusted public CA certificate if needed.
   Obtain the credential privately from the deployment owner, never through
   chat. Never enter Yahoo credentials. TLS verification cannot be bypassed.
4. Choose **Verify and install connection**. Setup verifies Court IQ and
   loopback CDP, launching the dedicated Chrome profile if necessary.
5. Paste the short-lived, single-use pairing code into Court IQ once.

The dedicated observer credential is encrypted using current-user Windows DPAPI
in `%LOCALAPPDATA%\CourtIQ\Observer\connection.json`. Reinstallation preserves
that configuration. The Court IQ browser receives an HttpOnly, Secure,
SameSite-strict pairing cookie, not the dedicated credential. Credential rotation
invalidates pairing; changing browsers or clearing cookies requires pairing
again, not reinstalling the observer.

Port 9222 must bind **only** Windows `127.0.0.1`. There is no local HTTP pairing
server, CDP forwarding, LAN listener or firewall rule. The desktop agent makes
outbound trusted HTTPS requests; Chrome debugging remains on Windows loopback.
The dedicated Chrome profile may retain the user's own Yahoo browser login,
but the observer never reads or exports passwords, cookies or auth parameters.

Background PowerShell listener verification and Chrome-launch helpers use Windows
`CREATE_NO_WINDOW`, `STARTF_USESHOWWINDOW`/`SW_HIDE`, and `-WindowStyle Hidden`.
Normal shortcuts/startup run `pythonw.exe`; accidental `python.exe desktop.py`
invocation relaunches with `pythonw.exe` without starting a console child.
The loopback checks, error handling and check cadence are unchanged. Already
installed Windows copies need the updated files and an observer restart;
changing server files alone does not update a running desktop installation.
Re-run the downloaded installer once: it replaces only the exact installed
`pythonw.exe` agent whose command line names the installed `desktop.py`, preserves
DPAPI configuration/pairing and existing Chrome, and starts the new background
agent without reopening setup. Close any legacy developer PowerShell window once;
the normal shortcut never needs it again. **Court IQ Observer Diagnostics** is an
explicit foreground exception, not the normal draft launch.

Sanitized event/type-only logs go to
`%LOCALAPPDATA%\CourtIQ\Observer\observer.log` (256 KiB plus two rotated copies).
No exception messages, Yahoo URLs, credentials, CDP payloads or tracebacks are logged.

Normal startup, tracking, and reconnect have been visually accepted without a
console or flash. The explicit Diagnostics shortcut and dedicated
troubleshooting commands may open a console; they are not normal operation.

## Every Yahoo mock afterward

1. Open **Court IQ Yahoo Chrome** from the Start menu and join the mock yourself.
2. Copy the Yahoo draft URL.
3. Paste the URL into Court IQ and choose **Connect**. The disposable Draft Room
   opens from that connection.
4. If authoritative slot evidence is missing, answer only the single slot
   question. Do not guess or map opponents.

No per-draft PowerShell/Python command, session UUID, selectors, opponent order,
or repeated observer-secret entry is required. The observer never makes Yahoo
selections.

Pasted query/auth/fragment values are discarded immediately in the UI. Only
the validated `/draftclient/nba/<room>/<team>` path is used for the connection.
The URL's team component is never interpreted as the user's draft slot.
The agent selects only the exact matching Yahoo Basketball draftclient target,
ignoring lobby, unrelated rooms, extensions and internal documents.

Missing or ambiguous team/round/slot evidence produces **NEEDS ATTENTION**;
nothing is guessed. The tested flow supports the configured 12-team practice
format; its 13-round setting is owner-confirmed configuration, not a universal
default or Yahoo-discovered metadata. Rendered rounds take precedence; conflicts
still halt, and Live mode never uses the practice-round setting. If all other
required metadata is present and only the user slot is missing, Court IQ asks
for that one slot number. Do not infer universal metadata discovery or automatic
production session routing from the accepted mock smoke. Other missing or
ambiguous team/round evidence continues to fail closed.

## Practice synchronization

An explicitly enabled **Yahoo Mock Practice** creates a new disposable namespace,
with Mock Slot 1..12 and Box Score Bully only at the verified/user-confirmed slot.
No imported opponent identities, real rosters or player identities are copied
or invented. Existing pool references/settings/metrics seed the practice board.
Internal opponent simulation, rehearsal controls, reset and manual pick mutation
are blocked in this room; make your own selections only in Yahoo.

Only numbered entries with exactly one authoritative numeric
`.ys-player[data-id]` are accepted from the verified bounded Picks subtree.
Team, queue and tab IDs are excluded. Complete contiguous history from pick 1
is required for persisted practice. No names or missing earlier picks are
fabricated. Each observation contains only:

```json
{
  "overall_pick": 1,
  "yahoo_player_id": "5352",
  "observed_at": "2026-10-18T12:00:00Z",
  "source": "yahoo_mock_browser"
}
```

The desktop snapshot envelope adds only bounded source status, rendered
team/round/slot metadata and optional local latency. It contains no Yahoo URL,
auth, cookies, browser credentials or debugger address.

The dedicated-secret-protected endpoint resolves existing `yahoo_player_id`
identities, normalizes picks and calls the **existing** sequential reconciler.
There are no direct DraftPick writes or second reconciler. Existing audit events,
versions, locks and recommendation snapshots remain authoritative.
Identical rereads are no-ops, contiguous additions catch up, changed history
latches **CONFLICT**, and unknown IDs/gaps/malformed observations stop writes.

The bounded MutationObserver marks history dirty; parsing uses the existing
250-ms dirty check and 10-second recovery reread, not whole-document scraping.
Local detection samples are bounded and recorded separately from transport.

## Reconnect and the next mock

**STOP TRACKING** disconnects the selected room without deleting its draft or
revoking pairing. The desktop agent becomes idle on its next job poll; updated
desktop copies also release the local CDP connection. A new URL resumes normal
use without pairing again. The Stop/Delete API/frontend release is deployed;
served frontend controls and OpenAPI route were verified over trusted HTTPS.
Stop no longer waits on the snapshot initialization/catch-up serialization lock.
It deactivates the mailbox immediately; an already-running reconciliation may
finish, but subsequent snapshots are rejected and no new job is offered.
Recent Drafts also provides **Delete Mock** with explicit confirmation, using the
existing mock-only deletion endpoint. Stop an actively tracked Yahoo mock first.
Real sessions and batch-managed runs are not deletable through this control.
Deployment used a fresh private PostgreSQL archive backup and recreated only
API/frontend. Migration stayed at 0006; before/after counts and full-row
session/pick/event/recommendation fingerprints were identical. No mocks were deleted during deployment. The owner
subsequently confirmed no console/flash during startup, tracking, and reconnect.

Ordinary target/page recreation triggers automatic exact-room reacquisition,
safe read-only Picks reopening if necessary, and full-history reconstruction.
Reusing the same sanitized room reuses its disposable session. A generation
counter lets a new Start request resume a stopped local connection without
clearing authoritative conflicts.

When the configured draft finishes, Court IQ shows **DRAFT ENDED** and
**CONNECT NEW YAHOO MOCK**. A new room URL selects a new isolated practice session;
the installation, profile and securely stored credential remain reusable.
The final acceptance evidence does not claim a full-draft endurance test, Yahoo
end-state test, or production `draftresults` verification. Never refresh near
the user's turn or automate a pick.

## Production boundaries

- **Browser Observer:** Windows read-only DOM acquisition, not official Yahoo API.
- **Yahoo Mock Practice:** explicit opt-in browser observations into a disposable
  session through existing reconciliation.
- **Internal Mock Sync Rehearsal:** synthetic source snapshots, not Yahoo evidence.
- **Official Yahoo draftresults:** existing authenticated production polling;
  active-draft results are still unverified.
- **Production Live Draft:** official draftresults, existing Sync Now and
  Quick Record remain unchanged. The new Live browser choice is **OBSERVE ONLY**,
  cannot create a practice session, and cannot write intended live picks.

Mock success does not validate production draftresults. Live browser writes
require separate explicit review and approval.

## Deployment and advanced troubleshooting

The API needs a dedicated high-entropy `COURT_IQ_OBSERVER_SECRET`, imported
`COURT_IQ_OBSERVER_LEAGUE_KEY`, trusted `COURT_IQ_OBSERVER_ORIGIN`, and explicit
`COURT_IQ_OBSERVER_PRACTICE_WRITES=true` for practice writes.
The existing practice authorization label
`COURT_IQ_OBSERVER_PRACTICE_SESSION` must remain configured.
Keep these values outside source control. Installer downloads never contain
the credential or local configuration.

Migration `0006_observer_connections` adds only the connection mailbox. It was
applied through the repository migration mechanism after a fresh private backup;
migration 0005 and
production session/source schemas are unchanged. The controller currently assumes
the deployed single API worker; do not deploy multiple workers without shared
initialization coordination.

The older `Inspect-YahooPicks.ps1`, `Start-YahooMockPractice.ps1` and
`observer.py` CLI remain developer diagnostics only. They are not normal setup
or per-draft steps. Never put the secret in a command-line argument or diagnostic
output. Do not refresh/restart Yahoo simply to troubleshoot.

Run focused observer/connection/practice/migration tests during implementation.
Run the full backend/frontend/build/compile/Compose/image/diff validation once,
only after actual Yahoo Mock Practice acceptance.

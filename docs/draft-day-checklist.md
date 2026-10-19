# Draft-Day Checklist

Use the intended live session only after completing the checks below. Never use a rehearsal session for draft-night picks.

## Yahoo Mock Practice - operator flow

The Windows observer's one-time install and pairing, background startup, and
no-console behavior have been accepted. CDP must remain bound to Windows
`127.0.0.1`; never expose it on the LAN. See the
[Windows observer runbook](../scripts/yahoo-observer/README.md) for installation,
pairing, and troubleshooting.

For each Yahoo practice mock:

- [ ] Join the Yahoo mock yourself in the dedicated Chrome profile.
- [ ] Copy the Yahoo draft URL, paste it into Court IQ, and choose **Connect**.
- [ ] If Court IQ asks for the user's slot because Yahoo did not expose an
  authoritative marker, enter only that one slot number. Never guess.
- [ ] Confirm the disposable Yahoo Mock Practice room is connected and observed
  picks flow into Recent Picks, availability, the manager roster, timing, and
  recommendations.
- [ ] Make every Yahoo selection yourself. The observer is read-only and never
  clicks or submits a Yahoo pick.
- [ ] On YOUR TURN, verify that only the manager's selections appear in the
  manager roster; opponent picks affect availability only.
- [ ] If evidence is missing or conflicting, stop and resolve it in Court IQ.
  Do not fill in opponent mappings or bypass the fail-closed behavior.

No per-draft PowerShell/Python commands, session UUID handoff, full opponent
mapping, or observer-secret entry are part of normal use. Internal Mock Live
Draft and Mock Sync Rehearsal are separate synthetic workflows.

## Recommendation and status checks

- [ ] Treat BEST PICK NOW as the highest current adjusted roster value under the
  existing heuristic. Read WAIT ANALYSIS separately; ADP does not directly
  determine BEST PICK NOW.
- [ ] Check Yahoo status and its timestamp. O/Out and NA/Not Active are excluded
  from normal recommendations and wait/fallback candidates; Q/P remain eligible
  with uncertainty. Blank means “No Yahoo status reported,” not healthy.
- [ ] Remember Yahoo status is refreshed by player-pool import, not continuous
  injury monitoring. Do not infer recovery timing or severity.
- [ ] Current data limitations: 744 Yahoo identities; 682 scored metrics and 62
  unscored; 119 preseason samples; 364 fresh Fantrax ADP rows plus 2 stale.
  Fantrax rank, XRank, frequency, sample size, and source-updated time are not
  provided. Survival/wait estimates are uncalibrated.

## Production Live Draft

- [ ] Use only the intended Production Live session. Yahoo Mock Practice does
  not verify official Yahoo `draftresults` or production synchronization.
- [ ] Keep the existing official Yahoo `draftresults` path and use **Sync Now**
  only when appropriate. Verify source/local picks and manager turn before
  recording.
- [ ] Keep **Quick Record/manual entry** ready. If a source error or conflict
  occurs, pause automatic updates, compare the evidence, and do not overwrite a
  conflict with a guess.
- [ ] Preserve correction/undo and conflict protection. Browser-based
  production Live writes are not verified or enabled.

## Before startup

- [ ] Confirm the Court IQ HTTPS origin is trusted by the browser/observer:

  ```bash
  ./scripts/export-caddy-root.sh
  ```

  Only install the verified public root if that client does not already trust it;
  confirm its fingerprint through a trusted channel. The script validates the
  served chain and host SAN and exports only `root.crt`, never private keys.
  Never bypass TLS verification or proceed through a certificate warning.
- [ ] Set `LIVE_DRAFT_POLL_INTERVAL_MS` in `.env` if needed. The conservative application default is 60000 ms; it is not a Yahoo-approved interval. Rebuild the frontend after changing it.
- [ ] Back up PostgreSQL to a new, private path before startup or migration; do not overwrite an earlier backup:

  ```bash
  umask 077
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$HOME/fantasy-gm-pre-draft-YYYYMMDD-HHMMSS.sql"
  test -s "$HOME/fantasy-gm-pre-draft-YYYYMMDD-HHMMSS.sql"
  chmod 600 "$HOME/fantasy-gm-pre-draft-YYYYMMDD-HHMMSS.sql"
  ```

## Start and verify

- [ ] Start the real Compose application and confirm every service is healthy:

  ```bash
  docker compose up --build -d
  docker compose ps
  ```

- [ ] Check the API health endpoint and Draft Room frontend through the configured Caddy URL:

  ```bash
  curl --fail --silent --show-error "$DRAFT_ROOM_URL/api/v1/health"
  curl --fail --silent --show-error "$DRAFT_ROOM_URL/"
  ```

- [ ] Verify migration `0006_observer_connections` is current. Do not run a
  production migration without a fresh private backup and change approval.

- [ ] In the Draft Room, confirm Yahoo authorization is connected without displaying or copying credentials/tokens. Refresh and verify the intended league, season, teams, roster/scoring settings, and available Yahoo player pool.
- [ ] Refresh NBA data and draft metrics for the active season:

  ```bash
  curl --fail --silent --show-error -X POST "$DRAFT_ROOM_URL/api/v1/nba/import?season=2026-27&recent_days=30"
  curl --fail --silent --show-error -X POST "$DRAFT_ROOM_URL/api/v1/draft/metrics?league_key=$LEAGUE_KEY&season=2026-27"
  ```

- [ ] Refresh Fantrax ADP and inspect its diagnostics:

  ```bash
  docker compose run --rm api python -m app.services.draft.market_sync --season 2026-27
  docker compose run --rm api python -m app.services.draft.market_diagnostics --season 2026-27
  ```

## Draft room readiness

- [ ] Create or resume only the correct **Live Draft** session. Verify the league, season, manager team, and round count. A manager position or full opponent mapping may remain unknown; do not enter guesses.
- [ ] Use **Sync Now** to load Yahoo draft results. Confirm first-round teams fill the progressive order table. Later rounds validate against known slots but do not fill unknown slots.
- [ ] When Yahoo identifies your first-round slot, deliberately set **My position** to the matching discovered slot. Until set, the app withholds manager turn timing and recommendations.
- [ ] Before recording draft-night picks, verify the sync header, source/status timestamps, current pick/team, manager's next pick, recommendations, and player availability.
- [ ] Keep Quick Record ready. Confirm the expected overall pick/team are correct; search, keyboard selection, and manual entry are available while recommendations remain visible.
- [ ] If a conflict or source error occurs, pause sync. Compare displayed source/local evidence. Use the advanced order editor only to enter a verified order; then explicitly resume sync and verify the next pick. Never overwrite a conflict with a guess.
- [ ] If a manual entry needs correction, verify the selection in Recent Picks and use correction or latest-pick undo; confirm the board, roster, timing, and recommendation refresh.
- [ ] Do not open, resume, reset, or modify any Mock Sync Rehearsal session during the real draft.

`DRAFT_ROOM_URL` should be the configured HTTPS Caddy origin. Do not paste OAuth credentials, tokens, authorization codes, or secrets into shell history or reports. A successful health check does not prove that Yahoo's active `draftresults` endpoint is returning draft picks.

For a reproducible mock run, choose a practice position and **Preview randomized order**. The displayed order seed is used for that preview and run; the optional simulation seed remains separately recorded. Regenerate the preview before creating the draft if you change the position or order seed.

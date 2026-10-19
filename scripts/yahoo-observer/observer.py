"""Windows-local, observe-only Yahoo draft DOM reader. No draft writes."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect refused")


HTTP = build_opener(ProxyHandler({}), NoRedirect())
INSPECTOR_VERSION = "picks-subtree-2"

OPEN_PICKS_EXPRESSION = """(() => {
if (location.protocol !== 'https:' || location.hostname !== 'basketball.fantasysports.yahoo.com'
    || !/^\\/draftclient\\/nba\\/\\d+\\/\\d+\\/?$/.test(location.pathname))
  return {error:'not_draft_document'};
const controls = [...document.querySelectorAll('button')]
  .filter(e => e.textContent.trim() === 'Picks'
    && e.getAttribute('role') === 'tab'
    && e.parentElement?.getAttribute('role') === 'tablist'
    && e.getAttribute('data-id') === 'picks' && !e.closest('.ys-team'));
if (controls.length !== 1 || controls[0].disabled)
  return {error:'unique_picks_tab_button_not_verified'};
controls[0].click();
return {opened_read_only_picks_tab:true};
})()"""


def structure_expression(history_selector=None):
    return """(() => {
if (location.protocol !== 'https:' || location.hostname !== 'basketball.fantasysports.yahoo.com'
    || !/^\\/draftclient\\/nba\\/\\d+\\/\\d+\\/?$/.test(location.pathname))
  return {error:'not_draft_document'};
const controls = [...document.querySelectorAll('button')]
  .filter(e => e.textContent.trim() === 'Picks');
const semanticClasses = e => [...e.classList].filter(c => /^ys-[a-z0-9_-]+$/i.test(c));
const shape = e => ({
  tag:e.tagName, role:e.getAttribute('role'), semantic_classes:semanticClasses(e),
  direct_child_count:e.children.length
});
if (controls.length !== 1) return {error:'picks_button_not_unique'};
const button = controls[0];
const control = {...shape(button), data_id:button.getAttribute('data-id') === 'picks' ? 'picks' : null};
const lineage = [];
for (let p=button.parentElement, depth=0; p && depth<4 && p!==document.body; p=p.parentElement,depth++)
  lineage.push({...shape(p), children:[...p.children].slice(0,16).map(shape)});
const configured = %s;
const controlledId = button.getAttribute('aria-controls');
let roots = configured ? [...document.querySelectorAll(configured)] :
  controlledId ? [document.getElementById(controlledId)].filter(Boolean) : [];
let containerEvidence = configured ? 'user_supplied_selector' : 'aria_controls';
if (!configured && !controlledId) {
  const tablist = button.parentElement;
  const wrapper = tablist && tablist.parentElement;
  const host = wrapper && wrapper.parentElement;
  if (tablist && tablist.getAttribute('role') === 'tablist'
      && wrapper.children.length === 1 && host && host.children.length === 2) {
    roots = [...host.children].filter(e => e !== wrapper && !e.contains(button));
    containerEvidence = 'observed_sibling_of_picks_tab_wrapper_requires_row_verification';
  }
}
if (roots.length !== 1) return {
  picks_control:control, control_lineage:lineage,
  error:'history_container_not_proven_supply_history_selector',
  team_slot_ids:[], drafted_player_ids:[], pick_history_rows:[]
};
const root = roots[0];
if (root === document.body || root === document.documentElement || root.contains(button)
    || root.closest('.ys-team,button,[role="tab"],[data-id="queue"]'))
  return {picks_control:control,error:'history_container_not_narrow_or_contains_controls'};
let budget=180;
const describe = (e, depth) => {
  if (--budget < 0) return {truncated:true};
  const blocked = e.closest('.ys-team,button,[role="tab"],[data-id="queue"],[data-id="picks"]');
  const result = shape(e);
  const id = e.getAttribute('data-id');
  if (id !== null) {
    result.data_id = /^(?:\\d{1,12}|queue|picks)$/.test(id) ? id : '[redacted]';
    result.id_kind = blocked ? 'team_or_ui_not_player' : 'unclassified_not_a_player_yet';
  }
  const slot = e.getAttribute('data-slot');
  if (slot && /^\\d{1,2}$/.test(slot)) result.data_slot = slot;
  if (!e.children.length) {
    const text = e.textContent.trim();
    result.text_pattern = /^\\d{1,3}\\.?$/.test(text) ? text :
      text.replace(/[A-Za-z\\u00c0-\\uffff]+/g,'WORD').replace(/\\d+/g,'NUMBER').slice(0,100);
    if (/https?:|auth|token|cookie|password|@/i.test(text)) result.text_pattern='[redacted]';
  }
  if (depth<8 && budget>0) result.children=[...e.children].slice(0,20).map(child=>describe(child,depth+1));
  else if (e.children.length) result.truncated=true;
  return result;
};
return {
  picks_control:control, history_container:shape(root), container_evidence:containerEvidence,
  structure:describe(root,0),
  drafted_player_ids:[], pick_history_rows:[],
  note:'Structure only: player and row selectors require verification; no candidates emitted'
};
})()""" % json.dumps(history_selector)


STRUCTURE_EXPRESSION = structure_expression()


def hidden_process_options():
    options = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    if hasattr(subprocess, "STARTUPINFO"):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    return options


def verify_windows_listener(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Invalid loopback port")
    command = (
        f"$a = @(Get-NetTCPConnection -State Listen -LocalPort {port} "
        "-ErrorAction Stop | Select-Object -ExpandProperty LocalAddress); "
        "ConvertTo-Json -InputObject $a -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", command],
        capture_output=True, text=True, timeout=10, check=False,
        **hidden_process_options(),
    )
    if result.returncode:
        raise ConnectionError("Windows listener verification unavailable")
    addresses = json.loads(result.stdout)
    if not isinstance(addresses, list) or not addresses or any(a != "127.0.0.1" for a in addresses):
        raise ValueError("CDP listener is not exclusively 127.0.0.1")


def is_draft_target(target):
    url = urlsplit(target.get("url", ""))
    return (
        target.get("type") == "page"
        and url.scheme == "https"
        and url.hostname == "basketball.fantasysports.yahoo.com"
        and url.username is None and url.password is None
        and url.port in (None, 443)
        and re.fullmatch(r"/draftclient/nba/\d+/\d+/?", url.path) is not None
    )


def loopback_websocket(url, port):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "ws"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != port
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or not parsed.path.startswith("/devtools/page/")
    ):
        raise ValueError("CDP must use the configured Windows loopback port")
    return url


def get_targets(port, room_path=None):
    with HTTP.open(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
        targets = json.loads(response.read(1_000_000))
    matches = [target for target in targets if is_draft_target(target)]
    if room_path is not None:
        matches = [target for target in matches if urlsplit(target["url"]).path.rstrip("/") == room_path.rstrip("/")]
    if len(matches) > 1:
        raise ValueError("Multiple Yahoo draftclients; close the unused draft tab")
    return matches


def reader_expression(selectors):
    # Selectors are configured only after inspecting the actual rendered Picks view.
    return """(() => {
const c = %s;
if (location.protocol !== 'https:' || location.hostname !== 'basketball.fantasysports.yahoo.com'
    || !/^\\/draftclient\\/nba\\/\\d+\\/\\d+\\/?$/.test(location.pathname))
  return {error: 'not_draft_document'};
const containers = document.querySelectorAll(c.history);
const users = document.querySelectorAll(c.user_slot);
if (containers.length !== 1 || users.length !== 1)
  return {error: 'history_or_user_slot_not_unique'};
const root = containers[0];
const slot = Number(users[0].getAttribute(c.user_slot_attribute));
if (!Number.isInteger(slot) || slot < 1 || slot > 12)
  return {error: 'unverified_user_slot'};
const rows = [...root.querySelectorAll(c.row)];
const picks = rows.map(row => {
  const numbers = row.querySelectorAll(c.pick);
  const players = [...row.querySelectorAll('.ys-player[data-id]')].filter(
    e => !e.closest('.ys-team,.ys-queue,button,nav,[role="tab"],[role="navigation"],[data-id="queue"],[data-id="picks"]')
  );
  const slots = row.querySelectorAll(c.slot);
  return {
    overall_pick: numbers.length === 1 ? Number(numbers[0].textContent.trim().replace(/\\.$/, '')) : null,
    yahoo_player_id: players.length === 1 ? players[0].getAttribute('data-id') : null,
    draft_slot: slots.length === 1 ? Number(slots[0].getAttribute(c.slot_attribute)) : null
  };
});
const key = '__courtIqReadOnlyObserverV1';
if (!globalThis[key] || globalThis[key].root !== root) {
  if (globalThis[key]) globalThis[key].observer.disconnect();
  const state = {root, changedAt: null};
  state.observer = new MutationObserver(() => { if (state.changedAt === null) state.changedAt = Date.now(); });
  state.observer.observe(root, {subtree:true, childList:true, attributes:true, characterData:true});
  globalThis[key] = state;
}
const changedAt = globalThis[key].changedAt;
globalThis[key].changedAt = null;
return {picks, user_slot:slot, changed_at:changedAt};
})()""" % json.dumps(selectors)


class History:
    def __init__(self):
        self.seen = {}
        self.user_slot = None

    def validate(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("error"):
            raise ValueError("Authoritative DOM structure unavailable")
        user_slot = snapshot.get("user_slot")
        if type(user_slot) is not int or not 1 <= user_slot <= 12:
            raise ValueError("User slot unavailable")
        if self.user_slot is not None and self.user_slot != user_slot:
            raise ValueError("User slot changed")
        picks = snapshot.get("picks")
        if not isinstance(picks, list) or any(not isinstance(pick, dict) for pick in picks):
            raise ValueError("Pick history missing or malformed")
        current = {}
        ids = set()
        for expected, pick in enumerate(picks, 1):
            number, yahoo_id, slot = (
                pick.get("overall_pick"), pick.get("yahoo_player_id"), pick.get("draft_slot")
            )
            expected_slot = (expected - 1) % 12 + 1
            if ((expected - 1) // 12) % 2:
                expected_slot = 13 - expected_slot
            if type(number) is not int or number != expected:
                raise ValueError("History must be ordered and contiguous from pick 1")
            if not isinstance(yahoo_id, str) or not yahoo_id.isascii() or not yahoo_id.isdigit():
                raise ValueError("Missing authoritative Yahoo ID")
            if yahoo_id in ids or type(slot) is not int or slot != expected_slot:
                raise ValueError("Duplicate player or unverified snake slot")
            ids.add(yahoo_id)
            current[number] = (yahoo_id, slot)
        if any(current.get(n) != identity for n, identity in self.seen.items()):
            raise ValueError("Earlier history missing or changed")
        fresh = [pick for pick in picks if pick["overall_pick"] not in self.seen]
        return current, user_slot, fresh

    def accept(self, current, user_slot):
        self.seen = current
        self.user_slot = user_slot


class CDP:
    def __init__(self, url):
        import websocket

        self.transport_errors = (websocket.WebSocketException, OSError)
        try:
            self.socket = websocket.create_connection(
                url, timeout=4, suppress_origin=True, http_no_proxy=["127.0.0.1", "localhost"]
            )
        except self.transport_errors:
            raise ConnectionError("CDP connection unavailable") from None
        self.sequence = 0

    def read(self, expression):
        try:
            return self._read(expression)
        except self.transport_errors:
            raise ConnectionError("CDP connection lost") from None

    def _read(self, expression):
        self.sequence += 1
        self.socket.send(json.dumps({
            "id": self.sequence, "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = json.loads(self.socket.recv())
            if response.get("id") != self.sequence:
                continue
            error_message = response.get("error", {}).get("message", "")
            if any(reason in error_message for reason in (
                "Cannot find context", "Execution context was destroyed",
                "Inspected target navigated or closed", "Session closed", "Target closed",
            )):
                raise ConnectionError("Draft document replacing")
            if "error" in response or response.get("result", {}).get("exceptionDetails"):
                raise ValueError("Draft document read failed")
            return response["result"]["result"].get("value")
        raise TimeoutError("CDP read timed out")

    def close(self):
        try:
            self.socket.close()
        except self.transport_errors:
            print("CDP connection already unavailable", flush=True)


def send_observation(origin, observer_session, picks, secret):
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use the trusted Court IQ HTTPS origin only")
    body = json.dumps({
        "observer_session": observer_session, "source": "yahoo_browser_observer",
        "picks": picks,
    }).encode()
    request = Request(
        origin.rstrip("/") + "/api/v2/draft/browser-observer/observe",
        data=body, headers={"Content-Type": "application/json", "X-Court-IQ-Observer": secret},
    )
    with HTTP.open(request, timeout=10) as response:
        result = json.loads(response.read(100_000))
    if result.get("mode") != "observe_only" or result.get("mapped_count") != len(picks):
        raise ValueError("Court IQ mapping confirmation missing")


def read_identities(origin):
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("trusted_https_court_iq_origin_required")
    # Existing read-only API; no observer secret or ingestion endpoint is used.
    with HTTP.open(origin.rstrip("/") + "/api/v1/players", timeout=10) as response:
        return json.loads(response.read(5_000_000))


def send_practice_history(origin, session_id, candidates):
    if not re.fullmatch(r"[0-9a-f-]{36}", session_id):
        raise ValueError("invalid_practice_session")
    secret = os.environ.get("COURT_IQ_OBSERVER_SECRET", "")
    if len(secret) < 43:
        raise ValueError("observer_secret_required")
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "mode": "yahoo_mock_practice",
        "picks": [{**pick, "source": "yahoo_mock_browser", "observed_at": now} for pick in candidates],
    }
    request = Request(
        origin.rstrip("/") + f"/api/v2/draft/browser-observer/practice/{session_id}/history",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Court-IQ-Observer": secret},
    )
    with HTTP.open(request, timeout=120) as response:
        result = json.loads(response.read(100_000))
    if result.get("mode") != "yahoo_mock_browser" or result.get("status") not in {"synced", "completed"}:
        raise ValueError("practice_not_synced")
    print(f"Practice confirmed through pick {result['confirmed_through']} | new={len(result['accepted_picks'])}", flush=True)


def inspect_candidates(args):
    from picks import CandidateHistory, DIRTY_EXPRESSION, expression, mapping_report, parse

    history, cdp, room_path, target_id = CandidateHistory(), None, None, None
    next_discovery, next_full_read, next_mapping = 0, 0, 0
    identities = None
    timings = []
    practice = getattr(args, "practice", False)
    read_expression = expression(args.history_selector)
    dirty_expression = DIRTY_EXPRESSION
    if practice:
        # Allow the original read-only watcher to continue independently.
        read_expression = read_expression.replace("__courtIqCandidatePicksV1", "__courtIqPracticePicksV1")
        dirty_expression = dirty_expression.replace("__courtIqCandidatePicksV1", "__courtIqPracticePicksV1")
    try:
        while True:
            try:
                if cdp is None or time.monotonic() >= next_discovery:
                    verify_windows_listener(args.port)
                    targets = get_targets(args.port)
                    if not targets:
                        raise ConnectionError("No draft target")
                    target = targets[0]
                    path = urlsplit(target["url"]).path
                    if room_path is not None and path != room_path:
                        raise ValueError("different_draft_room")
                    room_path = path
                    if cdp is None or target_id != target["id"]:
                        if cdp:
                            cdp.close()
                        cdp = CDP(loopback_websocket(target["webSocketDebuggerUrl"], args.port))
                        target_id, next_full_read = target["id"], 0
                        if args.open_picks:
                            opened = cdp.read(OPEN_PICKS_EXPRESSION)
                            if not isinstance(opened, dict) or not opened.get("opened_read_only_picks_tab"):
                                raise ConnectionError("Picks not ready")
                            time.sleep(0.5)
                    next_discovery = time.monotonic() + 10
                if time.monotonic() < next_full_read and not cdp.read(dirty_expression):
                    time.sleep(0.25)
                    continue
                snapshot = cdp.read(read_expression)
                if isinstance(snapshot, dict) and snapshot.get("error") == "not_draft_document":
                    raise ConnectionError("Document replacing")
                candidates, gaps = parse(snapshot)
                read_at = time.time() * 1000
                fresh = history.check(candidates)
                if identities is None or fresh or time.monotonic() >= next_mapping:
                    identities = read_identities(args.origin)
                    next_mapping = time.monotonic() + 10
                report = mapping_report(candidates, identities)
                print(json.dumps({
                    "history_start": candidates[0]["overall_pick"],
                    "history_end": candidates[-1]["overall_pick"],
                    "gaps": gaps, **report,
                }), flush=True)
                if gaps:
                    raise ValueError("visible_history_has_gaps")
                if report["unmapped_ids"] or report["ambiguous_ids"]:
                    raise ValueError("yahoo_id_mapping_failed")
                if practice:
                    if candidates[0]["overall_pick"] != 1:
                        raise ValueError("practice_requires_history_from_pick_1")
                    send_practice_history(args.origin, args.practice_session, candidates)
                history.accept(candidates)
                for pick in fresh:
                    print(f"Pick {pick['overall_pick']} | yahoo_player_id={pick['yahoo_player_id']} | mapped=yes", flush=True)
                changed = snapshot.get("changed_at")
                if fresh and isinstance(changed, (int, float)):
                    import statistics
                    delay = max(0, read_at-changed)
                    timings.append(delay)
                    print(f"DOM mutation-to-parse delay ms: {delay:.0f}", flush=True)
                    print(f"Local DOM timings count={len(timings)} min={min(timings):.0f} median={statistics.median(timings):.0f} max={max(timings):.0f} ms", flush=True)
                if not args.watch:
                    return 0
                next_full_read = time.monotonic() + 10
                time.sleep(0.25)
            except HTTPError as error:
                print(f"STOP: Court IQ HTTP {error.code}; automatic practice writes stopped", flush=True)
                return 1
            except ValueError as error:
                # Only locally generated reason codes; never print browser/server exceptions.
                safe_reasons = {
                    "different_draft_room", "visible_history_has_gaps", "yahoo_id_mapping_failed",
                    "previous_pick_changed_or_disappeared", "no_numbered_pick_rows",
                    "malformed_history_snapshot", "picks_control_not_unique",
                    "history_container_not_unique", "history_container_not_visible_or_not_narrow",
                    "history_container_too_large", "ambiguous_numbered_entry",
                    "player_without_numbered_entry", "duplicate_or_nonascending_pick",
                    "duplicate_yahoo_player_id",
                    "practice_requires_history_from_pick_1", "observer_secret_required",
                    "practice_not_synced", "invalid_practice_session",
                }
                reason = str(error)
                if reason not in safe_reasons and not re.fullmatch(
                    r"pick_[0-9]{1,3}_(requires_exactly_one_ys_player|team_or_ui_not_player|invalid_ys_player_id)", reason
                ):
                    reason = "invalid_structure_or_configuration"
                print(f"STOP: {reason}; no ingestion or draft writes", flush=True)
                return 1
            except (OSError, TimeoutError, subprocess.TimeoutExpired):
                if cdp:
                    cdp.close()
                cdp, target_id = None, None
                print("Candidate observer unavailable/reconnecting; no ingestion or draft writes", flush=True)
                if not args.watch:
                    return 1
                time.sleep(5)
    finally:
        if cdp:
            cdp.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--selectors", type=Path)
    parser.add_argument("--origin")
    parser.add_argument("--observer-session")
    parser.add_argument("--inspect-structure", action="store_true")
    parser.add_argument("--inspect-picks", action="store_true",
                        help="Print ID-mapped candidates only; never send ingestion events")
    parser.add_argument("--watch", action="store_true",
                        help="Watch candidate Picks mutations with --inspect-picks")
    parser.add_argument("--practice", action="store_true",
                        help="Explicitly reconcile a disposable Yahoo Mock Practice session only")
    parser.add_argument("--practice-session")
    parser.add_argument("--open-picks", action="store_true",
                        help="Display only the verified Picks tab button; never select a player")
    parser.add_argument("--history-selector",
                        help="Verified narrow history container for structure inspection only")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a non-privileged loopback port")
    if os.name != "nt":
        parser.error("Run on the Windows PC alongside Yahoo Chrome; Linux loopback is not Windows")
    if args.inspect_structure and args.inspect_picks:
        parser.error("Choose one diagnostic mode")
    if args.watch and not args.inspect_picks:
        parser.error("--watch requires --inspect-picks")
    if args.practice and (not args.inspect_picks or not args.practice_session):
        parser.error("--practice requires --inspect-picks and --practice-session")
    if (args.open_picks or args.history_selector) and not (args.inspect_structure or args.inspect_picks):
        parser.error("--open-picks/--history-selector require an inspection mode")
    if args.inspect_picks:
        if not args.origin:
            parser.error("--inspect-picks requires the trusted HTTPS --origin for read-only ID verification")
        return inspect_candidates(args)
    if args.inspect_structure:
        try:
            verify_windows_listener(args.port)
            targets = get_targets(args.port)
            if not targets:
                raise ValueError("No target")
            cdp = CDP(loopback_websocket(targets[0]["webSocketDebuggerUrl"], args.port))
            try:
                if args.open_picks:
                    opened = cdp.read(OPEN_PICKS_EXPRESSION)
                    if not isinstance(opened, dict) or opened.get("error"):
                        print("STOP: exact read-only Picks button not verified; no action taken")
                        return 1
                    time.sleep(0.5)
                result = cdp.read(structure_expression(args.history_selector))
                print(json.dumps({
                    "inspector_version": INSPECTOR_VERSION,
                    "result": result,
                }, indent=2))
                if not isinstance(result, dict) or result.get("error"):
                    return 1
            finally:
                cdp.close()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            print("Draft structure unavailable; no draft writes")
            return 1
        return 0
    if not args.selectors or not args.origin or not args.observer_session:
        parser.error("Observe-only mode needs --selectors, --origin and --observer-session")
    secret = os.environ.get("COURT_IQ_OBSERVER_SECRET", "")
    if len(secret) < 43:
        parser.error("Set a dedicated high-entropy COURT_IQ_OBSERVER_SECRET")
    selectors = json.loads(args.selectors.read_text(encoding="utf-8-sig"))
    required = {"history", "row", "pick", "slot", "slot_attribute", "user_slot", "user_slot_attribute"}
    if set(selectors) != required or not all(isinstance(v, str) and v for v in selectors.values()):
        parser.error("Supply all verified Picks selectors and slot attributes")
    expression = reader_expression(selectors)
    history = History()
    cdp = None
    target_id = None
    room_path = None
    next_discovery = 0
    next_full_read = 0
    try:
        while True:
            try:
                if cdp is None or time.monotonic() >= next_discovery:
                    verify_windows_listener(args.port)
                    targets = get_targets(args.port)
                    if not targets:
                        raise ConnectionError("No matching draftclient")
                    target = targets[0]
                    detected_path = urlsplit(target["url"]).path
                    if room_path is not None and detected_path != room_path:
                        raise ValueError("Different room; start a separate observation")
                    room_path = detected_path
                    if cdp is None or target_id != target["id"]:
                        if cdp:
                            cdp.close()
                        cdp = CDP(loopback_websocket(target["webSocketDebuggerUrl"], args.port))
                        target_id = target["id"]
                        next_full_read = 0
                        print("Yahoo Basketball draftclient detected; connected: yes", flush=True)
                    next_discovery = time.monotonic() + 10
                changed = cdp.read(
                    "(() => { const s=globalThis.__courtIqReadOnlyObserverV1;"
                    "return !s || !s.root.isConnected || s.changedAt !== null; })()"
                )
                if not changed and time.monotonic() < next_full_read:
                    time.sleep(0.25)
                    continue
                snapshot = cdp.read(expression)
                if isinstance(snapshot, dict) and snapshot.get("error") == "not_draft_document":
                    raise ConnectionError("Draft document replacing/reconnecting")
                current, user_slot, fresh = history.validate(snapshot)
                read_at = time.time() * 1000
                now = datetime.now(timezone.utc).isoformat()
                events = [{**pick, "observed_at": now} for pick in snapshot["picks"]]
                send_observation(args.origin, args.observer_session, events, secret)
                history.accept(current, user_slot)
                next_full_read = time.monotonic() + 10
                for pick in fresh:
                    print(json.dumps({**pick, "observed_at": now, "source": "yahoo_browser_observer"}), flush=True)
                changed = snapshot.get("changed_at")
                if fresh and changed is not None:
                    print(f"Local mutation-to-read delay ms: {max(0, read_at-changed):.0f}", flush=True)
                time.sleep(0.25)
            except HTTPError as error:
                if 400 <= error.code < 500:
                    print(f"STOP: Court IQ rejected observation (HTTP {error.code}); no draft writes", flush=True)
                    return 1
                if cdp:
                    cdp.close()
                cdp, target_id = None, None
                print("Court IQ unavailable; observation will be retried without draft writes", flush=True)
                time.sleep(5)
            except ValueError:
                print("STOP: authoritative structure, history, mapping, or configuration failed; no draft writes", flush=True)
                return 1
            except (OSError, TimeoutError, subprocess.TimeoutExpired):
                if cdp:
                    cdp.close()
                cdp, target_id = None, None
                print("Observer unavailable/reconnecting; no draft writes", flush=True)
                time.sleep(5)
    finally:
        if cdp:
            cdp.close()


if __name__ == "__main__":
    raise SystemExit(main())

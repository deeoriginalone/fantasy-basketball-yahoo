import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.database import get_session
from app.features.draft.browser_observer import router


OBSERVER_PATH = Path(__file__).resolve().parents[2] / "scripts/yahoo-observer/observer.py"
spec = importlib.util.spec_from_file_location("windows_observer", OBSERVER_PATH)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
pick_spec = importlib.util.spec_from_file_location("candidate_picks", OBSERVER_PATH.with_name("picks.py"))
candidate_picks = importlib.util.module_from_spec(pick_spec)
pick_spec.loader.exec_module(candidate_picks)


def candidate_row(number=30, yahoo_id="5827", **overrides):
    return {
        "overall_pick": number, "row_verified": True,
        "players": [{"semantic_player": True, "excluded": False, "yahoo_player_id": yahoo_id}],
        **overrides,
    }


def test_candidate_ordered_offset_history_and_mapping():
    picks, gaps = candidate_picks.parse({"rows": [candidate_row(), candidate_row(31, "4612")]})
    assert gaps == []
    assert picks[0] == {"overall_pick": 30, "yahoo_player_id": "5827"}
    report = candidate_picks.mapping_report(picks, [
        {"id": 1, "yahoo_player_id": "5827"}, {"id": 2, "yahoo_player_id": "4612"},
    ])
    assert report["uniquely_mapped"] == 2
    assert not report["unmapped_ids"]


@pytest.mark.parametrize("row", [
    candidate_row(yahoo_id="queue"), candidate_row(yahoo_id="picks"),
    candidate_row(yahoo_id="not-numeric"), candidate_row(players=[]),
    candidate_row(players=[{}, {}]), candidate_row(row_verified=False),
    candidate_row(players=[{"semantic_player": True, "excluded": True, "yahoo_player_id": "1"}]),
    candidate_row(players=[{"semantic_player": False, "excluded": False, "yahoo_player_id": "1"}]),
])
def test_candidate_requires_exactly_one_non_ui_semantic_player(row):
    with pytest.raises(ValueError):
        candidate_picks.parse({"rows": [row]})


def test_candidate_duplicate_pick_player_and_gap():
    for rows in [
        [candidate_row(), candidate_row()],
        [candidate_row(), candidate_row(31, "5827")],
        [candidate_row(31), candidate_row(30, "4612")],
    ]:
        with pytest.raises(ValueError):
            candidate_picks.parse({"rows": rows})
    picks, gaps = candidate_picks.parse({"rows": [candidate_row(), candidate_row(32, "4612")]})
    assert gaps == [[31, 31]]
    assert picks[0]["overall_pick"] == 30  # No fabricated earlier picks.


def test_candidate_reread_mutation_duplicates_conflict_and_catchup():
    history = candidate_picks.CandidateHistory()
    picks, _ = candidate_picks.parse({"rows": [candidate_row()]})
    assert history.check(picks) == picks
    history.accept(picks)
    assert history.check(picks) == []
    catchup, _ = candidate_picks.parse({"rows": [
        candidate_row(), candidate_row(31, "4612"), candidate_row(32, "6702"),
    ]})
    assert len(history.check(catchup)) == 2
    history.accept(catchup)
    assert history.check(catchup) == []
    changed, _ = candidate_picks.parse({"rows": [candidate_row(30, "999")]})
    with pytest.raises(ValueError, match="changed_or_disappeared"):
        history.check(changed)


def test_candidate_mapping_never_uses_names():
    picks, _ = candidate_picks.parse({"rows": [candidate_row()]})
    report = candidate_picks.mapping_report(picks, [
        {"id": 1, "yahoo_player_id": "999", "player_name": "same display name"},
    ])
    assert report["unmapped_ids"] == ["5827"]
    report = candidate_picks.mapping_report(picks, [
        {"id": 1, "yahoo_player_id": "5827"}, {"id": 2, "yahoo_player_id": "5827"},
    ])
    assert report["ambiguous_ids"] == ["5827"]


def test_candidate_diagnostics_and_reads_do_not_forward_secrets():
    expression = candidate_picks.expression()
    assert ".ys-player[data-id]" in expression
    assert ".ys-team" in expression
    for forbidden in ["location.search", "location.href", "outerHTML", "innerHTML", ".click(", "fetch("]:
        assert forbidden not in expression
    with pytest.raises(ValueError, match="unrecognized_history_error"):
        candidate_picks.parse({"error": "https://example/?auth=SECRET"})
    with pytest.raises(ValueError, match="trusted_https"):
        observer.read_identities("https://example/?auth=SECRET")


def pick(number=1, yahoo_id="6014", slot=1):
    return {"overall_pick": number, "yahoo_player_id": yahoo_id, "draft_slot": slot}


def target(url="https://basketball.fantasysports.yahoo.com/draftclient/nba/123/9?auth=DO_NOT_LOG", **kwargs):
    return {"type": "page", "id": "one", "url": url, **kwargs}


def test_target_matching_ignores_auth_query_without_exposing_it():
    assert observer.is_draft_target(target())
    for url in [
        "https://basketball.fantasysports.yahoo.com/nba/50505/mock_lobby",
        "https://evil.example/draftclient/nba/123/9",
        "https://basketball.fantasysports.yahoo.com.evil.example/draftclient/nba/123/9",
        "https://basketball.fantasysports.yahoo.com/usync.html",
        "http://basketball.fantasysports.yahoo.com/draftclient/nba/123/9",
    ]:
        assert not observer.is_draft_target(target(url))
    assert not observer.is_draft_target(target(type="iframe"))


@pytest.mark.parametrize("url", [
    "ws://192.168.0.2:9222/devtools/page/a",
    "ws://127.0.0.1:9333/devtools/page/a",
    "ws://127.0.0.1:9222/devtools/page/a?secret=unsafe",
    "ws://user:pass@127.0.0.1:9222/devtools/page/a",
    "ws://127.0.0.1:9222/devtools/browser/a",
])
def test_remote_or_secret_cdp_urls_rejected(url):
    with pytest.raises(ValueError):
        observer.loopback_websocket(url, 9222)


def test_incremental_history_and_duplicate_mutations():
    history = observer.History()
    snapshot = {"user_slot": 9, "picks": [pick()]}
    current, slot, fresh = history.validate(snapshot)
    assert fresh == [pick()]
    history.accept(current, slot)
    assert history.validate(snapshot)[2] == []
    snapshot["picks"].append(pick(2, "123", 2))
    assert history.validate(snapshot)[2] == [pick(2, "123", 2)]
    # Failed server delivery does not acknowledge new local picks.
    assert history.validate(snapshot)[2] == [pick(2, "123", 2)]


@pytest.mark.parametrize("picks", [
    [pick(2, "123", 2)], [pick(1, None)], [pick(), pick(2, "6014", 2)],
    [pick(), pick(3, "123", 3)], [pick(1, "6014", 2)],
])
def test_missing_ids_order_gaps_duplicate_and_wrong_slot_rejected(picks):
    with pytest.raises(ValueError):
        observer.History().validate({"user_slot": 9, "picks": picks})


def test_reconstruction_must_preserve_history_and_user_slot():
    history = observer.History()
    current, slot, _ = history.validate({"user_slot": 9, "picks": [pick()]})
    history.accept(current, slot)
    assert history.validate({"user_slot": 9, "picks": [pick()]})[2] == []
    for snapshot in [
        {"user_slot": 9, "picks": []},
        {"user_slot": 9, "picks": [pick(1, "999")]},
        {"user_slot": 8, "picks": [pick()]},
    ]:
        with pytest.raises(ValueError):
            history.validate(snapshot)


@pytest.mark.parametrize("snapshot", [None, {}, {"user_slot": 9}, {"user_slot": 9, "picks": [None]}])
def test_malformed_snapshot_fails_closed(snapshot):
    with pytest.raises(ValueError):
        observer.History().validate(snapshot)


def test_reader_is_local_dom_only_and_never_automates_yahoo():
    expression = observer.reader_expression({
        "history": ".history", "row": ".row", "pick": ".number",
        "slot": ".slot", "slot_attribute": "data-slot",
        "user_slot": ".me", "user_slot_attribute": "data-slot",
    })
    assert "MutationObserver" in expression
    assert "[data-id]" in expression
    for forbidden in [".click(", ".focus(", ".submit(", "fetch(", "XMLHttpRequest", "document.cookie", "location.href"]:
        assert forbidden not in expression
    source = OBSERVER_PATH.read_text()
    for forbidden in ["Page.navigate", "Page.reload", "Network.", "Input.", "Storage.", "document.cookie"]:
        assert forbidden not in source


@pytest.mark.parametrize("ui_id", ["queue", "picks"])
def test_ui_control_values_cannot_be_player_ids(ui_id):
    with pytest.raises(ValueError, match="Missing authoritative Yahoo ID"):
        observer.History().validate({"user_slot": 9, "picks": [pick(1, ui_id)]})


def test_structure_discovery_never_promotes_generic_or_team_ids():
    expression = observer.structure_expression()
    assert "document.querySelectorAll('[data-id]')" not in expression
    assert "drafted_id_ancestors" not in expression
    assert ".ys-team" in expression
    assert "team_or_ui_not_player" in expression
    assert "unclassified_not_a_player_yet" in expression
    assert "drafted_player_ids:[], pick_history_rows:[]" in expression
    assert "data-id=\"queue\"" in expression
    assert "data-id=\"picks\"" in expression
    assert "host.children.length === 2" in expression


def test_only_explicit_picks_tab_display_is_permitted():
    expression = observer.OPEN_PICKS_EXPRESSION
    assert "e.textContent.trim() === 'Picks'" in expression
    assert "e.getAttribute('data-id') === 'picks'" in expression
    assert "e.getAttribute('role') === 'tab'" in expression
    assert "controls.length !== 1" in expression
    assert "controls[0].click()" in expression
    assert ".click()" not in observer.STRUCTURE_EXPRESSION
    assert ".click()" not in observer.reader_expression({})


def test_structure_diagnostics_have_no_url_or_raw_dom_output():
    expression = observer.STRUCTURE_EXPRESSION
    for forbidden in [
        "location.href", "location.search", "outerHTML", "innerHTML",
        "document.cookie", "webSocketDebuggerUrl", "e.attributes",
    ]:
        assert forbidden not in expression
    assert "'[redacted]'" in expression
    assert "text_pattern" in expression
    assert observer.INSPECTOR_VERSION == "picks-subtree-2"


class FakeSession:
    def __init__(self, rows=None, imported=None):
        self.rows = [(41, "6014")] if rows is None else rows
        self.imported = [41] if imported is None else imported

    async def execute(self, statement):
        class Result:
            def all(inner):
                return self.rows
        return Result()

    async def scalars(self, statement):
        class Result:
            def all(inner):
                return self.imported
        return Result()


@pytest.fixture
def client(monkeypatch):
    for name, value in {
        "COURT_IQ_OBSERVER_SECRET": "a" * 64,
        "COURT_IQ_OBSERVER_PRACTICE_SESSION": "mock-evidence",
        "COURT_IQ_OBSERVER_LEAGUE_KEY": "fixture",
        "COURT_IQ_OBSERVER_ORIGIN": "https://court.example",
    }.items():
        monkeypatch.setenv(name, value)
    app = FastAPI()
    app.include_router(router)
    fake = FakeSession()
    app.dependency_overrides[get_session] = lambda: fake
    with TestClient(app, base_url="https://court.example") as test_client:
        yield test_client, fake


def post(client, *, picks=None, session="mock-evidence", source="yahoo_browser_observer", secret="a" * 64):
    return client.post("/api/v2/draft/browser-observer/observe", headers={"X-Court-IQ-Observer": secret}, json={
        "observer_session": session, "source": source,
        "picks": [{**p, "observed_at": "2026-10-18T17:00:00+00:00"} for p in ([pick()] if picks is None else picks)],
    })


def test_observe_only_mapping_is_repeatable_without_write_methods(client):
    api, _ = client
    for _ in range(2):
        result = post(api)
        assert result.status_code == 200, result.text
        assert result.json() == {
            "mode": "observe_only", "mapped_count": 1,
            "confirmed_through": 1, "draft_writes": False,
        }


def test_authentication_origin_source_and_live_isolation(client, monkeypatch):
    api, _ = client
    assert post(api, secret="wrong").status_code == 401
    assert post(api, session="real-live-session").status_code == 403
    assert post(api, source="yahoo_draftresults").status_code == 422
    assert api.post("/api/v2/draft/browser-observer/observe", headers={
        "Host": "evil.example", "X-Court-IQ-Observer": "a" * 64,
    }, json={"observer_session": "mock-evidence", "source": "yahoo_browser_observer", "picks": []}).status_code == 403
    monkeypatch.delenv("COURT_IQ_OBSERVER_SECRET")
    assert post(api).status_code == 503


@pytest.mark.parametrize("rows,imported", [
    ([], []), ([(41, "6014"), (42, "6014")], [41, 42]), ([(41, "6014")], []),
])
def test_unknown_ambiguous_or_unimported_id_rejected(client, rows, imported):
    api, fake = client
    fake.rows, fake.imported = rows, imported
    assert post(api).status_code == 422


def test_invalid_history_rejected_by_server(client):
    api, _ = client
    assert post(api, picks=[pick(2, "6014", 2)]).status_code == 422
    assert post(api, picks=[pick(1, "", 1)]).status_code == 422
    assert post(api, picks=[pick(), pick(2, "6014", 2)]).status_code == 422


def test_server_latches_history_conflict_without_draft_writes(client):
    api, _ = client
    assert post(api).status_code == 200
    assert post(api, picks=[]).status_code == 409
    assert post(api).status_code == 409


def test_https_only_and_no_redirect_replay():
    with pytest.raises(ValueError):
        observer.send_observation("http://court.example", "mock", [], "a" * 64)
    with pytest.raises(ValueError):
        observer.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")


def test_cdp_disconnect_and_recreated_connection_only_evaluates_dom(monkeypatch):
    class TransportError(Exception):
        pass

    sent = []

    class Socket:
        def __init__(self, disconnected):
            self.disconnected = disconnected

        def send(self, data):
            sent.append(json.loads(data))

        def recv(self):
            if self.disconnected:
                raise TransportError("sensitive transport diagnostic must not escape")
            return json.dumps({"id": 1, "result": {"result": {"value": {"picks": []}}}})

        def close(self):
            pass

    sockets = iter([Socket(True), Socket(False)])

    def connect(url, **kwargs):
        assert url == "ws://127.0.0.1:9222/devtools/page/test"
        assert kwargs["http_no_proxy"] == ["127.0.0.1", "localhost"]
        return next(sockets)

    monkeypatch.setitem(sys.modules, "websocket", SimpleNamespace(
        WebSocketException=TransportError, create_connection=connect,
    ))
    cdp = observer.CDP("ws://127.0.0.1:9222/devtools/page/test")
    with pytest.raises(ConnectionError, match="CDP connection lost"):
        cdp.read("read-only")
    cdp.close()
    cdp = observer.CDP("ws://127.0.0.1:9222/devtools/page/test")
    assert cdp.read("read-only") == {"picks": []}
    cdp.close()
    assert all(command["method"] == "Runtime.evaluate" for command in sent)


def test_target_reacquisition_and_multiple_rooms_refused(monkeypatch):
    responses = iter([
        [target()],
        [target(id="recreated")],
        [target(), target(id="other")],
    ])

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps(next(responses)).encode()

    def open_local(url, timeout):
        assert url == "http://127.0.0.1:9222/json/list"
        return Response()

    monkeypatch.setattr(observer, "HTTP", SimpleNamespace(open=open_local))
    assert observer.get_targets(9222)[0]["id"] == "one"
    assert observer.get_targets(9222)[0]["id"] == "recreated"
    with pytest.raises(ValueError, match="Multiple"):
        observer.get_targets(9222)


@pytest.mark.parametrize("addresses,allowed", [
    (["127.0.0.1"], True), (["0.0.0.0"], False),
    (["127.0.0.1", "::"], False), ([], False),
])
def test_windows_listener_must_be_exclusively_loopback(monkeypatch, addresses, allowed):
    def run(args, **kwargs):
        assert args[:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
        assert "-LocalPort 9222" in args[-1]
        assert kwargs["creationflags"] == 0x08000000
        return SimpleNamespace(returncode=0, stdout=json.dumps(addresses))
    monkeypatch.setattr(observer.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(observer.subprocess, "run", run)
    if allowed:
        observer.verify_windows_listener(9222)
    else:
        with pytest.raises(ValueError, match="exclusively"):
            observer.verify_windows_listener(9222)

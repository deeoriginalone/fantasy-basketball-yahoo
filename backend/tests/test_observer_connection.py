from datetime import datetime, timezone
import os
from types import SimpleNamespace
import importlib.util
import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.features.draft.observer_connection import (
    ConnectBody, DesktopSnapshot, ObserverConnection, router, view,
    apply_confirmed_mock_rounds,
    desktop_lock, paired,
)

ROOT = Path(__file__).resolve().parents[2]


def test_stop_does_not_wait_for_snapshot_serialization_lock():
    route = next(route for route in router.routes if route.path.endswith("/stop"))
    dependencies = {dependency.call for dependency in route.dependant.dependencies}
    assert paired in dependencies
    assert desktop_lock not in dependencies


def test_confirmed_mock_rounds_reused_only_for_twelve_team_practice(monkeypatch):
    monkeypatch.setenv("COURT_IQ_OBSERVER_MOCK_ROUNDS", "13")
    for _ in range(2):
        details = {"total_teams": 12, "rounds": None}
        apply_confirmed_mock_rounds("mock", details)
        assert details["rounds"] == 13
        assert details["rounds_source"] == "user_confirmed_mock_configuration"
    for mode, details in [
        ("live", {"total_teams": 12}),
        ("mock", {"total_teams": 10}),
        ("mock", {}),
        ("mock", {"total_teams": 12, "rounds": 15}),
    ]:
        before = dict(details)
        apply_confirmed_mock_rounds(mode, details)
        assert details == before
    monkeypatch.delenv("COURT_IQ_OBSERVER_MOCK_ROUNDS")
    details = {"total_teams": 12}
    apply_confirmed_mock_rounds("mock", details)
    assert "rounds" not in details


def test_invalid_confirmed_mock_rounds_fails_explicitly(monkeypatch):
    from fastapi import HTTPException

    for value in ["unknown", "0", "51"]:
        monkeypatch.setenv("COURT_IQ_OBSERVER_MOCK_ROUNDS", value)
        with pytest.raises(HTTPException) as error:
            apply_confirmed_mock_rounds("mock", {"total_teams": 12})
        assert error.value.status_code == 503


@pytest.fixture
def client(monkeypatch):
    for key, value in {
        "COURT_IQ_OBSERVER_SECRET": "s"*64,
        "COURT_IQ_OBSERVER_PRACTICE_SESSION": "practice",
        "COURT_IQ_OBSERVER_LEAGUE_KEY": "fixture",
        "COURT_IQ_OBSERVER_ORIGIN": "https://court.example",
    }.items():
        monkeypatch.setenv(key, value)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, base_url="https://court.example") as c:
        yield c


def test_pairing_requires_desktop_secret_and_same_origin_then_sets_secure_cookie(client):
    code = "x"*32
    assert client.post("/api/v2/draft/observer-connection/pairing", json={"code": code}).status_code == 401
    assert client.post("/api/v2/draft/observer-connection/pairing",
        headers={"X-Court-IQ-Observer": "s"*64}, json={"code": code}).status_code == 200
    assert client.post("/api/v2/draft/observer-connection/pair", json={"code": code}).status_code == 403
    r = client.post("/api/v2/draft/observer-connection/pair",
        headers={"Origin": "https://court.example"}, json={"code": code})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "s"*64 not in cookie
    assert client.post("/api/v2/draft/observer-connection/pair",
        headers={"Origin": "https://court.example"}, json={"code": code}).status_code == 401


def test_unpaired_connection_and_csrf_rejected(client):
    body = {"room_path": "/draftclient/nba/123/10", "mode": "mock"}
    assert client.post("/api/v2/draft/observer-connection",
        headers={"Origin": "https://court.example"}, json=body).status_code == 401
    assert client.post("/api/v2/draft/observer-connection",
        headers={"Origin": "https://evil.example"}, json=body).status_code == 403
    assert client.post("/api/v2/draft/observer-connection/example/stop",
        headers={"Origin": "https://court.example"}).status_code == 401
    assert client.post("/api/v2/draft/observer-connection/example/stop",
        headers={"Origin": "https://evil.example"}).status_code == 403


@pytest.mark.parametrize("value", [
    "/draftclient/nba/123/10?auth=SECRET",
    "https://basketball.fantasysports.yahoo.com/draftclient/nba/123/10",
    "/nba/50505/mock_lobby", "/usync.html",
])
def test_server_accepts_only_sanitized_room_path(value):
    with pytest.raises(ValidationError):
        ConnectBody(room_path=value, mode="mock")


def test_connection_view_preserves_safe_status_and_room_path():
    record = ObserverConnection(
        id="x"*64, room_path="/draftclient/nba/123/10", mode="mock",
        active=True, session_id=None, status="YOUR TURN",
        details={"user_slot": 10, "yahoo_through": 9, "court_iq_through": 9},
        updated_at=datetime.now(timezone.utc),
    )
    assert view(record)["user_slot"] == 10
    assert view(record)["status"] == "YOUR TURN"


def test_desktop_contract_excludes_browser_secrets_and_invalid_mode():
    for extra in [{"cookie": "secret"}, {"auth": "secret"}, {"url": "secret"}]:
        with pytest.raises(ValidationError):
            DesktopSnapshot(state="CONNECTED", **extra)
    with pytest.raises(ValidationError):
        ConnectBody(room_path="/draftclient/nba/123/10", mode="enable_live_writes")


def test_desktop_exact_target_filter_and_dpapi_source_boundaries():
    desktop = (ROOT / "scripts/yahoo-observer/desktop.py").read_text()
    assert 'room_path=job["room_path"]' in desktop
    assert 'cdp.read("location.pathname").rstrip("/") != job["room_path"]' in desktop
    assert "CryptProtectData" in desktop and "CryptUnprotectData" in desktop
    for forbidden in ["document.cookie", "Network.", "Page.navigate", "Page.reload", "Input."]:
        assert forbidden not in desktop
    assert "http.server" not in desktop  # No inbound LAN/loopback credential endpoint.
    installer = (ROOT / "scripts/yahoo-observer/Install-CourtIQObserver.ps1").read_text()
    assert "New-NetFirewallRule" not in installer
    assert "connection.json" not in installer  # Reinstallation must preserve saved DPAPI config.
    ast.parse(desktop)


def test_desktop_reconnects_requested_room_and_resends_idempotent_full_history(monkeypatch):
    folder = ROOT / "scripts/yahoo-observer"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("desktop_under_test", folder / "desktop.py")
    desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desktop)
    job = {"id": "safe-job", "room_path": "/draftclient/nba/123/10",
           "request_generation": 1, "status": "CONNECTING"}
    calls, sockets = [], []

    class Finished(BaseException):
        pass

    class Config:
        def read_text(self, **kwargs):
            return '{"origin":"https://court.example","port":9222}'

    class API:
        def __init__(self, config):
            pass

        def call(self, path, body=None):
            if path == "/agent":
                return {"connection": job}
            calls.append(body)
            if len(calls) == 3:
                raise Finished()
            return {"status": "SYNCED"}

    class CDP:
        def __init__(self, url):
            self.failed = False
            sockets.append(self)

        def read(self, code):
            if code == "location.pathname":
                return job["room_path"]
            if code == desktop.METADATA_EXPRESSION:
                return {"user_slot": 10, "total_teams": 12, "rounds": 13}
            if code == desktop.DIRTY_EXPRESSION:
                if len(sockets) == 1 and not self.failed:
                    self.failed = True
                    raise ConnectionError("Document replaced")
                return True
            return {"rows": [{
                "overall_pick": 1, "row_verified": True,
                "players": [{"semantic_player": True, "excluded": False, "yahoo_player_id": "5352"}],
            }]}

        def close(self):
            pass

    def targets(port, room_path=None):
        assert port == 9222 and room_path == job["room_path"]
        return [{"id": "target", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/test"}]

    monkeypatch.setattr(desktop, "CONFIG", Config())
    monkeypatch.setattr(desktop, "API", API)
    monkeypatch.setattr(desktop.observer, "CDP", CDP)
    monkeypatch.setattr(desktop.observer, "get_targets", targets)
    monkeypatch.setattr(desktop.observer, "verify_windows_listener", lambda port: None)
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: None)
    with pytest.raises(Finished):
        desktop.run()
    assert len(sockets) == 2
    assert all(body["picks"][0]["yahoo_player_id"] == "5352" for body in calls)
    assert all(set(body["picks"][0]) == {
        "overall_pick", "yahoo_player_id", "source", "observed_at",
    } for body in calls)


def test_windowless_bootstrap_and_hidden_chrome_recovery(monkeypatch, tmp_path):
    folder = ROOT / "scripts/yahoo-observer"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("desktop_launch_test", folder / "desktop.py")
    desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desktop)
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    pythonw.touch()
    monkeypatch.setattr(desktop.sys, "executable", str(python))
    monkeypatch.setattr(desktop.observer.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    startup = SimpleNamespace(dwFlags=0, wShowWindow=1)
    monkeypatch.setattr(desktop.subprocess, "STARTUPINFO", lambda: startup, raising=False)
    monkeypatch.setattr(desktop.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(desktop.subprocess, "SW_HIDE", 0, raising=False)
    launches = []
    def launch(args, **kwargs):
        assert kwargs["creationflags"] == 0x08000000
        assert kwargs["startupinfo"].wShowWindow == 0
        launches.append((args, kwargs))
    monkeypatch.setattr(desktop.subprocess, "Popen", launch)
    assert desktop.relaunch_windowless([]) is True
    assert launches[0][0][0] == str(pythonw)
    assert all(launches[0][1][key] == desktop.subprocess.DEVNULL for key in ("stdin", "stdout", "stderr"))
    monkeypatch.setattr(desktop.sys, "executable", str(pythonw))
    assert desktop.relaunch_windowless([]) is False
    monkeypatch.setattr(desktop.observer, "verify_windows_listener", lambda port: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr(desktop.subprocess, "run", launch)
    with pytest.raises(ConnectionError):
        desktop.ensure_chrome(9222)
    assert launches[-1][0][:5] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]


def test_desktop_log_is_bounded_and_installer_replaces_only_owned_windowless_agent(monkeypatch, tmp_path):
    folder = ROOT / "scripts/yahoo-observer"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("desktop_log_test", folder / "desktop.py")
    desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desktop)
    monkeypatch.setattr(desktop, "FOLDER", tmp_path)
    desktop.configure_logging()
    try:
        handler = desktop.logger.handlers[-1]
        assert handler.maxBytes == 262144 and handler.backupCount == 2
        assert desktop.logger.propagate is False
        desktop.logger.info("Observer starting")
        assert "Observer starting" in (tmp_path / "observer.log").read_text()
    finally:
        desktop.logger.removeHandler(handler)
        handler.close()
    installer = (folder / "Install-CourtIQObserver.ps1").read_text()
    assert "$_.ExecutablePath -eq $agent" in installer
    assert '$_.CommandLine -like "*`"$desktop`"*"' in installer
    assert "Stop-Process -Id $_.ProcessId" in installer
    assert installer.index("Stop-Process") < installer.index("Copy-Item")
    assert 'Arguments="`"$desktop`" --diagnostic"' in installer
    assert 'Start-Process -FilePath $pythonw -ArgumentList @("`"$desktop`"") -WindowStyle Hidden' in installer

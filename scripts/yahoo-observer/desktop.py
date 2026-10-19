"""Reusable Windows desktop observer. No inbound service or Yahoo credentials."""

import argparse
import base64
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, Request, build_opener, ProxyHandler
import ssl

import observer
from picks import CandidateHistory, DIRTY_EXPRESSION, expression, parse

FOLDER = Path(os.environ.get("LOCALAPPDATA", ".")) / "CourtIQ" / "Observer"
CONFIG = FOLDER / "connection.json"
BASE = "/api/v2/draft/observer-connection"
logger = logging.getLogger("court_iq_desktop")


def configure_logging():
    FOLDER.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        FOLDER / "observer.log", maxBytes=262144, backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def relaunch_windowless(arguments):
    if Path(sys.executable).name.lower() != "python.exe":
        return False
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise OSError("Windowless Python is missing; update Court IQ Observer installation")
    subprocess.Popen(
        [str(pythonw), str(Path(__file__).resolve()), *arguments],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **observer.hidden_process_options(),
    )
    return True

METADATA_EXPRESSION = r"""(() => {
if (location.protocol !== 'https:' || location.hostname !== 'basketball.fantasysports.yahoo.com'
    || !/^\/draftclient\/nba\/\d+\/\d+\/?$/.test(location.pathname)) return {};
const teams=[...document.querySelectorAll('.ys-team[data-id]')];
const slots=teams.map(e=>Number(e.getAttribute('data-id')));
const unique=[...new Set(slots)].sort((a,b)=>a-b);
const count=unique.length>=2 && unique.every((s,i)=>s===i+1) ? unique.length : null;
const mine=teams.filter(e=>[...e.querySelectorAll('*')].some(
  n=>!n.children.length && /^(?:You|YOU)$/.test(n.textContent.trim())));
const slot=mine.length===1 ? Number(mine[0].getAttribute('data-id')) : null;
const headings=[...document.querySelectorAll('h1,h2,h3,h4')].map(e=>e.textContent.trim());
const roster=headings.map(t=>t.match(/^YOUR TEAM\s*\(\d+\s*\/\s*(\d+)\)$/i)).filter(Boolean);
return {total_teams:count, user_slot:slot, rounds:roster.length===1 ? Number(roster[0][1]) : null};
})()"""


def protect(data, decrypt=False):
    """DPAPI current-Windows-user encryption, not portable credential storage."""
    if os.name != "nt":
        raise ValueError("Windows is required")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    crypt.CryptProtectData.argtypes = [
        ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob),
    ]
    crypt.CryptProtectData.restype = wintypes.BOOL
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob),
    ]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "Court IQ Observer", None, None, None, 1,
                                   ctypes.byref(destination))
    if not ok:
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel.LocalFree(destination.data)


def validate_origin(origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Use only the trusted Court IQ HTTPS origin")
    return origin.rstrip("/")


class API:
    def __init__(self, config):
        self.origin = validate_origin(config["origin"])
        self.secret = protect(base64.b64decode(config["credential"]), decrypt=True).decode()
        ctx = ssl.create_default_context(cafile=config.get("ca_file") or None)
        self.http = build_opener(ProxyHandler({}), observer.NoRedirect(), HTTPSHandler(context=ctx))

    def call(self, path, body=None):
        req = Request(self.origin + BASE + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"X-Court-IQ-Observer": self.secret, "Content-Type": "application/json"})
        with self.http.open(req, timeout=120) as response:
            return json.loads(response.read(2_000_000))


def setup():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("Install Court IQ Yahoo Observer")
    values = {}
    existing = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    for key, label, default, mask in [
        ("origin", "Court IQ HTTPS address", existing.get("origin", "https://192.168.0.85:18002"), ""),
        ("secret", "Dedicated Court IQ credential (one time; not Yahoo)", "", "*"),
        ("ca_file", "Trusted Court IQ root certificate (optional)", existing.get("ca_file", ""), ""),
    ]:
        tk.Label(root, text=label).pack(anchor="w", padx=18, pady=4)
        values[key] = tk.StringVar(value=default)
        tk.Entry(root, textvariable=values[key], show=mask, width=65).pack(padx=18)
    tk.Button(root, text="Choose trusted certificate", command=lambda: values["ca_file"].set(
        filedialog.askopenfilename(filetypes=[("Certificates", "*.crt *.pem"), ("All", "*")])
    )).pack(pady=5)

    def save():
        try:
            secret = values["secret"].get()
            encrypted = (
                base64.b64encode(protect(secret.encode())).decode()
                if secret else existing.get("credential")
            )
            if not encrypted or (secret and len(secret) < 43):
                raise ValueError("Enter the dedicated high-entropy Court IQ observer credential")
            config = {
                "origin": validate_origin(values["origin"].get()),
                "credential": encrypted, "ca_file": values["ca_file"].get(), "port": 9222,
            }
            api = API(config)
            api.call("/agent")
            ensure_chrome(config["port"])
            code = secrets.token_urlsafe(24)
            api.call("/pairing", {"code": code})
            FOLDER.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(config), encoding="utf-8")
            values["secret"].set("")
            # Pairing code is short-lived, single-use, distinct from the stored credential.
            dialog = tk.Toplevel(root)
            dialog.title("Pair Court IQ once")
            tk.Label(dialog, text="Open Court IQ → Connect to Yahoo Draft → Pair observer.\n"
                     "Paste this one-time pairing code there (expires in 10 minutes).").pack(padx=18, pady=12)
            entry = tk.Entry(dialog, width=45)
            entry.insert(0, code)
            entry.configure(state="readonly")
            entry.pack(padx=18)
            tk.Button(dialog, text="Copy pairing code", command=lambda: (
                root.clipboard_clear(), root.clipboard_append(code)
            )).pack(pady=10)
            tk.Button(dialog, text="Finish", command=root.destroy).pack(pady=10)
        except (OSError, ValueError, subprocess.SubprocessError):
            messagebox.showerror("Setup needs attention",
                "Could not verify the trusted HTTPS connection, credential, or loopback Chrome.\n"
                "Check the entered settings and certificate. No TLS bypass or firewall change was made.")

    tk.Button(root, text="Verify and install connection", command=save).pack(pady=18)
    root.mainloop()
    return CONFIG.exists()


def ensure_chrome(port):
    try:
        observer.verify_windows_listener(port)
    except ConnectionError:
        subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-File",
            str(Path(__file__).with_name("Launch-YahooDraftChrome.ps1")), "-Port", str(port),
        ], capture_output=True, timeout=30, check=True,
           **observer.hidden_process_options())
        observer.verify_windows_listener(port)
    with observer.HTTP.open(f"http://127.0.0.1:{port}/json/version", timeout=3) as response:
        version = json.loads(response.read(16384))
    if not isinstance(version, dict) or "Browser" not in version or "Protocol-Version" not in version:
        raise ValueError("The loopback listener is not Chrome CDP")


def run():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    api, cdp, active_id, target_id = API(config), None, None, None
    history = CandidateHistory()
    next_job = next_read = next_listener = 0
    job = None
    stopped = None
    generation = 0
    while True:
        try:
            if time.monotonic() >= next_job:
                job = api.call("/agent")["connection"]
                next_job = time.monotonic() + 2
                if not job and cdp:
                    cdp.close()
                    cdp, target_id, active_id = None, None, None
                    history = CandidateHistory()
                if job and (
                    active_id != job["id"]
                    or generation != job.get("request_generation", 0)
                ):
                    if cdp:
                        cdp.close()
                    cdp, target_id = None, None
                    active_id, history, stopped = job["id"], CandidateHistory(), None
                    generation = job.get("request_generation", 0)
            if not job or stopped == active_id or job["status"] in {"DRAFT ENDED", "CONFLICT"}:
                time.sleep(1)
                continue
            if time.monotonic() >= next_listener:
                observer.verify_windows_listener(config["port"])
                next_listener = time.monotonic() + 10
            if cdp is None:
                targets = observer.get_targets(config["port"], room_path=job["room_path"])
                if len(targets) != 1:
                    api.call(f"/{active_id}/snapshot", {"state": "RECONNECTING"})
                    time.sleep(2)
                    continue
                cdp = observer.CDP(observer.loopback_websocket(
                    targets[0]["webSocketDebuggerUrl"], config["port"]))
                target_id = targets[0]["id"]
                next_read = 0
            if time.monotonic() < next_read and not cdp.read(DIRTY_EXPRESSION):
                time.sleep(0.25)
                continue
            if cdp.read("location.pathname").rstrip("/") != job["room_path"]:
                raise ConnectionError("Target is not the requested room")
            snapshot = cdp.read(expression())
            if isinstance(snapshot, dict) and snapshot.get("error") in {
                "not_draft_document", "picks_control_not_unique",
                "history_container_not_visible_or_not_narrow",
            }:
                opened = cdp.read(observer.OPEN_PICKS_EXPRESSION)
                if not isinstance(opened, dict) or not opened.get("opened_read_only_picks_tab"):
                    raise ConnectionError("Picks not ready")
                time.sleep(0.5)
                snapshot = cdp.read(expression())
            metadata = cdp.read(METADATA_EXPRESSION)
            # Before pick 1 an evidenced parser may report no rows; do not invent a pick.
            if isinstance(snapshot, dict) and snapshot.get("error") == "no_numbered_pick_rows":
                api.call(f"/{active_id}/snapshot", {"state": "NEEDS ATTENTION", **metadata})
                next_read = time.monotonic() + 2
                continue
            candidates, gaps = parse(snapshot)
            if gaps or candidates[0]["overall_pick"] != 1:
                raise ValueError("Complete history from pick 1 is required")
            fresh = history.check(candidates)
            parsed_at = time.time() * 1000
            changed = snapshot.get("changed_at")
            observed = observer.datetime.now(observer.timezone.utc).isoformat()
            body = {
                "state": "CONNECTED", **metadata,
                "picks": [{**p, "source": "yahoo_mock_browser", "observed_at": observed} for p in candidates],
            }
            if fresh and isinstance(changed, (int, float)):
                body["latency_ms"] = max(0, parsed_at-changed)
            api.call(f"/{active_id}/snapshot", body)
            history.accept(candidates)
            next_read = time.monotonic() + 10
        except HTTPError as error:
            logger.warning("Observer delivery failed (HTTP %s)", error.code)
            if error.code in {401, 403}:
                raise RuntimeError("Observer authorization unavailable; reopen one-time setup") from None
            if error.code in {409, 422}:
                stopped = active_id
            time.sleep(3)
        except ValueError as error:
            logger.warning("Observer source requires attention (%s)", type(error).__name__)
            if active_id:
                try:
                    api.call(f"/{active_id}/snapshot", {
                        "state": "CONFLICT" if str(error) == "previous_pick_changed_or_disappeared" else "NEEDS ATTENTION",
                    })
                except HTTPError as error:
                    # The server may already have latched conflict; never overwrite it.
                    if error.code not in {409, 422}:
                        raise RuntimeError("Court IQ status delivery unavailable") from None
            stopped = active_id
        except (OSError, subprocess.SubprocessError) as error:
            logger.warning("Observer reconnecting (%s)", type(error).__name__)
            if cdp:
                cdp.close()
            cdp, target_id = None, None
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--diagnostic", action="store_true", help="Explicit foreground diagnostic launch")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Install on the Windows computer running Yahoo Chrome")
    try:
        if not args.diagnostic and relaunch_windowless(sys.argv[1:]):
            return
        configure_logging()
        logger.info("Observer starting; windowless normal launch")
        if args.setup or not CONFIG.exists():
            if not setup():
                return
        ensure_chrome(json.loads(CONFIG.read_text())["port"])
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel.CreateMutexW(None, False, "Local\\CourtIQYahooObserver")
        if not handle:
            raise OSError("Cannot acquire desktop observer lock")
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
            return
        run()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        logger.error("Observer stopped; setup required (%s)", type(error).__name__)
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Court IQ Observer unavailable",
                             "Open Court IQ Observer Setup to verify the saved connection.\n"
                             "No Yahoo selections or production draft writes were made.")
        root.destroy()


if __name__ == "__main__":
    main()

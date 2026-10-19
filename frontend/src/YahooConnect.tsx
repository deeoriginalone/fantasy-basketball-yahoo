import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sanitizeYahooDraftUrl } from "./yahooConnection.js";

export type Connection = {
  id?: string;
  paired?: boolean;
  mode?: "mock" | "live";
  status: string;
  user_slot?: number;
  total_teams?: number;
  rounds?: number;
  yahoo_through?: number;
  court_iq_through?: number;
  draft_room_path?: string;
  target_detected?: boolean;
};
const base = "/api/v2/draft/observer-connection";

async function call(path: string, method = "GET", body?: unknown): Promise<Connection> {
  const response = await fetch(base + path, {
    method, credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  if (response.status === 401) return { status: "PAIR OBSERVER", paired: false };
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Yahoo connection needs attention.");
  }
  return payload;
}

export function YahooConnect({ inRoom = false }: { inRoom?: boolean }) {
  const navigate = useNavigate();
  const [connection, setConnection] = useState<Connection>({ status: "CONNECTING" });
  const [roomPath, setRoomPath] = useState("");
  const [chooseMode, setChooseMode] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await call("");
        if (!cancelled) { setConnection(next); setError(""); }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Observer unavailable.");
      } finally {
        if (!cancelled) timer = setTimeout(() => void refresh(), 2000);
      }
    };
    void refresh();
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);

  useEffect(() => {
    if (waiting && connection.draft_room_path) {
      setWaiting(false);
      navigate(connection.draft_room_path);
    }
  }, [waiting, connection.draft_room_path, navigate]);

  function acceptUrl(value: string) {
    try {
      setRoomPath(sanitizeYahooDraftUrl(value));
      setError("");
    } catch {
      setRoomPath("");
      setError("Paste a valid HTTPS Yahoo Basketball draft-room URL.");
    }
  }

  async function act(action: () => Promise<Connection>) {
    setBusy(true);
    try { setConnection(await action()); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Connection failed."); }
    finally { setBusy(false); }
  }

  function start(mode: "mock" | "live") {
    setChooseMode(false);
    void act(async () => {
      const result = await call("", "POST", { room_path: roomPath, mode });
      if (result.id) setWaiting(true);
      return result;
    });
  }

  return <section className="panel yahoo-desk" aria-label="Yahoo draft connection">
    <YahooConnectionStatus connection={connection} />
    {connection.paired === true && connection.id && <button className="button button-quiet"
      type="button" disabled={busy} onClick={() => {
        setWaiting(false); setChooseMode(false);
        void act(() => call(`/${connection.id}/stop`, "POST"));
      }}>STOP TRACKING</button>}
    {error && <p role="alert">{error}</p>}
    {connection.paired === false ? <>
      <h2>Yahoo Observer Setup</h2>
      <p>Install once on your Yahoo Windows PC, then pair using the setup window’s code.</p>
      <a className="button button-primary" href={`${base}/installer`}>INSTALL OBSERVER</a>
      <form onSubmit={event => {
        event.preventDefault();
        const value = code;
        setCode("");
        void act(async () => {
          await call("/pair", "POST", { code: value });
          return call("");
        });
      }}>
        <label>One-time pairing code <input type="password" autoComplete="off" value={code}
          onChange={event => setCode(event.target.value)} /></label>
        <button className="button button-quiet" type="submit" disabled={busy || !code}>PAIR</button>
      </form>
    </> : connection.paired === true && !inRoom && <form onSubmit={event => {
      event.preventDefault();
      setChooseMode(true);
    }}>
      <label className="field">Yahoo draft URL <input ref={inputRef} type="text" autoComplete="off" autoFocus
        value={roomPath ? `https://basketball.fantasysports.yahoo.com${roomPath}` : ""}
        placeholder="Paste Yahoo draft URL"
        onPaste={event => { event.preventDefault(); acceptUrl(event.clipboardData.getData("text")); }}
        onChange={event => acceptUrl(event.target.value)} /></label>
      <button className="button button-primary" type="submit" disabled={busy || !roomPath || connection.paired !== true}>
        {busy ? "Connecting to Yahoo..." : "CONNECT TO YAHOO DRAFT"}
      </button>
      {chooseMode && <fieldset className="connection-question">
        <legend>Is this a Yahoo mock or your real draft?</legend>
        <p>Yahoo room URLs do not establish this safely. Real draft browser input remains observe-only.</p>
        <button className="button button-quiet" type="button" disabled={busy} onClick={() => start("mock")}>MOCK</button>
        <button className="button button-quiet" type="button" disabled={busy} onClick={() => start("live")}>REAL DRAFT</button>
      </fieldset>}
    </form>}
    <YahooSlotQuestion connection={connection} busy={busy}
      selectSlot={slot => void act(() => call(`/${connection.id}/slot`, "PUT", { slot }))} />
    {connection.status === "NEEDS ATTENTION" && connection.user_slot && <p role="status">
      {!connection.rounds ? "Needs attention: Yahoo’s total draft rounds could not be verified. Connection is paused; no rounds will be guessed."
        : "Needs attention: keep Yahoo Picks visible so complete draft history can be verified."}
    </p>}
    {connection.draft_room_path && !inRoom && <button type="button"
      onClick={() => navigate(connection.draft_room_path!)}>Open Yahoo Mock Practice</button>}
    {connection.status === "DRAFT ENDED" && <div>
      <h2>{connection.mode === "mock" ? "YAHOO MOCK COMPLETE" : "YAHOO DRAFT COMPLETE"}</h2>
      <button className="button button-primary" type="button" onClick={() => {
        setRoomPath(""); setChooseMode(false); setWaiting(false);
        if (inRoom) navigate("/"); else inputRef.current?.focus();
      }}>CONNECT ANOTHER MOCK</button>
    </div>}
    <details className="connection-diagnostics">
      <summary>Advanced · Connection diagnostics</summary>
      <p>Room match: {connection.target_detected ? "detected" : "not confirmed"} · Slot: {connection.user_slot ?? "unknown"}
        {" · "}Yahoo through: {connection.yahoo_through ?? "unknown"}
        {" · "}Court IQ through: {connection.court_iq_through ?? "unknown"}
        {" · "}Source: Browser · State: {connection.status}</p>
      <p>Teams: {connection.total_teams ?? "unknown"} · Rounds: {connection.rounds ?? "unknown"}</p>
      <p>URL query/auth/fragment values are discarded. Live browser input is observe-only.
        Official Yahoo draftresults, Sync Now and Quick Record are unchanged.</p>
    </details>
  </section>;
}

export function YahooSlotQuestion({ connection, busy, selectSlot }: {
  connection: Connection; busy: boolean; selectSlot: (slot: number) => void;
}) {
  if (connection.status !== "NEEDS ATTENTION" || connection.user_slot || !connection.id) return null;
  return <fieldset className="connection-question">
    <legend>What is your draft position?</legend>
    <div className="slot-choices">{Array.from({ length: connection.total_teams ?? 12 }, (_, i) => i + 1).map(slot =>
      <button className="button button-quiet" type="button" key={slot} disabled={busy}
        aria-label={`Draft position ${slot}`} onClick={() => selectSlot(slot)}>{slot}</button>)}</div>
  </fieldset>;
}

export function YahooConnectionStatus({ connection }: { connection: Connection }) {
  const labels: Record<string, string> = {
    "PAIR OBSERVER": "Observer setup required", CONNECTING: "Connecting to Yahoo...",
    "SOURCE UNAVAILABLE": "Observer ready", RECONNECTING: "Reconnecting...",
    "NEEDS ATTENTION": "Needs attention", CONFLICT: "Needs attention: conflicting draft history",
    "CATCHING UP": "Catching up...", "YOUR TURN": "Your turn", "OBSERVE ONLY": "Yahoo connected · Live browser input is observe-only",
    "DRAFT ENDED": "Draft complete",
  };
  const text = connection.paired === false ? "Observer setup required"
    : connection.status === "SYNCED" ? `Synced through pick ${connection.court_iq_through ?? "—"}`
    : labels[connection.status] ?? "Yahoo connected";
  return <p className="observer-readiness" role="status">{text}</p>;
}

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Activity,
  ArrowDownWideNarrow,
  ArrowLeft,
  ArrowRight,
  ArrowUpNarrowWide,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  ExternalLink,
  Filter,
  Flame,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  SkipForward,
  Sparkles,
  Target,
  Undo2,
  X,
} from "lucide-react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "./api";
import { YahooConnect } from "./YahooConnect";
import { createRoomPoller } from "./roomPolling.js";
import type { RoomPoller } from "./roomPolling.js";
import { findQuickMatches, moveQuickSelection } from "./quickRecord.js";
import { createBackoffPoller } from "./draftSyncPolling.js";
import type {
  BoardPlayer,
  DraftBoard,
  DraftMockBatch,
  DraftMode,
  DraftPick,
  DraftSession,
  DraftSyncResult,
  DraftSyncState,
  League,
  MockOrderPreview,
  PlayerIdentity,
  RosterImpact,
  YahooStatusEvidence,
  TargetStatus,
} from "./types";

const modes: DraftMode[] = ["balanced", "upside", "safe"];
const targetStatuses: TargetStatus[] = ["target", "priority", "watch", "avoid"];
const DEFAULT_LIVE_DRAFT_POLL_INTERVAL_MS = 60_000;
const MAX_LIVE_DRAFT_POLL_INTERVAL_MS = 5 * 60_000;
const configuredLiveDraftPollIntervalMs = Number(import.meta.env.VITE_LIVE_DRAFT_POLL_INTERVAL_MS);
const liveDraftPollIntervalMs = Number.isSafeInteger(configuredLiveDraftPollIntervalMs)
  && configuredLiveDraftPollIntervalMs >= 1_000
  ? configuredLiveDraftPollIntervalMs
  : DEFAULT_LIVE_DRAFT_POLL_INTERVAL_MS;

interface RoomPollValue {
  session: { version: number };
  board: DraftBoard;
}

function BrandBar({ right }: { right?: React.ReactNode }) {
  return (
    <header className="brandbar">
      <Link className="brand" to="/" aria-label="Court IQ draft desk">
        <span className="brand-mark"><Activity size={19} strokeWidth={2.5} /></span>
        <span className="brand-name">COURT<span>IQ</span></span>
      </Link>
      <div className="brandbar-right">{right}</div>
    </header>
  );
}

function ErrorLine({ children }: { children: React.ReactNode }) {
  return <div className="notice notice-error" role="alert"><CircleAlert size={17} />{children}</div>;
}

function SetupPage() {
  const navigate = useNavigate();
  const legacySetupRef = useRef<HTMLDetailsElement>(null);
  const now = new Date().getFullYear();
  const [leagues, setLeagues] = useState<League[]>([]);
  const [sessions, setSessions] = useState<DraftSession[]>([]);
  const [mockSessions, setMockSessions] = useState<DraftSession[]>([]);
  const [mockBatches, setMockBatches] = useState<DraftMockBatch[]>([]);
  const [leagueKey, setLeagueKey] = useState("");
  const [managerTeamKey, setManagerTeamKey] = useState("");
  const [draftPosition, setDraftPosition] = useState<number | null>(null);
  const [teamSlots, setTeamSlots] = useState<Record<string, number | "">>({});
  const [season, setSeason] = useState(`${now}-${String((now + 1) % 100).padStart(2, "0")}`);
  const [rounds, setRounds] = useState(13);
  const [mode, setMode] = useState<DraftMode>("balanced");
  const [draftSource, setDraftSource] = useState<"manual" | "internal_mock" | null>(null);
  const [mockCount, setMockCount] = useState(1);
  const [mockAggressiveness, setMockAggressiveness] = useState(0.5);
  const [mockSeed, setMockSeed] = useState("");
  const [mockOrderPreview, setMockOrderPreview] = useState<MockOrderPreview | null>(null);
  const [mockOrderPreviewKey, setMockOrderPreviewKey] = useState("");
  const [mockSyncRehearsal, setMockSyncRehearsal] = useState(false);
  const [mockRunSelections, setMockRunSelections] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refreshWorkspace() {
    const [nextLeagues, nextSessions, nextMocks, nextBatches] = await Promise.all([
      api.getLeagues(),
      api.getSessions(),
      api.getMockSessions(),
      api.getMockBatches(),
    ]);
    setLeagues(nextLeagues);
    setSessions(nextSessions);
    setMockSessions(nextMocks);
    setMockBatches(nextBatches);
    setLeagueKey((current) => current || nextLeagues[0]?.league_key || "");
  }

  useEffect(() => {
    let active = true;
    Promise.all([api.getLeagues(), api.getSessions(), api.getMockSessions(), api.getMockBatches()])
      .then(([nextLeagues, nextSessions, nextMocks, nextBatches]) => {
        if (!active) return;
        setLeagues(nextLeagues);
        setSessions(nextSessions);
        setMockSessions(nextMocks);
        setMockBatches(nextBatches);
        setLeagueKey(nextLeagues[0]?.league_key || "");
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load draft setup.");
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!mockBatches.some((batch) => batch.status === "running")) return;
    const timer = window.setInterval(() => {
      void api.getMockBatches().then(setMockBatches).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [mockBatches]);

  const league = leagues.find((item) => item.league_key === leagueKey);
  const mappingComplete = Boolean(league)
    && league!.teams.every((team) => typeof teamSlots[team.team_key] === "number")
    && new Set(Object.values(teamSlots).filter((slot): slot is number => typeof slot === "number")).size === league!.teams.length;
  const managerSlot = typeof teamSlots[managerTeamKey] === "number" ? teamSlots[managerTeamKey] : null;
  const validPartialMapping = Boolean(league)
    && Object.entries(teamSlots).every(([teamKey, slot]) =>
      league!.teams.some((team) => team.team_key === teamKey)
      && (slot === "" || (Number.isInteger(slot) && slot >= 1 && slot <= league!.teams.length)))
    && new Set(Object.values(teamSlots).filter((slot): slot is number => typeof slot === "number")).size
      === Object.values(teamSlots).filter((slot): slot is number => typeof slot === "number").length;
  const mockPreviewKey = `${leagueKey}|${managerTeamKey}|${draftPosition ?? ""}|${mockSeed}`;
  const mockPreviewCurrent = Boolean(mockOrderPreview && mockOrderPreviewKey === mockPreviewKey);
  const setupCoreValid = Boolean(league && managerTeamKey && /^\d{4}-\d{2}$/.test(season)
    && Number.isInteger(rounds) && rounds > 0 && rounds <= 100);
  const mockSeedValid = mockSeed === ""
    || (Number.isSafeInteger(Number(mockSeed)) && Number(mockSeed) >= 0);
  const canCreate = draftSource === "manual"
    ? setupCoreValid && validPartialMapping
      && (draftPosition === null || (managerSlot === null || managerSlot === draftPosition))
    : draftSource === "internal_mock"
      ? setupCoreValid && mockSeedValid && draftPosition !== null && mockPreviewCurrent
      : false;

  function changeLeague(value: string) {
    setLeagueKey(value);
    setManagerTeamKey("");
    setDraftPosition(null);
    setTeamSlots({});
    setMockOrderPreview(null);
    setError("");
  }

  function changeManagerTeam(value: string) {
    setManagerTeamKey(value);
    setDraftPosition(null);
    setTeamSlots({});
    setMockOrderPreview(null);
  }

  function changeDraftPosition(value: string) {
    const nextPosition = value ? Number(value) : null;
    setDraftPosition(nextPosition);
    setMockOrderPreview(null);
    if (draftSource === "manual" && managerTeamKey) {
      setTeamSlots((current) => {
        const next = { ...current };
        if (nextPosition === null) delete next[managerTeamKey];
        else next[managerTeamKey] = nextPosition;
        return next;
      });
    }
  }

  function setTeamSlot(teamKey: string, value: string) {
    const nextSlot = value ? Number(value) : "";
    setTeamSlots((current) => ({ ...current, [teamKey]: nextSlot }));
    if (teamKey === managerTeamKey) {
      setDraftPosition(typeof nextSlot === "number" ? nextSlot : null);
    }
    setMockOrderPreview(null);
  }

  async function previewMockDraftOrder() {
    if (!league || !managerTeamKey || draftPosition === null) return;
    setBusy(true);
    setError("");
    try {
      const seed = mockSeed
        ? Number(mockSeed)
        : crypto.getRandomValues(new Uint32Array(1))[0];
      const preview = await api.previewMockOrder({
        league_key: league.league_key,
        manager_team_key: managerTeamKey,
        draft_position: draftPosition,
        total_teams: league.teams.length,
        seed,
      });
      setMockOrderPreview(preview);
      setMockOrderPreviewKey(mockPreviewKey);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Mock order preview could not be generated.");
    } finally {
      setBusy(false);
    }
  }

  async function syncLeagues() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api.importLeagues();
      await refreshWorkspace();
      setMessage("Yahoo leagues refreshed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Yahoo league import failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (!draftSource) {
      setError("Choose Mock Draft or Live Draft before creating a room.");
      return;
    }
    if (!league || !managerTeamKey || !canCreate) {
      setError(draftSource === "manual"
        ? "Choose a manager team and provide a valid manager position or leave it unknown."
        : "Choose a manager team and position, then preview the seeded mock order.");
      return;
    }
    setBusy(true);
    try {
      setStep("Refreshing Yahoo player pool");
      await api.importPlayers(league.league_key);
      setStep("Building league draft metrics");
      await api.buildMetrics(league.league_key, season);
      const sessionConfig = {
        league_key: league.league_key,
        season,
        manager_team_key: managerTeamKey,
        draft_position: draftPosition!,
        total_teams: league.teams.length,
        rounds,
        mode,
      };
      const liveTeamSlots: Record<string, number> = {};
      for (const team of league.teams) {
        const slot = teamSlots[team.team_key];
        if (typeof slot === "number") liveTeamSlots[team.team_key] = slot;
      }
      if (draftSource === "internal_mock" && mockCount > 1) {
        setStep(`Creating ${mockCount} internal mock drafts`);
        const response = await api.createMockBatch({
          ...sessionConfig,
          count: mockCount,
          aggressiveness: mockAggressiveness,
          opponent_order_seed: mockOrderPreview!.order_seed,
          ...(mockSeed ? { seed: Number(mockSeed) } : {}),
        });
        setMockBatches((current) => [response.batch, ...current]);
        await api.runMockBatch(response.batch.batch_id);
        navigate(`/draft/${response.session_ids[0]}`);
      } else if (draftSource === "internal_mock") {
        setStep("Creating your internal mock draft");
        const response = await api.createMockSession({
          ...sessionConfig,
          aggressiveness: mockAggressiveness,
          opponent_order_seed: mockOrderPreview!.order_seed,
          live_sync_rehearsal: mockSyncRehearsal,
          ...(mockSeed ? { seed: Number(mockSeed) } : {}),
        });
        navigate(`/draft/${response.state.session_id}`);
      } else {
        setStep("Creating your live draft room");
        const response = await api.createLiveSession({ ...sessionConfig, team_slots: liveTeamSlots });
        navigate(`/draft/${response.state.session_id}`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Draft session could not be created.");
    } finally {
      setBusy(false);
      setStep("");
    }
  }

  async function deleteSavedMock(mock: DraftSession) {
    if (!window.confirm("Delete this mock draft and its picks? This cannot be undone.")) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteMockSession(mock.session_id);
      setMockSessions(current => current.filter(item => item.session_id !== mock.session_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Mock draft could not be deleted.");
    } finally {
      setBusy(false);
    }
  }

  async function runMockBatch(batch: DraftMockBatch) {
    setBusy(true);
    setError("");
    try {
      await api.runMockBatch(batch.batch_id);
      setMockBatches((current) => current.map((item) => item.batch_id === batch.batch_id
        ? { ...item, status: "running" }
        : item));
      navigate(`/draft/${batch.session_ids[0]}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The mock batch could not start.");
    } finally {
      setBusy(false);
    }
  }

  function openMockBatchRun(batch: DraftMockBatch) {
    const runIndex = Math.min(
      batch.requested_runs - 1,
      Math.max(0, (mockRunSelections[batch.batch_id] ?? 1) - 1),
    );
    const run = batch.runs
      .filter((item) => item.run_index === runIndex)
      .sort((left, right) => right.attempt_index - left.attempt_index)[0];
    if (run) navigate(`/draft/${run.session_id}`);
  }

  const leagueNameByKey = Object.fromEntries(leagues.map((item) => [item.league_key, item.league_name]));
  const teamName = (leagueKeyValue: string, teamKey: string) => {
    const foundLeague = leagues.find((item) => item.league_key === leagueKeyValue);
    return foundLeague?.teams.find((team) => team.team_key === teamKey)?.team_name ?? teamKey;
  };

  return (
    <div className="app-shell">
      <BrandBar right={<span className="top-label"><span className="status-dot" /> DRAFT DESK</span>} />
      <main className="setup-page">
        <div className="page-intro">
          <div>
            <p className="eyebrow">DRAFT DESK</p>
            <h1>READY FOR YAHOO</h1>
          </div>
        </div>

        {error && <ErrorLine>{error}</ErrorLine>}
        {message && <div className="notice notice-success" role="status"><Check size={17} />{message}</div>}
        <YahooConnect />
        <p className="internal-practice-link">Practice without Yahoo{" · "}
          <button className="text-button" type="button" onClick={() => {
            setDraftSource("internal_mock");
            if (legacySetupRef.current) {
              legacySetupRef.current.open = true;
              legacySetupRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
              legacySetupRef.current.focus();
            }
          }}>Start Internal Mock</button>
        </p>

        {loading ? (
          <div className="loading-block"><LoaderCircle className="spin" /> Loading your draft workspace</div>
        ) : (
          <div className="desk-secondary">
            <details className="desk-disclosure" ref={legacySetupRef} tabIndex={-1}>
              <summary>Advanced</summary>
              <h2>Manual / legacy setup</h2>
              <button className="button button-quiet" type="button" onClick={syncLeagues} disabled={busy}>
                <RefreshCw size={16} className={busy ? "spin" : ""} /> Refresh leagues
              </button>
            <section className="setup-main">
              {leagues.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon"><ExternalLink size={22} /></div>
                  <h2>Connect a Yahoo league</h2>
                  <p>No imported leagues are available yet. Authorize Yahoo, then refresh this page.</p>
                  <a className="button button-primary" href="/api/v1/yahoo/oauth/authorize">
                    <ExternalLink size={16} /> Connect Yahoo
                  </a>
                </div>
              ) : (
                <form onSubmit={createSession}>
                  <section className="setup-section">
                    <div className="section-heading"><span className="step-index">00</span><div><h2>Choose a draft room</h2><p>Select the session type before configuring your Yahoo league.</p></div></div>
                    <div className="draft-mode-cards" role="group" aria-label="Draft session type">
                      <button
                        className={`draft-mode-card mock-mode-card ${draftSource === "internal_mock" ? "selected" : ""}`}
                        type="button"
                        aria-pressed={draftSource === "internal_mock"}
                        onClick={() => setDraftSource("internal_mock")}
                      >
                        <span className="eyebrow">MOCK LIVE DRAFT</span>
                        <strong>Practice the complete draft before draft night.</strong>
                        <span>Simulated opponents, the same player board and roster-aware recommendations. Mock picks stay separate from live sessions and Yahoo rosters.</span>
                        <span className="draft-mode-cta">Start Mock Draft <ArrowRight size={15} /></span>
                      </button>
                      <button
                        className={`draft-mode-card live-mode-card ${draftSource === "manual" ? "selected" : ""}`}
                        type="button"
                        aria-pressed={draftSource === "manual"}
                        onClick={() => setDraftSource("manual")}
                      >
                        <span className="eyebrow">LIVE DRAFT</span>
                        <strong>Track the real Yahoo draft and receive recommendations as picks happen.</strong>
                        <span>Start a live tracking room, or resume one from the saved rooms.</span>
                        <span className="draft-mode-cta">Start / Resume Live Draft <ArrowRight size={15} /></span>
                      </button>
                    </div>
                    {draftSource === "manual" && <p className="setup-live-note">Yahoo does not push picks in real time. This room polls draftresults when available; manual recording remains supported.</p>}
                    {draftSource === "internal_mock" && <div className="form-grid mock-config-grid">
                      <label className="field"><span>Mock drafts</span><div className="select-wrap"><select value={mockCount} onChange={(event) => setMockCount(Number(event.target.value))}>{[1, 10, 50, 100, 500].map((count) => <option key={count} value={count}>{count === 1 ? "Single draft" : `${count} drafts`}</option>)}</select><ChevronDown size={16} /></div></label>
                      <label className="field"><span>Opponent aggressiveness · {mockAggressiveness.toFixed(1)}</span><input type="range" min="0" max="1" step="0.1" value={mockAggressiveness} onChange={(event) => setMockAggressiveness(Number(event.target.value))} /></label>
                      <label className="field"><span>Seed (optional)</span><input type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" value={mockSeed} onChange={(event) => { setMockSeed(event.target.value); setMockOrderPreview(null); }} placeholder="Random" /></label>
                      {mockCount === 1 && <label className="field checkbox-field"><span>Sync rehearsal</span><span><input type="checkbox" checked={mockSyncRehearsal} onChange={(event) => setMockSyncRehearsal(event.target.checked)} /> Exercise Yahoo-shaped source polling, delay, conflict and recovery controls.</span></label>}
                    </div>}
                  </section>
                  <section className="setup-section">
                    <div className="section-heading"><span className="step-index">01</span><div><h2>Choose your league</h2><p>Imported Yahoo league and season.</p></div></div>
                    <div className="form-grid">
                      <label className="field"><span>League</span><div className="select-wrap"><select value={leagueKey} onChange={(event) => changeLeague(event.target.value)} required>
                        <option value="">Select a league</option>
                        {leagues.map((item) => <option key={item.league_key} value={item.league_key}>{item.league_name}</option>)}
                      </select><ChevronDown size={16} /></div></label>
                      <label className="field"><span>Season</span><input value={season} onChange={(event) => setSeason(event.target.value)} pattern="\d{4}-\d{2}" required /></label>
                      <label className="field"><span>My team</span><div className="select-wrap"><select value={managerTeamKey} onChange={(event) => changeManagerTeam(event.target.value)} required disabled={!league}>
                        <option value="">Select your Yahoo team</option>
                        {league?.teams.map((team) => <option key={team.team_key} value={team.team_key}>{team.team_name || team.team_key}</option>)}
                      </select><ChevronDown size={16} /></div></label>
                      <label className="field"><span>Draft rounds</span><input type="number" min="1" max="100" value={rounds} onChange={(event) => setRounds(Number(event.target.value))} required /></label>
                      {draftSource && <div className="field"><label htmlFor="draft-position">{draftSource === "internal_mock" ? "Practice position" : "My draft position"}</label><div className="select-wrap"><select id="draft-position" value={draftPosition ?? ""} onChange={(event) => changeDraftPosition(event.target.value)} required={draftSource === "internal_mock"}>
                        {draftSource === "manual" && <option value="">Unknown until Yahoo reports it</option>}
                        {league?.teams.map((_, index) => index + 1).map((slot) => <option key={slot} value={slot}>Slot {slot}</option>)}
                      </select><ChevronDown size={16} /></div>{draftSource === "internal_mock" && <button className="text-button" type="button" onClick={() => {
                        if (!league) return;
                        const random = crypto.getRandomValues(new Uint32Array(1))[0];
                        changeDraftPosition((random % league.teams.length + 1).toString());
                      }}>Randomize my practice position</button>}</div>}
                    </div>
                  </section>

                  {league && draftSource === "manual" && <section className="setup-section setup-order">
                    <div className="section-heading"><span className="step-index">02</span><div><h2>Live draft order</h2><p>Yahoo’s first round fills the order progressively. Full opponent mapping is optional.</p></div></div>
                    <div className="order-summary">
                      <span>{mappingComplete ? <Check size={15} /> : <CircleAlert size={15} />}</span>
                      {mappingComplete
                        ? `Confirmed: ${league.teams.length} unique slots${managerSlot ? ` · your slot is ${managerSlot}` : ""}`
                        : `${Object.keys(teamSlots).filter((key) => typeof teamSlots[key] === "number").length} of ${league.teams.length} slots mapped${draftPosition === null ? " · your position can remain unknown" : ` · your position is ${draftPosition}`}`}
                    </div>
                    <details className="advanced-order-editor">
                      <summary>Advanced: manually map Yahoo teams to draft slots</summary>
                    <div className="slot-table">
                      <div className="slot-table-head"><span>YAHOO TEAM</span><span>DRAFT SLOT</span></div>
                      {league.teams.map((team) => {
                        const assignedElsewhere = new Set(Object.entries(teamSlots)
                          .filter(([key, value]) => key !== team.team_key && typeof value === "number")
                          .map(([, value]) => value));
                        return <label className={`slot-row ${team.team_key === managerTeamKey ? "is-manager" : ""}`} key={team.team_key}>
                          <span><span className="team-dot" />{team.team_name || team.team_key}{team.team_key === managerTeamKey && <em>YOU</em>}</span>
                          <span className="select-wrap slot-select"><select aria-label={`Draft slot for ${team.team_name || team.team_key}`} value={teamSlots[team.team_key] ?? ""} onChange={(event) => setTeamSlot(team.team_key, event.target.value)}>
                            <option value="">Unassigned</option>
                            {league.teams.map((_, index) => index + 1).map((slot) => <option key={slot} value={slot} disabled={assignedElsewhere.has(slot)}>Slot {slot}</option>)}
                          </select><ChevronDown size={15} /></span>
                        </label>;
                      })}
                    </div>
                    </details>
                  </section>}

                  {league && draftSource === "internal_mock" && <section className="setup-section setup-order">
                    <div className="section-heading"><span className="step-index">02</span><div><h2>Preview mock order</h2><p>Opponents are assigned reproducibly from the order seed; no manual team mapping is needed.</p></div></div>
                    <button className="button button-quiet" type="button" disabled={!managerTeamKey || draftPosition === null || busy} onClick={() => void previewMockDraftOrder()}>
                      <RefreshCw size={15} />{mockPreviewCurrent ? "Regenerate / preview order" : "Preview randomized order"}
                    </button>
                    {mockPreviewCurrent && mockOrderPreview && <div className="slot-table mock-order-preview">
                      <div className="slot-table-head"><span>DRAFT SLOT</span><span>YAHOO TEAM</span></div>
                      {Object.entries(mockOrderPreview.team_slots).sort((left, right) => left[1] - right[1]).map(([teamKey, slot]) => <div className={`slot-row ${teamKey === managerTeamKey ? "is-manager" : ""}`} key={teamKey}>
                        <span>Slot {slot}{teamKey === managerTeamKey && <em>YOU</em>}</span><span>{league.teams.find((team) => team.team_key === teamKey)?.team_name || teamKey}</span>
                      </div>)}
                      <div className="order-summary"><Check size={15} /> Seed {mockOrderPreview.order_seed} · {mockCount > 1 ? "first run preview" : "single draft order"}</div>
                    </div>}
                  </section>}

                  <section className="setup-section">
                    <div className="section-heading"><span className="step-index">03</span><div><h2>Choose a mode</h2><p>Changes utility adjustments only; backend owns all player decisions.</p></div></div>
                    <div className="mode-control" role="group" aria-label="Draft mode">
                      {modes.map((value) => <button type="button" key={value} className={mode === value ? "selected" : ""} aria-pressed={mode === value} onClick={() => setMode(value)}>{value}</button>)}
                    </div>
                  </section>
                  <div className="setup-submit">
                    <span>{step || (canCreate ? "Player pool and metrics refresh when you create the room." : draftSource === "internal_mock" ? "Choose your practice position and preview the randomized order." : "Choose your team; unknown Live positions can be filled when Yahoo reveals the first-round order.")}</span>
                    <button className="button button-primary" type="submit" disabled={!draftSource || !canCreate || busy}>
                      {busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
                      {busy ? "Preparing room" : draftSource === "internal_mock" ? `Start ${mockCount === 1 ? "Mock Draft" : `${mockCount} Mock Drafts`}` : "Start Live Draft"}
                    </button>
                  </div>
                </form>
              )}
            </section>
            </details>

            <details className="desk-disclosure recent-drafts">
              <summary>Recent Drafts</summary>
            <aside className="session-sidebar">
              <div className="sidebar-heading"><div><p className="eyebrow">PERSISTED ROOMS</p><h2>Resume a draft</h2></div><span className="count-pill">{sessions.length}</span></div>
              {sessions.length === 0 ? <p className="muted small-copy">Sessions appear here after you create a room.</p> : <div className="session-list">
                {sessions.map((session) => <Link className="session-link" to={`/draft/${session.session_id}`} key={session.session_id}>
                  <div className="session-link-top"><span className={`session-status ${session.status}`}>{session.status}</span><span>v{session.version}</span></div>
                  <strong>{leagueNameByKey[session.league_key] || session.league_key}</strong>
                  <span className="session-team">{teamName(session.league_key, session.manager_team_key)}</span>
                  <span className="session-link-bottom">Round {session.timing.current_round ?? "Done"} <span>·</span> Pick {session.timing.current_pick ?? "—"} <ArrowUpNarrowWide size={14} /></span>
                </Link>)}
              </div>}
              <div className="sidebar-heading mock-batches-heading"><div><p className="eyebrow">INTERNAL MOCKS</p><h2>Single drafts</h2></div><span className="count-pill">{mockSessions.length}</span></div>
              {mockSessions.length === 0 ? <p className="muted small-copy">No standalone mock drafts yet.</p> : <div className="session-list">
                {mockSessions.slice(0, 8).map((mock) => <div key={mock.session_id}>
                  <Link className="session-link" to={`/draft/${mock.session_id}`}>
                  <div className="session-link-top"><span className={`session-status ${mock.status}`}>{mock.status}</span><span>v{mock.version}</span></div>
                  <strong>{leagueNameByKey[mock.league_key] || mock.league_key}</strong>
                  <span className="session-team">{teamName(mock.league_key, mock.manager_team_key)} · slot {mock.draft_position}</span>
                  <span className="session-link-bottom">Round {mock.timing.current_round ?? "Done"} · Pick {mock.timing.current_pick ?? "—"}</span>
                </Link>
                  <button className="button button-danger" type="button" disabled={busy}
                    aria-label={`Delete mock ${leagueNameByKey[mock.league_key] || mock.league_key}`}
                    onClick={() => void deleteSavedMock(mock)}>Delete Mock</button>
                </div>)}
              </div>}
              <div className="sidebar-heading mock-batches-heading"><div><p className="eyebrow">INTERNAL MOCKS</p><h2>Mock batches</h2></div><span className="count-pill">{mockBatches.length}</span></div>
              {mockBatches.length === 0 ? <p className="muted small-copy">No internal mock batches yet.</p> : <div className="session-list">
                {mockBatches.slice(0, 8).map((batch) => <div className="session-link mock-batch-link" key={batch.batch_id}>
                  <div className="session-link-top"><span className={`session-status ${batch.status}`}>{batch.status}</span><span>{batch.completed_runs}/{batch.requested_runs}</span></div>
                  <strong>{leagueNameByKey[batch.league_key] || batch.league_key}</strong>
                  <span className="session-team">{teamName(batch.league_key, batch.manager_team_key)} · aggressiveness {batch.aggressiveness.toFixed(1)} · seed {batch.seed}</span>
                  <div className="mock-batch-actions">
                    <label className="mock-run-picker"><span>Run</span><input type="number" min="1" max={batch.requested_runs} value={mockRunSelections[batch.batch_id] ?? 1} onChange={(event) => setMockRunSelections((current) => ({ ...current, [batch.batch_id]: Number(event.target.value) }))} /></label>
                    <button className="button button-quiet" type="button" onClick={() => openMockBatchRun(batch)}>Open run</button>
                    {batch.status !== "completed" && <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockBatch(batch)}>Run / recover</button>}
                  </div>
                </div>)}
              </div>}
            </aside>
            </details>
          </div>
        )}
        <footer className="setup-footer"><ShieldCheck size={15} /> Draft actions are explicit and version-checked. No transactions are automated.</footer>
      </main>
    </div>
  );
}

function DraftRoomPage() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [board, setBoard] = useState<DraftBoard | null>(null);
  const [players, setPlayers] = useState<PlayerIdentity[]>([]);
  const [league, setLeague] = useState<League | null>(null);
  const [sortBy, setSortBy] = useState("decision");
  const [descending, setDescending] = useState(true);
  const [search, setSearch] = useState("");
  const [positionFilter, setPositionFilter] = useState("");
  const [targetFilter, setTargetFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [correcting, setCorrecting] = useState<DraftPick | null>(null);
  const [replacementId, setReplacementId] = useState("");
  const [replayVersion, setReplayVersion] = useState<number | null>(null);
  const [replaySelection, setReplaySelection] = useState(0);
  const [replayError, setReplayError] = useState("");
  const [syncState, setSyncState] = useState<DraftSyncState | null>(null);
  const [syncError, setSyncError] = useState("");
  const [orderDraft, setOrderDraft] = useState<Record<string, string>>({});
  const [orderUpdateBusy, setOrderUpdateBusy] = useState(false);
  const [quickSearch, setQuickSearch] = useState("");
  const [quickSelection, setQuickSelection] = useState(0);
  const [quickRecordPending, setQuickRecordPending] = useState(false);
  const quickRecordInputRef = useRef<HTMLInputElement | null>(null);
  const quickRecordVersionRef = useRef<number | null>(null);
  const syncRequestRef = useRef<{ sessionId: string; promise: Promise<DraftSyncResult> } | null>(null);
  const syncPollerRef = useRef<{ stop: () => void; refresh: () => void } | null>(null);
  const boardVersionRef = useRef<number | null>(null);
  const liveBoardRef = useRef<DraftBoard | null>(null);
  const pollerRef = useRef<RoomPoller<RoomPollValue> | null>(null);
  const sortOptionsRef = useRef({ sortBy, descending });
  const previousSortRef = useRef(`${sortBy}:${descending}`);
  sortOptionsRef.current = { sortBy, descending };

  useEffect(() => {
    if (conflict || replayVersion !== null) return;
    boardVersionRef.current = null;
    if (liveBoardRef.current?.session.session_id !== sessionId) {
      liveBoardRef.current = null;
      setBoard(null);
      setLoading(true);
    } else {
      setLoading(false);
    }
    const poller = createRoomPoller<RoomPollValue>({
      load: async (signal) => {
        const options = sortOptionsRef.current;
        const nextBoard = await api.getBoard(
          sessionId,
          options.sortBy,
          options.descending,
          signal,
        );
        return { session: { version: nextBoard.session.version }, board: nextBoard };
      },
      apply: (value) => {
        boardVersionRef.current = value.session.version;
        liveBoardRef.current = value.board;
        setBoard(value.board);
        if (quickRecordVersionRef.current !== null && value.session.version > quickRecordVersionRef.current) {
          quickRecordVersionRef.current = null;
          setQuickRecordPending(false);
          globalThis.setTimeout(() => quickRecordInputRef.current?.focus(), 0);
        }
        setRefreshError("");
        setLoading(false);
      },
      getCurrentVersion: () => boardVersionRef.current,
      onError: (cause) => {
        if (cause instanceof ApiError && cause.status === 409) {
          setConflict(true);
        } else {
          setRefreshError(cause instanceof Error ? cause.message : "Could not load the draft room.");
        }
        setLoading(false);
      },
    });
    pollerRef.current = poller;
    return () => {
      poller.stop();
      if (pollerRef.current === poller) pollerRef.current = null;
    };
  }, [sessionId, conflict, replayVersion]);

  useEffect(() => {
    if (board?.session.draft_source !== "yahoo_live" || replayVersion !== null) {
      setSyncState(null);
      return;
    }
    let stopped = false;
    const syncPoller = createBackoffPoller({
      intervalMs: liveDraftPollIntervalMs,
      maxIntervalMs: MAX_LIVE_DRAFT_POLL_INTERVAL_MS,
      run: async () => {
        const result = await requestLiveSync();
        if (stopped) return;
        setSyncState(result.sync);
        setSyncError("");
        if (result.changed) pollerRef.current?.refresh();
        if (["source_unavailable", "authentication_required", "malformed_source"].includes(result.sync.status)) {
          throw new Error(result.sync.status.replaceAll("_", " "));
        }
      },
      onError: (cause) => {
        if (!stopped) setSyncError(cause instanceof Error ? cause.message : "Yahoo draft sync failed.");
      },
    });
    syncPollerRef.current = syncPoller;
    return () => {
      stopped = true;
      syncPoller.stop();
      if (syncPollerRef.current === syncPoller) syncPollerRef.current = null;
    };
  }, [board?.session.draft_source, sessionId, replayVersion]);

  useEffect(() => {
    if (board?.session.session_id !== sessionId) return;
    setOrderDraft(Object.fromEntries(
      Object.entries(board.session.team_slots).map(([teamKey, slot]) => [teamKey, String(slot)]),
    ));
  }, [board?.session.session_id, sessionId]);

  useEffect(() => {
    if (!board?.session.sync_enabled || board.session.draft_source !== "internal_mock") return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refreshSyncState = async () => {
      try {
        const state = await api.getDraftSync(sessionId);
        if (!stopped) setSyncState(state);
      } catch (cause) {
        if (!stopped) setSyncError(cause instanceof Error ? cause.message : "Mock rehearsal status could not be loaded.");
      } finally {
        if (!stopped) timer = globalThis.setTimeout(() => void refreshSyncState(), 10_000);
      }
    };
    void refreshSyncState();
    return () => {
      stopped = true;
      if (timer !== undefined) globalThis.clearTimeout(timer);
    };
  }, [board?.session.sync_enabled, board?.session.draft_source, sessionId]);

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const loadPlayers = async () => {
      try {
        setPlayers(await api.getPlayers(controller.signal));
      } catch {
        if (!controller.signal.aborted) {
          retryTimer = globalThis.setTimeout(() => void loadPlayers(), 30_000);
        }
      }
    };
    void loadPlayers();
    return () => {
      controller.abort();
      if (retryTimer !== undefined) globalThis.clearTimeout(retryTimer);
    };
  }, [sessionId]);

  useEffect(() => {
    const leagueKey = board?.session.league_key;
    if (!leagueKey) return;
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const loadLeague = async () => {
      try {
        setLeague(await api.getLeague(leagueKey, controller.signal));
      } catch {
        if (!controller.signal.aborted) {
          retryTimer = globalThis.setTimeout(() => void loadLeague(), 30_000);
        }
      }
    };
    void loadLeague();
    return () => {
      controller.abort();
      if (retryTimer !== undefined) globalThis.clearTimeout(retryTimer);
    };
  }, [board?.session.league_key]);

  useEffect(() => {
    const nextSort = `${sortBy}:${descending}`;
    if (previousSortRef.current !== nextSort) {
      previousSortRef.current = nextSort;
      pollerRef.current?.refresh();
    }
  }, [sortBy, descending]);

  const session = board?.session;
  const recommendation = board?.recommendation;
  const readOnlyReplay = replayVersion !== null;
  const isMock = session?.session_type === "mock";
  const browserPractice = session?.browser_practice === true;
  const batchManagedRun = Boolean(session?.mock_batch_id);
  const batchWriteLocked = batchManagedRun && ["queued", "running"].includes(session?.mock_run_status ?? "");
  const batchWorkerOwnsRun = Boolean(session?.mock_batch_id)
    && ["queued", "running"].includes(session?.mock_run_status ?? "");
  const playerById = Object.fromEntries(players.map((player) => [player.id, player]));
  const teamNameById = Object.fromEntries((league?.teams ?? []).map((team) => [team.team_key, team.team_name || team.team_key]));
  const positionChoices = [...new Set(board?.players.flatMap((player) => player.positions) ?? [])].sort();
  const visiblePlayers = (board?.players ?? []).filter((player) => {
    const matchesSearch = `${player.player_name} ${player.positions.join(" ")}`.toLowerCase().includes(search.toLowerCase());
    const matchesPosition = !positionFilter || player.positions.includes(positionFilter);
    const matchesTarget = !targetFilter
      || (targetFilter === "untargeted" ? !player.target_status : player.target_status === targetFilter);
    return matchesSearch && matchesPosition && matchesTarget;
  });
  const allQuickMatches = findQuickMatches(board?.players ?? [], quickSearch);
  const quickMatches = allQuickMatches.slice(0, 6);
  const selectedQuickMatchIndex = Math.min(quickSelection, Math.max(quickMatches.length - 1, 0));
  const selectedQuickMatch = quickMatches[selectedQuickMatchIndex];

  async function performAction(
    action: () => Promise<unknown>,
    successMessage: string,
    onSuccess?: () => void,
    onFailure?: () => void,
  ) {
    if (readOnlyReplay) return;
    setBusy(true);
    setActionError("");
    setNotice("");
    try {
      await action();
      setNotice(successMessage);
      onSuccess?.();
      pollerRef.current?.refresh();
    } catch (cause) {
      onFailure?.();
      if (cause instanceof ApiError && cause.status === 409) {
        setConflict(true);
        setActionError("Draft changed. Reload the latest session version before continuing.");
      } else {
        setActionError(cause instanceof Error ? cause.message : "The draft action could not be saved.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function simulateMock(action: "next_pick" | "until_my_turn") {
    if (!session) return;
    setBusy(true);
    setActionError("");
    setNotice("");
    try {
      const result = await api.mockAction(session.session_id, action);
      setNotice(result.event === "manager_turn"
        ? "Stopped at your slot."
        : result.event === "draft_complete"
          ? "Mock draft complete."
          : `${result.simulated_picks} pick${result.simulated_picks === 1 ? "" : "s"} simulated.`);
      pollerRef.current?.refresh();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Mock simulation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function updateMockPause(paused: boolean) {
    if (!session) return;
    setBusy(true);
    setActionError("");
    try {
      await (paused ? api.pauseMock(session.session_id) : api.resumeMock(session.session_id));
      pollerRef.current?.refresh();
      setNotice(paused ? "Mock paused." : "Mock resumed.");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Mock state could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  async function requestLiveSync() {
    if (!session) throw new Error("Draft session is not loaded.");
    if (syncRequestRef.current?.sessionId === session.session_id) {
      return syncRequestRef.current.promise;
    }
    const request = api.syncDraft(session.session_id);
    const pending = { sessionId: session.session_id, promise: request };
    syncRequestRef.current = pending;
    try {
      return await request;
    } finally {
      if (syncRequestRef.current === pending) syncRequestRef.current = null;
    }
  }

  async function syncNow() {
    if (!session || session.draft_source !== "yahoo_live") return;
    setBusy(true);
    setSyncError("");
    try {
      const result = await requestLiveSync();
      setSyncState(result.sync);
      if (result.changed) pollerRef.current?.refresh();
      setNotice(result.accepted_picks.length
        ? `Synced ${result.accepted_picks.length} Yahoo pick${result.accepted_picks.length === 1 ? "" : "s"}.`
        : "Yahoo draft results checked.");
    } catch (cause) {
      setSyncError(cause instanceof Error ? cause.message : "Yahoo draft sync failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveLiveOrder(
    request: {
      draft_position?: number;
      team_slots?: Record<string, number>;
      replace_mapping?: boolean;
      clear_manager_position?: boolean;
    },
    successMessage: string,
  ) {
    if (!session || session.draft_source !== "yahoo_live") return;
    setOrderUpdateBusy(true);
    setActionError("");
    try {
      const updated = await api.updateLiveOrder(session.session_id, {
        expected_version: session.version,
        ...request,
      });
      setBoard((current) => current ? { ...current, session: updated } : current);
      if (liveBoardRef.current) {
        liveBoardRef.current = { ...liveBoardRef.current, session: updated };
      }
      setNotice(successMessage);
      pollerRef.current?.refresh();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Live draft order could not be updated.");
    } finally {
      setOrderUpdateBusy(false);
    }
  }

  function selectManagerPosition(value: string) {
    if (!session || !league) return;
    const teamSlots = { ...session.team_slots };
    delete teamSlots[session.manager_team_key];
    if (!value) {
      void saveLiveOrder(
        { team_slots: teamSlots, replace_mapping: true, clear_manager_position: true },
        "Your draft position is marked unknown.",
      );
      return;
    }
    const position = Number(value);
    const occupiedBy = Object.entries(teamSlots).find(([, slot]) => slot === position)?.[0];
    if (occupiedBy) {
      setActionError("That slot is already mapped to another Yahoo team. Use the advanced order editor to resolve the mapping.");
      return;
    }
    teamSlots[session.manager_team_key] = position;
    void saveLiveOrder(
      { draft_position: position, team_slots: teamSlots, replace_mapping: true },
      `Your draft position is set to slot ${position}.`,
    );
  }

  function saveManualOrder() {
    if (!session) return;
    const teamSlots = Object.fromEntries(Object.entries(orderDraft)
      .filter(([, slot]) => slot !== "")
      .map(([teamKey, slot]) => [teamKey, Number(slot)]));
    const managerPosition = teamSlots[session.manager_team_key];
    void saveLiveOrder({
      team_slots: teamSlots,
      replace_mapping: true,
      ...(managerPosition ? { draft_position: managerPosition } : { clear_manager_position: true }),
    }, "Manual draft order saved.");
  }

  async function toggleDraftSync(paused: boolean) {
    if (!session || session.draft_source !== "yahoo_live") return;
    setBusy(true);
    setSyncError("");
    try {
      setSyncState(await (paused
        ? api.pauseDraftSync(session.session_id)
        : api.resumeDraftSync(session.session_id)));
      setNotice(paused ? "Yahoo draft sync paused." : "Yahoo draft sync resumed.");
    } catch (cause) {
      setSyncError(cause instanceof Error ? cause.message : "Yahoo draft sync status could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  async function runMockRehearsal(action: import("./api").MockRehearsalAction, label: string) {
    if (!session?.sync_enabled || session.draft_source !== "internal_mock") return;
    setBusy(true);
    setSyncError("");
    try {
      const result = await api.mockRehearsal(session.session_id, action);
      setSyncState(result.sync);
      setNotice(label);
      pollerRef.current?.refresh();
    } catch (cause) {
      setSyncError(cause instanceof Error ? cause.message : "Mock source rehearsal failed.");
    } finally {
      setBusy(false);
    }
  }

  async function resumeMockBatch(batchId: string) {
    setBusy(true);
    setActionError("");
    try {
      await api.runMockBatch(batchId);
      pollerRef.current?.refresh();
      setNotice("Batch recovery started.");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Batch recovery failed.");
    } finally {
      setBusy(false);
    }
  }

  async function resetMock() {
    if (!session) return;
    setBusy(true);
    setActionError("");
    try {
      const restarted = await api.resetMock(session.session_id);
      navigate(`/draft/${restarted.session_id}`);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Mock could not be restarted.");
    } finally {
      setBusy(false);
    }
  }

  async function removeMock() {
    if (!session || session.session_type !== "mock") return;
    if (!window.confirm("Remove this mock draft and its picks? This cannot be undone.")) return;
    setBusy(true);
    setActionError("");
    try {
      await api.deleteMockSession(session.session_id);
      navigate("/");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Mock draft could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  async function loadReplayAt(version: number) {
    if (!session) return;
    pollerRef.current?.stop();
    pollerRef.current = null;
    setReplaySelection(version);
    setReplayVersion(version);
    setReplayError("");
    try {
      const replay = await api.getReplay(session.session_id, version);
      setBoard(replay.board);
    } catch (cause) {
      setReplayError(cause instanceof Error ? cause.message : "Replay snapshot could not be loaded.");
      setReplayVersion(null);
    }
  }

  function loadReplay() {
    void loadReplayAt(replaySelection);
  }

  function stepReplay(direction: -1 | 1) {
    if (replayVersion === null || !session) return;
    const next = Math.min(session.version, Math.max(0, replayVersion + direction));
    if (next !== replayVersion) void loadReplayAt(next);
  }

  function returnToLatest() {
    if (liveBoardRef.current) setBoard(liveBoardRef.current);
    setReplayError("");
    setReplayVersion(null);
  }

  function recordPlayer(playerId: number, fromQuickRecord = false) {
    if (browserPractice) {
      setActionError("Make your selection in Yahoo; the browser observer records it here.");
      return;
    }
    if (!session || readOnlyReplay) return;
    if (isMock && !session.timing.your_turn) return;
    if (fromQuickRecord) {
      quickRecordVersionRef.current = session.version;
      setQuickRecordPending(true);
    }
    void performAction(
      () => api.recordPick(
        session.session_id,
        session.next_overall_pick,
        playerId,
        session.version,
        isMock ? "mock_manager_pick" : "manual",
      ),
      "Pick recorded.",
      fromQuickRecord ? () => {
        setQuickSearch("");
        setQuickSelection(0);
      } : undefined,
      fromQuickRecord ? () => {
        quickRecordVersionRef.current = null;
        setQuickRecordPending(false);
      } : undefined,
    );
  }

  function updateTarget(playerId: number, value: string) {
    if (!session || readOnlyReplay) return;
    const action = value
      ? api.setTarget(session.session_id, playerId, value as TargetStatus, session.version)
      : api.clearTarget(session.session_id, playerId, session.version);
    void performAction(() => action, value ? `Target marked ${value}.` : "Target removed.");
  }

  function submitCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || readOnlyReplay || !correcting || !replacementId) return;
    const overallPick = correcting.overall_pick;
    void performAction(
      () => api.correctPick(session.session_id, overallPick, Number(replacementId), session.version),
      "Pick corrected.",
    );
    setCorrecting(null);
  }

  function undoPick(pick: DraftPick) {
    if (!session || readOnlyReplay) return;
    void performAction(
      () => api.undoPick(session.session_id, pick.overall_pick, session.version),
      "Latest pick undone.",
    );
  }

  if (loading && !board) return <div className="full-loading"><LoaderCircle className="spin" /> Loading draft room</div>;
  if (!board || !session) return <div className="app-shell"><BrandBar /><main className="room-error"><ErrorLine>{refreshError || "Draft session could not be loaded."}</ErrorLine><Link to="/" className="button button-quiet"><ArrowLeft size={16} /> Back to setup</Link></main></div>;

  const recommendedPlayer = recommendation?.recommended_player;
  const currentOverallPick = session?.timing.current_pick;
  const latestPick = [...(session?.picks ?? [])].reverse().find((pick) => pick.selected_player_id !== null);
  const pickedIdsElsewhere = new Set((session?.picks ?? [])
    .filter((pick) => pick.selected_player_id !== null && pick.overall_pick !== correcting?.overall_pick)
    .map((pick) => pick.selected_player_id));
  const inPoolIds = new Set([
    ...(board?.players.map((player) => player.player_identity_id) ?? []),
    ...(session?.picks.map((pick) => pick.selected_player_id).filter((id): id is number => id !== null) ?? []),
  ]);
  const correctionOptions = players.filter((player) => inPoolIds.has(player.id) && !pickedIdsElsewhere.has(player.id));
  const actionLabel = recommendation?.action === "draft_now" ? "DRAFT NOW"
    : recommendation?.action === "wait" ? "WAIT" : "INSUFFICIENT EVIDENCE";
  const localConflictPlayerId = syncState?.conflict_evidence.local_player_identity_id;
  const sourceConflictPlayerId = syncState?.conflict_evidence.source_player_identity_id;
  const localConflictTeam = syncState?.conflict_evidence.local_team_key;
  const sourceConflictTeam = syncState?.conflict_evidence.source_team_key;
  const conflictPlayerName = (value: unknown) => typeof value === "number"
    ? playerById[value]?.player_name ?? `player ID ${value}`
    : "not provided";
  const teamOnClock = session.timing.current_team_key
    ? teamNameById[session.timing.current_team_key] ?? session.timing.current_team_key
    : session.status === "completed"
      ? "Draft complete"
      : session.draft_position === null
        ? "Position pending"
        : "Team not mapped";

  return (
    <div className="app-shell room-shell">
      <BrandBar right={<div className="room-top-actions"><span className={`live-tag ${isMock ? "mock-room-tag" : "live-room-tag"}`}><span className="pulse-dot" /> {browserPractice ? "YAHOO MOCK PRACTICE" : isMock ? "MOCK LIVE DRAFT" : "LIVE DRAFT"}</span><Link to="/" className="top-link"><ArrowLeft size={15} /> Setup</Link></div>} />
      <main className="draft-page">
        <section className="draft-heading">
          <div className="draft-heading-main">
            <p className="eyebrow">{league?.league_name ?? session.league_key} <span>/</span> {session.season}</p>
            <h1>{browserPractice ? "Yahoo Mock Practice" : isMock ? "Mock live draft" : "Live draft"}</h1>
            <div className="heading-subline"><span>{teamNameById[session.manager_team_key] || session.manager_team_key}</span><span className="divider-dot" /> <span className="mode-label">{session.mode} mode</span></div>
          </div>
          <div className="draft-stats" aria-label="Draft status">
            <div><span>ROUND</span><strong>{session.timing.current_round ?? "—"}<small> / {session.rounds}</small></strong></div>
            <div><span>CURRENT PICK</span><strong>#{session.timing.current_pick ?? "—"}</strong></div>
            <div><span>ON THE CLOCK</span><strong>{teamOnClock}</strong></div>
            <div><span>MY NEXT PICK</span><strong>#{session.timing.next_pick ?? "—"}</strong></div>
            <div className="stat-gap"><span>PICKS UNTIL</span><strong>{session.timing.picks_until_next ?? "—"}</strong></div>
          </div>
        </section>

        {session.timing.your_turn && <div className="your-turn-banner" role="status"><Check size={17} /> YOUR TURN <span>Pick #{session.timing.current_pick} · {teamOnClock}</span></div>}
        {conflict && <div className="conflict-banner" role="alert"><CircleAlert size={19} /><div><strong>Draft changed</strong><span>Another update landed on this session. Reload the latest state before taking another action.</span></div><button className="button button-dark" type="button" onClick={() => setConflict(false)}><RefreshCw size={15} /> Reload draft</button></div>}
        {actionError && !conflict && <ErrorLine>{actionError}</ErrorLine>}
        {refreshError && board && <div className="notice notice-warning" role="status"><CircleAlert size={17} />Live refresh paused: {refreshError}</div>}
        {notice && <div className="notice notice-success" role="status"><Check size={17} />{notice}</div>}
        {replayError && <ErrorLine>{replayError}</ErrorLine>}
        {!isMock && <div className="notice notice-warning" role="status"><CircleAlert size={17} />Yahoo does not push picks to this room in real time. Picks are logged manually unless Yahoo draft-results polling is enabled for this session.</div>}
        {session.draft_source === "yahoo_live" && <section className="sync-panel" aria-label="Yahoo draft results sync">
          <div>
            <strong>Yahoo draft-results polling</strong>
            <p>{syncState
              ? `${syncState.status.replaceAll("_", " ")} · confirmed through pick ${syncState.source_confirmed_through} · local picks through ${syncState.local_recorded_through}`
              : "Waiting for sync status."}</p>
            <small>Yahoo draftresults is polled; this is not a verified real-time stream. Manual pick recording remains available.</small>
          </div>
          <div className="sync-actions">
            <button className="button button-quiet" type="button" disabled={busy} title="Fetch and reconcile current Yahoo draft results" onClick={() => void syncNow()}><RefreshCw size={15} /> Sync Now</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void toggleDraftSync(!syncState?.paused)}>{syncState?.paused ? <Play size={15} /> : <Pause size={15} />}{syncState?.paused ? "Resume sync" : "Pause sync"}</button>
          </div>
          {syncError && <ErrorLine>{syncError}</ErrorLine>}
          {syncState?.status === "conflict" && <div className="notice notice-warning sync-conflict-evidence" role="alert">
            <CircleAlert size={16} /><div><strong>Source conflict at pick #{syncState.conflict_overall_pick}</strong>
              <span>Automatic source writes stop at this pick.</span>
              <span>Local: {conflictPlayerName(localConflictPlayerId)}{typeof localConflictTeam === "string" ? ` · ${teamNameById[localConflictTeam] ?? localConflictTeam}` : ""}</span>
              <span>Yahoo source: {conflictPlayerName(sourceConflictPlayerId)}{typeof sourceConflictTeam === "string" ? ` · ${teamNameById[sourceConflictTeam] ?? sourceConflictTeam}` : ""}</span>
            </div>
          </div>}
          {syncState?.status === "authentication_required" && <div className="notice notice-warning" role="alert">Reconnect Yahoo authorization before syncing draft results.</div>}
        </section>}
        {session.draft_source === "yahoo_live" && <section className="panel live-order-panel" aria-label="Live draft order">
          <div className="panel-heading"><div><p className="eyebrow">AUTHORITATIVE ORDER</p><h2>Yahoo draft positions</h2></div><span className={`session-status ${session.draft_order_status}`}>{session.draft_order_status}</span></div>
          <p className="muted small-copy">First-round Yahoo results progressively confirm team slots. Later rounds are checked against the snake order but never used to guess unknown teams.</p>
          {session.draft_order_status === "conflict" && <div className="notice notice-warning" role="alert">
            <CircleAlert size={16} /><div><strong>Order evidence conflicts with the current mapping. Automatic order discovery is halted.</strong>
              <pre>{JSON.stringify(session.draft_order_evidence.conflict ?? {}, null, 2)}</pre>
            </div>
          </div>}
          <div className="order-summary">
            <span>{session.draft_position === null ? <CircleAlert size={15} /> : <Check size={15} />}</span>
            {session.draft_position === null
              ? "Your position is unknown; turn timing and manager recommendations are withheld."
              : `Your manager position: slot ${session.draft_position}`}
            {session.team_slots[session.manager_team_key] !== undefined
              && session.draft_position === null
              && <button className="button button-quiet" type="button" disabled={busy || orderUpdateBusy || readOnlyReplay}
                onClick={() => selectManagerPosition(String(session.team_slots[session.manager_team_key]))}>
                Set my position to slot {session.team_slots[session.manager_team_key]}
              </button>}
          </div>
          <div className="form-grid live-order-controls">
            <label className="field"><span>My position</span><div className="select-wrap"><select value={session.draft_position ?? ""} disabled={busy || orderUpdateBusy || readOnlyReplay}
              onChange={(event) => selectManagerPosition(event.target.value)}>
              <option value="">Unknown</option>
              {Array.from({ length: session.total_teams }, (_, index) => index + 1).map((slot) => <option key={slot} value={slot}>Slot {slot}</option>)}
            </select><ChevronDown size={16} /></div></label>
            <span className="muted small-copy">{Object.keys(session.team_slots).length} of {session.total_teams} team slots currently known.</span>
          </div>
          <div className="slot-table">
            <div className="slot-table-head"><span>DRAFT SLOT</span><span>YAHOO TEAM</span></div>
            {Array.from({ length: session.total_teams }, (_, index) => index + 1).map((slot) => {
              const teamKey = Object.entries(session.team_slots).find(([, mappedSlot]) => mappedSlot === slot)?.[0];
              return <div className={`slot-row ${teamKey === session.manager_team_key ? "is-manager" : ""}`} key={slot}>
                <span>Slot {slot}</span><span>{teamKey ? teamNameById[teamKey] ?? teamKey : "Not yet discovered"}</span>
              </div>;
            })}
          </div>
          <details className="advanced-order-editor">
            <summary>Advanced: resolve or replace the full manual order</summary>
            <div className="slot-table">
              <div className="slot-table-head"><span>YAHOO TEAM</span><span>DRAFT SLOT</span></div>
              {(league?.teams ?? []).map((team) => {
                const assignedElsewhere = new Set(Object.entries(orderDraft)
                  .filter(([key, value]) => key !== team.team_key && value !== "")
                  .map(([, value]) => Number(value)));
                return <label className={`slot-row ${team.team_key === session.manager_team_key ? "is-manager" : ""}`} key={team.team_key}>
                  <span>{team.team_name || team.team_key}{team.team_key === session.manager_team_key && <em>YOU</em>}</span>
                  <span className="select-wrap slot-select"><select aria-label={`Manual draft slot for ${team.team_name || team.team_key}`}
                    value={orderDraft[team.team_key] ?? ""}
                    onChange={(event) => setOrderDraft((current) => ({ ...current, [team.team_key]: event.target.value }))}>
                    <option value="">Unassigned</option>
                    {Array.from({ length: session.total_teams }, (_, index) => index + 1).map((slot) => <option key={slot} value={slot} disabled={assignedElsewhere.has(slot)}>Slot {slot}</option>)}
                  </select><ChevronDown size={15} /></span>
                </label>;
              })}
            </div>
            <button className="button button-quiet" type="button" disabled={busy || orderUpdateBusy || readOnlyReplay}
              onClick={saveManualOrder}>{orderUpdateBusy ? "Saving order…" : "Save manual order"}</button>
          </details>
        </section>}
        {!isMock && <section className="quick-record" aria-label="Quick Record">
          <label htmlFor="quick-record-search">Quick Record · search available players</label>
          <input
            ref={quickRecordInputRef}
            id="quick-record-search"
            type="search"
            autoFocus
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={Boolean(quickSearch && quickMatches.length)}
            aria-controls={quickSearch ? "quick-record-results" : undefined}
            aria-activedescendant={quickSearch && selectedQuickMatch
              ? `quick-record-option-${selectedQuickMatch.player_identity_id}`
              : undefined}
            value={quickSearch}
            onChange={(event) => {
              setQuickSearch(event.target.value);
              setQuickSelection(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                if (selectedQuickMatch) recordPlayer(selectedQuickMatch.player_identity_id, true);
              } else if (event.key === "ArrowDown" && quickMatches.length) {
                event.preventDefault();
                setQuickSelection((current) => moveQuickSelection(current, 1, quickMatches.length));
              } else if (event.key === "ArrowUp" && quickMatches.length) {
                event.preventDefault();
                setQuickSelection((current) => moveQuickSelection(current, -1, quickMatches.length));
              } else if (event.key === "Escape") {
                event.preventDefault();
                if (quickSearch) {
                  setQuickSearch("");
                  setQuickSelection(0);
                } else {
                  event.currentTarget.blur();
                }
              }
            }}
            placeholder="Search a player · arrows select · Enter records · Esc clears"
            disabled={busy || quickRecordPending || conflict || readOnlyReplay || session.status === "completed"}
          />
          <span className="quick-record-context">{session.status === "completed"
            ? "Draft complete"
            : `Pick #${session.next_overall_pick} · ${teamOnClock}`}<br />
            {selectedQuickMatch
              ? `${selectedQuickMatch.player_name} selected · ${allQuickMatches.length} match${allQuickMatches.length === 1 ? "" : "es"}`
              : quickSearch ? "No matching available player" : "Recommendations remain visible below."}</span>
          {quickSearch && <ul id="quick-record-results" className="quick-record-results" role="listbox" aria-label="Available player matches">
            {quickMatches.slice(0, 6).map((player, index) => <li
              id={`quick-record-option-${player.player_identity_id}`}
              key={player.player_identity_id}
              role="option"
              aria-selected={index === selectedQuickMatchIndex}
              className={index === selectedQuickMatchIndex ? "quick-record-option selected" : "quick-record-option"}
            >
              <button type="button" tabIndex={-1} disabled={busy || quickRecordPending || conflict || readOnlyReplay}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setQuickSelection(index)}
                onClick={() => recordPlayer(player.player_identity_id, true)}>
                <strong>{player.player_name}</strong><span>{player.positions.join(" / ") || "Position unavailable"}</span>
              </button>
            </li>)}
          </ul>}
        </section>}

        {browserPractice && <YahooConnect inRoom />}
        {browserPractice && <section className="sync-panel" aria-label="Yahoo Mock Practice source">
          <div><strong>Yahoo Mock Practice · browser input only</strong>
            <p>{syncState ? `${syncState.status.replaceAll("_", " ")} · confirmed through pick ${syncState.source_confirmed_through}` : "Waiting for browser observer status."}</p>
            <small>Make every selection in Yahoo. Internal simulation and Court IQ pick entry are disabled. This does not verify production Yahoo draftresults.</small>
          </div>
        </section>}
        {isMock && !browserPractice && <section className="mock-toolbar" aria-label="Mock live draft controls">
          <div className="mock-toolbar-heading">
            <div><p className="eyebrow">MOCK LIVE DRAFT {session.mock_batch_id ? `· RUN ${(session.mock_run_index ?? 0) + 1}` : "· SINGLE RUN"}</p><h2>{readOnlyReplay ? `Replay · version ${replayVersion}` : `${session.status} · ${session.picks.filter((pick) => pick.selected_player_id !== null).length} / ${session.total_teams * session.rounds} picks`}</h2></div>
            <span className="mock-config-label">Aggressiveness {session.mock_aggressiveness?.toFixed(1) ?? "—"} · seed {session.mock_seed ?? "—"}{session.mock_attempt_index ? ` · attempt ${session.mock_attempt_index + 1}` : ""}</span>
          </div>
          <div className="mock-toolbar-actions">
            {batchWorkerOwnsRun && <span className="mock-config-label">Batch simulation is running; picks are locked to the batch.</span>}
            {batchManagedRun && !batchWorkerOwnsRun && <span className="mock-config-label">Run history is controlled by its batch.</span>}
            {!readOnlyReplay && <>
              {!batchManagedRun && <>
                <button className="button button-quiet" type="button" disabled={busy || session.status !== "active"} onClick={() => void simulateMock("next_pick")}><SkipForward size={15} /> Auto Pick Next</button>
                <button className="button button-quiet" type="button" disabled={busy || session.status !== "active" || session.timing.your_turn === true} onClick={() => void simulateMock("until_my_turn")}><Target size={15} /> Auto Pick Until My Turn</button>
              </>}
              {batchManagedRun && session.mock_batch_id && <button className="button button-accent" type="button" disabled={busy} onClick={() => void resumeMockBatch(session.mock_batch_id!)}><Play size={15} /> Run / recover batch</button>}
              {session.status === "paused"
                ? <button className="button button-quiet" type="button" disabled={busy} onClick={() => void updateMockPause(false)}><Play size={15} /> Resume</button>
                : <button className="button button-quiet" type="button" disabled={busy || session.status === "completed"} onClick={() => void updateMockPause(true)}><Pause size={15} /> Pause</button>}
              {!batchManagedRun && latestPick && <button className="button button-quiet" type="button" disabled={busy || readOnlyReplay} onClick={() => undoPick(latestPick)}><Undo2 size={15} /> Undo latest pick</button>}
              <button className="button button-quiet" type="button" disabled={busy} onClick={() => void resetMock()}><RotateCcw size={15} /> Reset Mock Draft</button>
              <button className="button button-quiet" type="button" disabled={busy} onClick={() => navigate("/")}><Sparkles size={15} /> New Mock Draft</button>
              {!batchManagedRun && <button className="button button-danger" type="button" disabled={busy} onClick={() => void removeMock()}><X size={15} /> Remove Mock</button>}
              <label className="replay-control"><Clock3 size={15} /><span>Replay version</span><input type="number" min="0" max={session.version} value={replaySelection} onChange={(event) => setReplaySelection(Math.min(session.version, Math.max(0, Number(event.target.value))))} /></label>
              <button className="button button-quiet" type="button" disabled={busy} onClick={() => void loadReplay()}>Load</button>
            </>}
            {readOnlyReplay && <>
              <button className="icon-button" type="button" aria-label="Previous snapshot" title="Previous snapshot" disabled={replayVersion === 0} onClick={() => stepReplay(-1)}><ArrowLeft size={16} /></button>
              <span className="mock-config-label">Snapshot {replayVersion} / {session.version}</span>
              <button className="icon-button" type="button" aria-label="Next snapshot" title="Next snapshot" disabled={replayVersion === session.version} onClick={() => stepReplay(1)}><ArrowRight size={16} /></button>
              <button className="button button-primary" type="button" onClick={returnToLatest}><RefreshCw size={15} /> Return to latest</button>
            </>}
          </div>
          <p className="mock-data-note">Opponent picks use current ADP when present; otherwise the backend falls back to the scored board ranking. Missing ADP is never filled in or invented.</p>
        </section>}
        {isMock && !browserPractice && session.sync_enabled && <section className="sync-panel mock-sync-panel" aria-label="Mock source sync rehearsal">
          <div>
            <strong>Mock Sync Rehearsal · Yahoo-shaped snapshots</strong>
            <p>{syncState ? `${syncState.status.replaceAll("_", " ")} · source through ${syncState.source_confirmed_through} · local through ${syncState.local_recorded_through}` : "Loading rehearsal state."}</p>
            <small>Generated snapshots pass through the same normalizer and sequential reconciliation path. No Yahoo source or Yahoo roster is changed.</small>
          </div>
          <div className="sync-actions">
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("step_one_pick", "One mock pick simulated and reconciled.")}>Step one pick</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("fast", "Mock picks simulated until your turn and reconciled.")}>Run until turn</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal(syncState?.mock_hold_delivery ? "release_delayed_picks" : "simulate_source_lag", syncState?.mock_hold_delivery ? "Delayed source picks released." : "Source delivery held to simulate lag.")}>{syncState?.mock_hold_delivery ? "Release delayed picks" : "Simulate lag"}</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal(syncState?.paused ? "resume_source" : "pause_source", syncState?.paused ? "Mock source resumed." : "Mock source paused.")}>{syncState?.paused ? "Resume source" : "Pause source"}</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("simulate_pick_conflict", "A source conflict was injected.")}>Inject conflict</button>
            {syncState?.status === "conflict" && <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("resolve_with_yahoo", "Conflict resolved using the mock source snapshot.")}>Resolve with source</button>}
            {syncState?.status === "conflict" && <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("keep_local_and_pause", "Local pick retained; source paused.")}>Keep local + pause</button>}
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal(syncState?.status === "source_unavailable" ? "recover_source" : "simulate_source_outage", syncState?.status === "source_unavailable" ? "Mock source recovered." : "Mock source outage simulated.")}>{syncState?.status === "source_unavailable" ? "Recover source" : "Simulate outage"}</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("simulate_duplicate_snapshot", "Duplicate source snapshot injected.")}>Duplicate snapshot</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("simulate_malformed_source", "Malformed source payload injected.")}>Malformed payload</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("simulate_unknown_player", "Unknown Yahoo player ID injected.")}>Unknown player</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("simulate_local_ahead_confirmation", "Local picks submitted for source confirmation.")}>Confirm local picks</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("undo_latest_local", "Latest mock pick undone and source rechecked.")}>Undo latest</button>
            <button className="button button-quiet" type="button" disabled={busy} onClick={() => void runMockRehearsal("reset_rehearsal", "Mock rehearsal reset.")}>Reset rehearsal</button>
          </div>
          {syncError && <ErrorLine>{syncError}</ErrorLine>}
          {syncState?.status === "conflict" && <div className="notice notice-warning sync-conflict-evidence" role="alert">
            <CircleAlert size={16} /><div><strong>Source conflict at pick #{syncState.conflict_overall_pick}</strong>
              <span>Automatic source writes stop at this pick.</span>
              <span>Local: {conflictPlayerName(localConflictPlayerId)}{typeof localConflictTeam === "string" ? ` · ${teamNameById[localConflictTeam] ?? localConflictTeam}` : ""}</span>
              <span>Yahoo-shaped source: {conflictPlayerName(sourceConflictPlayerId)}{typeof sourceConflictTeam === "string" ? ` · ${teamNameById[sourceConflictTeam] ?? sourceConflictTeam}` : ""}</span>
            </div>
          </div>}
        </section>}
        {isMock && session.mock_evaluation && <section className="mock-evaluation" aria-label="Mock draft outcomes">
          <div><span>MANAGER DECISIONS</span><strong>{session.mock_evaluation.manager_decision_count}</strong></div>
          <div><span>PLAYERS DRAFTED</span><strong>{session.mock_evaluation.players_drafted.length}</strong></div>
          <div><span>DEFERRED TARGETS SURVIVED</span><strong>{session.mock_evaluation.survival_outcomes.filter((item) => item.survived_to_next_manager_turn === true).length} / {session.mock_evaluation.survival_outcomes.filter((item) => item.survived_to_next_manager_turn !== null).length}</strong></div>
          <div><span>REALIZED WAIT COSTS</span><strong>{session.mock_evaluation.wait_cost_outcomes.filter((item) => item.realized_wait_cost !== null).length}</strong></div>
        </section>}

        <div className="room-grid">
          <div className="room-primary">
            <section className={`decision-card action-${recommendation?.action ?? "insufficient_evidence"}`} aria-labelledby="decision-title">
              <div className="decision-topline"><span className="decision-kicker"><Sparkles size={15} /> YOUR DECISION</span><span className="confidence-tag">{recommendation?.confidence ?? "unavailable"} confidence</span></div>
              {recommendedPlayer ? <>
                <div className="decision-player-line">
                  <div><p className="eyebrow">BEST PICK NOW · ROSTER UTILITY</p><h2 id="decision-title">{recommendedPlayer.player_name}</h2><p className="player-meta">{recommendedPlayer.positions.join(" / ") || "Position unavailable"}</p><p className="player-meta">Highest current adjusted roster value</p></div>
                  <div className="decision-score"><span>DECISION SCORE</span><strong>{recommendation?.decision_score?.toFixed(1) ?? "—"}</strong></div>
                </div>
                <p className="player-meta">Roster utility: {recommendedPlayer.utility_score.toFixed(2)} before mode/run adjustments</p>
                <YahooPlayerStatus evidence={recommendedPlayer} />
                <RosterImpactDetails impact={board.players.find((player) => player.player_identity_id === recommendedPlayer.player_identity_id)?.roster_impact} />
                <div aria-label="Wait analysis">
                <p className="eyebrow">WAIT ANALYSIS</p>
                <p className="player-meta">{recommendation?.action === "insufficient_evidence" ? "WAIT ANALYSIS UNAVAILABLE" : `${actionLabel} AT YOUR NEXT PICK`}</p>
                <p className="player-meta">{recommendedPlayer.reasons.find((reason) => reason.startsWith("Wait decision unavailable:") || reason.startsWith("Expected wait utility")) ?? "Wait-analysis reason unavailable in this saved snapshot."}</p>
                <div className="decision-metrics">
                  <div><span>SURVIVAL ESTIMATE · UNVALIDATED</span><strong>{recommendation?.survival_probability == null ? "Unknown" : `${Math.round(recommendation.survival_probability * 100)}% heuristic`}</strong></div>
                  <div><span>EXPECTED WAIT COST</span><strong>{recommendation?.expected_wait_cost == null ? "Unknown" : recommendation.expected_wait_cost.toFixed(1)}</strong></div>
                  <div><span>VALUE</span><strong>{recommendedPlayer.fantasy_value.toFixed(1)}</strong></div>
                  <div><span>BEST VALUE AT RISK</span><strong>{recommendation?.best_value_at_risk?.player_name ?? "Unavailable"}</strong><small>{recommendation?.best_value_at_risk?.expected_wait_cost == null ? "Wait cost unavailable" : `Expected wait cost ${recommendation.best_value_at_risk.expected_wait_cost.toFixed(1)}`}</small></div>
                </div>
                </div>
                <div className="decision-footer">
                  <span>{session.timing.your_turn ? `You are on the clock · pick ${currentOverallPick}` : `Your pick is ${session.timing.picks_until_next ?? "—"} picks away`}</span>
                  <button className="button button-accent" type="button" disabled={browserPractice || !session.timing.your_turn || busy || conflict || readOnlyReplay || batchWriteLocked} onClick={() => recordPlayer(recommendedPlayer.player_identity_id)}>
                    {busy ? <LoaderCircle className="spin" size={17} /> : <Target size={17} />}
                    {session.timing.your_turn ? "Draft player" : `Waiting for pick ${session.timing.next_pick ?? "—"}`}
                  </button>
                </div>
              </> : <div className="decision-empty"><h2 id="decision-title">No eligible recommendation available</h2><p>No scored player passes the current recommendation eligibility checks. Historical values and Yahoo status remain visible on the board.</p></div>}
            </section>

            <section className="panel roster-panel" aria-labelledby="roster-title">
              <div className="panel-heading"><div><p className="eyebrow">TEAM BUILD</p><h2 id="roster-title">My roster</h2></div><span className="roster-count">{board.roster.filled_count} filled <i>/</i> {board.roster.open_count} open</span></div>
              <div className="roster-slots">
                {board.roster.slots.map((slot, index) => <div key={`${slot.position}-${index}`} className={`roster-slot ${slot.player ? "filled" : "open"}`}>
                  <span className="slot-position">{slot.position}</span>
                  {slot.player ? <><strong>{slot.player.player_name}</strong><span>{slot.player.positions.join(" / ")}</span></> : <><strong>Open</strong><span>Position available</span></>}
                </div>)}
                {board.roster.slots.length === 0 && <p className="muted small-copy">No starting or bench roster slots are available from league settings.</p>}
              </div>
              <div className="roster-drafted"><strong>Drafted by you</strong><span>{board.roster.drafted_players.length ? board.roster.drafted_players.map((player) => player.player_name).join(" · ") : "No picks recorded yet"}</span></div>
            </section>

            <section className="panel window-panel" aria-labelledby="window-title">
              <div className="panel-heading"><div><p className="eyebrow">SNAKE TIMING</p><h2 id="window-title">Draft window</h2></div><Clock3 size={19} /></div>
              <div className="draft-window-track">
                <div className={`window-stop ${session.timing.your_turn ? "is-current" : ""}`}><span className="window-marker">{session.timing.current_pick ?? "—"}</span><span>CURRENT PICK</span><strong>{session.timing.your_turn ? "Your turn" : teamOnClock}</strong></div>
                <div className="window-connector"><span>{session.timing.picks_until_next ?? "—"} picks</span><i /></div>
                <div className="window-stop next-stop"><span className="window-marker">{session.timing.next_pick ?? "—"}</span><span>YOUR NEXT PICK</span><strong>{session.timing.next_round ? `Round ${session.timing.next_round}` : "Draft complete"}</strong></div>
              </div>
              <div className="run-strip"><Flame size={16} /><span>Recent position runs</span><div>{(recommendation?.recommended_player ? (board.session.latest_recommendation as { draft_runs?: Array<{ position_group: string; recent_pick_count: number; active: boolean }> } | null)?.draft_runs ?? [] : []).filter((run) => run.active).map((run) => <span className="run-chip" key={run.position_group}>{run.position_group} <b>{run.recent_pick_count}</b></span>)}{!((board.session.latest_recommendation as { draft_runs?: Array<{ active: boolean }> } | null)?.draft_runs ?? []).some((run) => run.active) && <span className="muted">No active run reported</span>}</div></div>
            </section>
          </div>

          <div className="room-secondary">
            <section className="panel board-panel" aria-labelledby="board-title">
              <div className="panel-heading board-heading"><div><p className="eyebrow">AVAILABLE PLAYER POOL</p><h2 id="board-title">Draft board <span>{board.players.length}</span></h2></div><button className="icon-button" type="button" aria-label="Refresh draft board" title="Refresh draft board" onClick={() => pollerRef.current?.refresh()}><RefreshCw size={17} /></button></div>
              <div className="board-controls">
                <label className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search players" aria-label="Search available players" /></label>
                <label className="filter-control"><Filter size={15} /><select value={positionFilter} onChange={(event) => setPositionFilter(event.target.value)} aria-label="Filter by position"><option value="">All positions</option>{positionChoices.map((position) => <option key={position}>{position}</option>)}</select><ChevronDown size={14} /></label>
                <label className="filter-control"><Target size={15} /><select value={targetFilter} onChange={(event) => setTargetFilter(event.target.value)} aria-label="Filter by target status"><option value="">All targets</option><option value="untargeted">Unmarked</option>{targetStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select><ChevronDown size={14} /></label>
                <label className="filter-control sort-control"><select value={sortBy} onChange={(event) => setSortBy(event.target.value)} aria-label="Sort draft board"><option value="decision">Decision score</option><option value="value">Value</option><option value="survival">Survival</option><option value="name">Player name</option></select><ChevronDown size={14} /></label>
                <button className="icon-button sort-direction" type="button" aria-label={`Sort ${descending ? "ascending" : "descending"}`} title={`Sort ${descending ? "ascending" : "descending"}`} onClick={() => setDescending((value) => !value)}>{descending ? <ArrowDownWideNarrow size={17} /> : <ArrowUpNarrowWide size={17} />}</button>
              </div>
              <div className="table-scroll"><table className="player-table"><thead><tr><th>Player</th><th>Decision</th><th>Value</th><th>ADP</th><th>Market delta</th><th>Survival / miss risk</th><th>Target</th><th>Action</th></tr></thead><tbody>
                {visiblePlayers.map((player) => <PlayerRow key={player.player_identity_id} player={player} busy={busy || conflict || readOnlyReplay || batchWriteLocked || browserPractice} allowPick={!isMock || session.timing.your_turn === true} onRecord={recordPlayer} onTarget={updateTarget} />)}
                {visiblePlayers.length === 0 && <tr><td colSpan={8} className="table-empty">No available players match these filters.</td></tr>}
              </tbody></table></div>
              <div className="table-foot"><span>Sorted by {sortBy === "decision" ? "backend decision score" : sortBy}</span><span>{visiblePlayers.length} shown</span></div>
            </section>

            <section className="panel recent-panel" aria-labelledby="recent-title">
              <div className="panel-heading"><div><p className="eyebrow">ROOM LOG</p><h2 id="recent-title">Recent picks</h2></div><span className="recent-version">VERSION {session.version}</span></div>
              <div className="recent-picks">
                {[...session.picks].filter((pick) => pick.selected_player_id !== null).reverse().slice(0, 8).map((pick) => {
                  const draftedPlayer = playerById[pick.selected_player_id!];
                  const isLatest = latestPick?.overall_pick === pick.overall_pick;
                  return <div className="recent-pick" key={pick.overall_pick}>
                    <span className="recent-pick-number">{pick.overall_pick}</span>
                    <div className="recent-pick-info"><strong>{draftedPlayer?.player_name ?? `Player ${pick.selected_player_id}`}</strong><span>{pick.team_key ? teamNameById[pick.team_key] ?? pick.team_key : "Team not yet mapped"} · {draftedPlayer?.position ?? "Position unknown"}</span>{isMock && pick.selection_source && <small>{pick.selection_source === "scored_board_ranking_adp_unavailable" ? "Scored board fallback · ADP unavailable" : pick.selection_source === "fresh_adp_plus_randomness" ? "Fresh ADP + randomness" : "Available-pool fallback · no ADP or score"}</small>}</div>
                    <div className="recent-actions"><button className="icon-button" type="button" title="Correct pick" aria-label={`Correct pick ${pick.overall_pick}`} disabled={busy || conflict || readOnlyReplay || batchWriteLocked} onClick={() => { setCorrecting(pick); setReplacementId(String(pick.selected_player_id)); }}><RefreshCw size={15} /></button>{isLatest && <button className="icon-button danger-icon" type="button" title="Undo latest pick" aria-label="Undo latest pick" disabled={busy || conflict || readOnlyReplay || batchWriteLocked} onClick={() => undoPick(pick)}><Undo2 size={16} /></button>}</div>
                  </div>;
                })}
                {session.picks.every((pick) => pick.selected_player_id === null) && <p className="muted small-copy">Picks show here as the room advances.</p>}
              </div>
            </section>

            <section className="panel analysis-panel" aria-labelledby="analysis-title">
              <div className="panel-heading"><div><p className="eyebrow">DECISION CONTEXT</p><h2 id="analysis-title">Why & if you wait</h2></div><Sparkles size={18} /></div>
              {recommendation?.reasons.length ? <ul className="reason-list">{recommendation.reasons.slice(0, 5).map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul> : <p className="muted small-copy">No recommendation explanation is available.</p>}
              <div className="wait-block"><div className="wait-heading"><span>IF YOU WAIT</span><span>{recommendation?.wait_analysis.length ?? 0} FALLBACKS</span></div>{recommendation?.wait_analysis.slice(0, 3).map((fallback) => <div className="fallback-row" key={fallback.player_identity_id}><span>{fallback.player_name}</span><strong>{Math.round(fallback.survival_probability * 100)}% <small>survival</small></strong></div>)}{!recommendation?.wait_analysis.length && <p className="muted small-copy">Fallback survival is unavailable for this pick.</p>}</div>
              {recommendation?.alternatives.length ? <div className="alternatives-block"><span className="eyebrow">ALTERNATIVES FROM ENGINE</span>{recommendation.alternatives.slice(0, 3).map((player) => <div className="alternative-row" key={player.player_identity_id}><span><strong>{player.player_name}</strong><small>{Math.round(player.survival_probability * 100)}% survival</small></span><b>{player.utility_score.toFixed(1)}</b></div>)}</div> : null}
              <div className="quality-block"><div className="quality-heading"><ShieldCheck size={16} /><strong>Data quality</strong></div>
                <QualityLine label="Decision score" value={recommendation?.decision_score == null ? "Unavailable" : "Heuristic"} status={recommendation?.data_quality.decision ?? "insufficient_evidence"} />
                <QualityLine label="Survival probability" value={recommendation?.survival_probability == null ? "Unavailable" : "Heuristic estimate, not calibrated"} status={recommendation?.data_quality.survival ?? "insufficient_evidence"} />
                <QualityLine label="Expected wait cost" value={recommendation?.expected_wait_cost == null ? "Unavailable" : "Heuristic"} status={recommendation?.data_quality.wait_cost ?? "insufficient_evidence"} />
                <QualityLine label="Category fit" value="Not implemented" status="insufficient_evidence" />
              </div>
              {recommendation?.warnings.map((warning) => <p className="warning-copy" key={warning}>{warning}</p>)}
            </section>
          </div>
        </div>
      </main>

      {correcting && !readOnlyReplay && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setCorrecting(null)}>
        <form className="correction-dialog" role="dialog" aria-modal="true" aria-labelledby="correction-title" onSubmit={submitCorrection}>
          <div className="dialog-title"><div><p className="eyebrow">PICK {correcting.overall_pick}</p><h2 id="correction-title">Correct this selection</h2></div><button className="icon-button" type="button" aria-label="Close correction dialog" onClick={() => setCorrecting(null)}><X size={18} /></button></div>
          <label className="field"><span>Replace with</span><div className="select-wrap"><select value={replacementId} onChange={(event) => setReplacementId(event.target.value)} required>
            {correctionOptions.map((player) => <option key={player.id} value={player.id}>{player.player_name} · {player.position ?? "Position unknown"}</option>)}
          </select><ChevronDown size={16} /></div></label>
          <div className="dialog-actions"><button className="button button-quiet" type="button" onClick={() => setCorrecting(null)}>Cancel</button><button className="button button-primary" type="submit" disabled={busy || conflict || !replacementId}><Check size={16} /> Save correction</button></div>
        </form>
      </div>}
    </div>
  );
}

function YahooPlayerStatus({ evidence }: { evidence: YahooStatusEvidence }) {
  return <div className={`yahoo-player-status status-${evidence.recommendation_eligibility ?? "unknown"}`}>
    <strong>CURRENT YAHOO STATUS: {evidence.yahoo_status_label ?? evidence.yahoo_status ?? "Unknown"}</strong>
    <small>{evidence.yahoo_status_reason ?? "Availability unknown; this snapshot has no status evidence."}</small>
    <small>Yahoo pool retrieved: {evidence.yahoo_status_as_of ? new Date(evidence.yahoo_status_as_of).toLocaleString() : "Unknown"}</small>
  </div>;
}

function RosterImpactDetails({ impact }: { impact?: RosterImpact | null }) {
  if (!impact) return <small className="market-source">Roster comparison unavailable for this saved snapshot.</small>;
  const signed = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
  return <details className="roster-impact">
    <summary>Why this rank? #{impact.rank_without_roster} → #{impact.rank_with_roster} · roster {signed(impact.score_change)}</summary>
    <p>Same available players, scoring, mode and run pressure; only your roster changes. Rank 1 is best.</p>
    <small>Value ranks include status-excluded board players. Recommendation eligibility is separate.</small>
    <dl>
      <dt>Score without your picks</dt><dd>{impact.score_without_roster.toFixed(2)}</dd>
      <dt>Position need</dt><dd>{impact.need_without_roster.toFixed(1)} → {impact.need_with_roster.toFixed(1)} / 100 ({signed(impact.need_score_change)})</dd>
      <dt>Scarcity × need change</dt><dd>{signed(impact.scarcity_need_score_change)}</dd>
      <dt>Construction fit</dt><dd>{impact.construction_without_roster.toFixed(0)} → {impact.construction_with_roster.toFixed(0)} / 100 ({signed(impact.construction_score_change)})</dd>
    </dl>
    <p>Player value, durability, risk, upside, replacement, mode and run bonus are held fixed in this comparison. ADP affects wait analysis, not this ranking.</p>
  </details>;
}

function PlayerRow({ player, busy, allowPick, onRecord, onTarget }: {
  player: BoardPlayer;
  busy: boolean;
  allowPick: boolean;
  onRecord: (playerId: number) => void;
  onTarget: (playerId: number, value: string) => void;
}) {
  const status = player.target_status ?? "";
  return <tr>
    <td><strong className="table-player-name">{player.player_name}</strong><span className="table-player-pos">{player.positions.join(" / ") || "Position unknown"}</span><YahooPlayerStatus evidence={player} /></td>
    <td><span className={`action-pill ${player.decision_action}`}>{player.recommendation_eligibility === "excluded" ? "Not recommendation eligible" : player.decision_action === "draft_now" ? "Draft" : player.decision_action === "wait" ? "Wait" : "Unclear"}</span><RosterImpactDetails impact={player.roster_impact} /></td>
    <td className="mono-cell">{player.value_score == null ? "—" : player.value_score.toFixed(1)}</td>
    <td className="mono-cell" title={player.adp_source ? `ADP source: ${player.adp_source}` : "ADP unavailable"}>{player.adp == null ? <span className="unknown-value">{player.data_freshness === "stale" ? "ADP stale" : "ADP unavailable"}<small className="market-source">{player.data_freshness === "stale" ? `Last retrieved ${player.market_data_as_of ? new Date(player.market_data_as_of).toLocaleString() : "timestamp unavailable"}` : "No matched current market record"}</small></span> : <>{player.adp.toFixed(1)}<small className="market-source">{player.adp_source}</small></>}</td>
    <td className="mono-cell">{player.market_value_delta == null ? <span className="unknown-value">Unknown</span> : <>{player.market_value_delta > 0 ? "+" : ""}{player.market_value_delta.toFixed(1)}<small className="market-source">{player.market_value_delta > 0 ? "reach" : player.market_value_delta < 0 ? "fallen" : "at market"}</small></>}</td>
    <td className="survival-cell">{player.survival_probability == null
      ? <span className="unknown-value">{player.data_freshness === "stale" ? "Stale · unknown" : "Unknown"}</span>
      : <><strong>{Math.round(player.survival_probability * 100)}% heuristic</strong><small>Miss-risk index {player.miss_risk_score == null ? "—" : player.miss_risk_score.toFixed(0)}/100 · unvalidated</small></>}</td>
    <td><label className="sr-only" htmlFor={`target-${player.player_identity_id}`}>Target status for {player.player_name}</label><select id={`target-${player.player_identity_id}`} className={`target-select ${status ? `target-${status}` : ""}`} value={status} onChange={(event) => onTarget(player.player_identity_id, event.target.value)} disabled={busy}><option value="">Mark</option>{targetStatuses.map((target) => <option key={target} value={target}>{target}</option>)}</select></td>
    <td><button className="row-pick-button" type="button" onClick={() => onRecord(player.player_identity_id)} disabled={busy || !allowPick}>{allowPick ? player.decision_action === "draft_now" ? "Pick" : "Log pick" : "Your turn only"}</button></td>
  </tr>;
}

function QualityLine({ label, value, status }: { label: string; value: string; status: string }) {
  return <div className="quality-line"><span><strong>{label}</strong><small>{value}</small></span><em className={`quality-status quality-${status}`}>{status.replaceAll("_", " ")}</em></div>;
}

export default function App() {
  return <Routes><Route path="/" element={<SetupPage />} /><Route path="/draft/:sessionId" element={<DraftRoomPage />} /><Route path="*" element={<SetupPage />} /></Routes>;
}
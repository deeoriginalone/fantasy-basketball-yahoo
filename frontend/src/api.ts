import type {
  DraftBoard,
  DraftMode,
  DraftMockBatch,
  MockOrderPreview,
  DraftReplay,
  DraftSession,
  League,
  PlayerIdentity,
  TargetStatus,
  DraftSyncResult,
  DraftSyncState,
} from "./types";

export type MockRehearsalAction =
  | "normal" | "fast" | "step_one_pick" | "deliver_next_snapshot" | "pause_source"
  | "resume_source" | "simulate_source_lag" | "release_delayed_picks"
  | "simulate_duplicate_snapshot" | "simulate_multiple_picks_together"
  | "simulate_source_outage" | "recover_source" | "simulate_local_ahead_confirmation"
  | "simulate_pick_conflict" | "resolve_with_yahoo" | "keep_local_and_pause" | "undo_latest_local"
  | "simulate_malformed_source" | "simulate_unknown_player" | "reset_rehearsal";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.reason_code ?? response.statusText;
    throw new ApiError(response.status, message || "The request could not be completed.");
  }
  return payload as T;
}

export const api = {
  getLeagues: () => request<League[]>("/api/v1/leagues"),
  getLeague: (leagueKey: string, signal?: AbortSignal) =>
    request<League>(`/api/v1/league?league_key=${encodeURIComponent(leagueKey)}`, { signal }),
  getSessions: () => request<DraftSession[]>("/api/v2/draft/sessions"),
  getMockSessions: () => request<DraftSession[]>("/api/v2/draft/mock-sessions"),
  deleteMockSession: (sessionId: string) =>
    request<void>(`/api/v2/draft/mock-sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),
  getPlayers: (signal?: AbortSignal) => request<PlayerIdentity[]>("/api/v1/players", { signal }),
  getBoard: (sessionId: string, sortBy = "decision", descending = true, signal?: AbortSignal) =>
    request<DraftBoard>(
      `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/board?sort_by=${sortBy}&descending=${descending}`,
      { signal },
    ),
  getDraftSync: (sessionId: string, signal?: AbortSignal) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync`, { signal }),
  syncDraft: (sessionId: string) =>
    request<DraftSyncResult>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync`, {
      method: "POST",
    }),
  pauseDraftSync: (sessionId: string) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync/pause`, {
      method: "POST",
    }),
  resumeDraftSync: (sessionId: string) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync/resume`, {
      method: "POST",
    }),
  mockRehearsal: (sessionId: string, action: MockRehearsalAction) =>
    request<DraftSyncResult>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock-rehearsal`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  importLeagues: () => request<unknown>("/api/v1/leagues/import", { method: "POST" }),
  importPlayers: (leagueKey: string) =>
    request<unknown>(`/api/v1/players/import?league_key=${encodeURIComponent(leagueKey)}`, { method: "POST" }),
  buildMetrics: (leagueKey: string, season: string) =>
    request<unknown>(
      `/api/v1/draft/metrics?league_key=${encodeURIComponent(leagueKey)}&season=${encodeURIComponent(season)}`,
      { method: "POST" },
    ),
  createSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots: Record<string, number>;
    mode: DraftMode;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createLiveSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number | null;
    total_teams: number;
    rounds: number;
    team_slots: Record<string, number>;
    mode: DraftMode;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/live-sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createMockSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots?: Record<string, number>;
    mode: DraftMode;
    aggressiveness: number;
    seed?: number;
    opponent_order_seed?: number;
    live_sync_rehearsal?: boolean;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/mock-sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createMockBatch: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots?: Record<string, number>;
    mode: DraftMode;
    aggressiveness: number;
    seed?: number;
    opponent_order_seed?: number;
    count: number;
  }) => request<{ batch: DraftMockBatch; session_ids: string[] }>("/api/v2/draft/mock-batches", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  previewMockOrder: (body: {
    league_key: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    seed: number;
  }) => request<MockOrderPreview>("/api/v2/draft/mock-order-preview", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  updateLiveOrder: (sessionId: string, body: {
    expected_version: number;
    draft_position?: number;
    team_slots?: Record<string, number>;
    replace_mapping?: boolean;
    clear_manager_position?: boolean;
  }) => request<DraftSession>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/order`, {
    method: "PUT",
    body: JSON.stringify(body),
  }),
  getMockBatches: () => request<DraftMockBatch[]>("/api/v2/draft/mock-batches"),
  runMockBatch: (batchId: string) => request<{ batch: DraftMockBatch }>(
    `/api/v2/draft/mock-batches/${encodeURIComponent(batchId)}/run`,
    { method: "POST" },
  ),
  mockAction: (sessionId: string, action: "next_pick" | "until_my_turn") =>
    request<{ state: DraftSession; event: string; simulated_picks: number }>(
      `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock-action`,
      { method: "POST", body: JSON.stringify({ action }) },
    ),
  pauseMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/pause`, { method: "POST" },
  ),
  resumeMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/resume`, { method: "POST" },
  ),
  resetMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/reset`, { method: "POST" },
  ),
  getReplay: (sessionId: string, version: number) => request<DraftReplay>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/replay?version=${version}`,
  ),
  recordPick: (
    sessionId: string,
    pick: number,
    playerId: number,
    version: number,
    source = "manual",
  ) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}`, {
      method: "POST",
      body: JSON.stringify({
        selected_player_id: playerId,
        expected_version: version,
        source,
      }),
    }),
  correctPick: (sessionId: string, pick: number, playerId: number, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}`, {
      method: "PUT",
      body: JSON.stringify({
        selected_player_id: playerId,
        expected_version: version,
        source: "manual_correction",
      }),
    }),
  undoPick: (sessionId: string, pick: number, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}/undo`, {
      method: "POST",
      body: JSON.stringify({ expected_version: version }),
    }),
  setTarget: (sessionId: string, playerId: number, status: TargetStatus, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/targets/${playerId}`, {
      method: "PUT",
      body: JSON.stringify({ status, expected_version: version }),
    }),
  clearTarget: (sessionId: string, playerId: number, version: number) =>
    request<unknown>(
      `/api/v2/draft/sessions/${sessionId}/targets/${playerId}?expected_version=${version}`,
      { method: "DELETE" },
    ),
};
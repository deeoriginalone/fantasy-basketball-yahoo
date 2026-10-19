export interface VersionedRoom {
  session: { version: number };
}

export interface RoomPoller<T extends VersionedRoom> {
  refresh: () => void;
  stop: () => void;
}

export function createRoomPoller<T extends VersionedRoom>(options: {
  load: (signal: AbortSignal) => Promise<T>;
  apply: (value: T) => void;
  getCurrentVersion: () => number | null;
  onError: (error: unknown) => void;
  intervalMs?: number;
}): RoomPoller<T>;
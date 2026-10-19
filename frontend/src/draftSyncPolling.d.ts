export interface BackoffPollerOptions {
  run: () => Promise<void>;
  onError: (error: unknown) => void;
  intervalMs: number;
  maxIntervalMs: number;
  setTimer?: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
}

export function createBackoffPoller(options: BackoffPollerOptions): {
  refresh: () => void;
  stop: () => void;
};

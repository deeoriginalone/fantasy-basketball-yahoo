export function createBackoffPoller({
  run,
  onError,
  intervalMs,
  maxIntervalMs,
  setTimer = globalThis.setTimeout,
  clearTimer = globalThis.clearTimeout,
}) {
  let stopped = false;
  let inFlight = false;
  let refreshPending = false;
  let failures = 0;
  let timer = null;

  function delayAfterFailure() {
    return Math.min(intervalMs * (2 ** Math.min(failures, 30)), Math.max(intervalMs, maxIntervalMs));
  }

  function schedule(delay) {
    if (stopped) return;
    timer = setTimer(() => {
      timer = null;
      void poll();
    }, delay);
  }

  async function poll() {
    if (stopped || inFlight) return;
    inFlight = true;
    try {
      await run();
      failures = 0;
    } catch (error) {
      failures += 1;
      if (!stopped) onError(error);
    } finally {
      inFlight = false;
      if (stopped) return;
      if (refreshPending) {
        refreshPending = false;
        schedule(0);
      } else {
        schedule(failures ? delayAfterFailure() : intervalMs);
      }
    }
  }

  function refresh() {
    if (stopped) return;
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
    if (inFlight) {
      refreshPending = true;
      return;
    }
    void poll();
  }

  function stop() {
    stopped = true;
    refreshPending = false;
    if (timer !== null) clearTimer(timer);
    timer = null;
  }

  void poll();
  return { refresh, stop };
}

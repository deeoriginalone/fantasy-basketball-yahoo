export function createRoomPoller({
  load,
  apply,
  getCurrentVersion,
  onError,
  intervalMs = 5000,
}) {
  let stopped = false;
  let inFlight = false;
  let refreshPending = false;
  let timer = null;
  let controller = null;

  async function poll() {
    if (stopped || inFlight) return;
    inFlight = true;
    const requestController = new AbortController();
    controller = requestController;
    try {
      const value = await load(requestController.signal);
      if (stopped || requestController.signal.aborted) return;
      const currentVersion = getCurrentVersion();
      if (currentVersion === null || value.session.version >= currentVersion) {
        apply(value);
      }
    } catch (error) {
      if (!stopped && error?.name !== "AbortError") onError(error);
    } finally {
      inFlight = false;
      controller = null;
      if (!stopped) {
        if (refreshPending) {
          refreshPending = false;
          void poll();
        } else {
          timer = globalThis.setTimeout(() => void poll(), intervalMs);
        }
      }
    }
  }

  function refresh() {
    if (stopped) return;
    if (timer !== null) {
      globalThis.clearTimeout(timer);
      timer = null;
    }
    if (inFlight) {
      refreshPending = true;
      controller?.abort();
      return;
    }
    void poll();
  }

  function stop() {
    stopped = true;
    refreshPending = false;
    if (timer !== null) globalThis.clearTimeout(timer);
    timer = null;
    controller?.abort();
  }

  void poll();
  return { refresh, stop };
}
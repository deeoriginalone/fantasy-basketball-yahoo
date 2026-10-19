import assert from "node:assert/strict";
import { test } from "node:test";
import { createBackoffPoller } from "./draftSyncPolling.js";

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

function createFakeTimers() {
  let nextId = 0;
  const timers = new Map();
  return {
    timers,
    setTimer(callback, delay) {
      const id = ++nextId;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimer(id) {
      timers.delete(id);
    },
    runNext() {
      const [id, timer] = timers.entries().next().value ?? [];
      if (!timer) return false;
      timers.delete(id);
      timer.callback();
      return true;
    },
    delay() {
      return [...timers.values()][0]?.delay;
    },
  };
}

test("draft sync uses configured interval, bounded backoff, and resets after recovery", async () => {
  const timers = createFakeTimers();
  const failures = [];
  let calls = 0;
  const poller = createBackoffPoller({
    intervalMs: 100,
    maxIntervalMs: 300,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    run: async () => {
      calls += 1;
      if (calls < 3) throw new Error("source unavailable");
    },
    onError: (error) => failures.push(error.message),
  });

  await flush();
  assert.equal(timers.delay(), 200);
  timers.runNext();
  await flush();
  assert.equal(timers.delay(), 300);
  timers.runNext();
  await flush();
  assert.equal(timers.delay(), 100);
  assert.deepEqual(failures, ["source unavailable", "source unavailable"]);
  poller.stop();
});

test("manual refresh waits for an in-flight response instead of overlapping it", async () => {
  const timers = createFakeTimers();
  let calls = 0;
  let finish;
  const poller = createBackoffPoller({
    intervalMs: 100,
    maxIntervalMs: 300,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    run: () => {
      calls += 1;
      return new Promise((resolve) => { finish = resolve; });
    },
    onError: (error) => { throw error; },
  });

  await flush();
  poller.refresh();
  assert.equal(calls, 1);
  finish();
  await flush();
  assert.equal(timers.delay(), 0);
  timers.runNext();
  await flush();
  assert.equal(calls, 2);
  poller.stop();
  finish();
});

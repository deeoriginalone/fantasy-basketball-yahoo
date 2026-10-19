import assert from "node:assert/strict";
import { test } from "node:test";
import { createRoomPoller } from "./roomPolling.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("polling never overlaps requests and aborts stale work on refresh", async () => {
  const pending = [deferred(), deferred()];
  const signals = [];
  const applied = [];
  let calls = 0;
  let currentVersion = 2;
  const poller = createRoomPoller({
    load: (signal) => {
      signals.push(signal);
      return pending[calls++].promise;
    },
    apply: (value) => {
      applied.push(value.session.version);
      currentVersion = value.session.version;
    },
    getCurrentVersion: () => currentVersion,
    onError: (error) => { throw error; },
  });

  await flush();
  assert.equal(calls, 1);
  poller.refresh();
  assert.equal(signals[0].aborted, true);
  assert.equal(calls, 1);

  pending[0].resolve({ session: { version: 3 } });
  await flush();
  assert.equal(calls, 2);
  assert.deepEqual(applied, []);

  pending[1].resolve({ session: { version: 4 } });
  await flush();
  assert.deepEqual(applied, [4]);
  poller.stop();
});

test("a response older than the rendered server version is discarded", async () => {
  const pending = deferred();
  const applied = [];
  const poller = createRoomPoller({
    load: () => pending.promise,
    apply: (value) => applied.push(value.session.version),
    getCurrentVersion: () => 8,
    onError: (error) => { throw error; },
  });

  await flush();
  pending.resolve({ session: { version: 7 } });
  await flush();
  assert.deepEqual(applied, []);
  poller.stop();
});
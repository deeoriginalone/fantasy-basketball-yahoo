import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("./picks.py", import.meta.url), "utf8");
const expression = source.match(/return r"""([\s\S]*?)"""\.replace/)[1]
  .replace("CONFIGURED_SELECTOR", "null");

function readResults({ selected = true, headers = ["Pick", "Player", "Team"],
  entries = [[2, "222"], [1, "111"]], tables = 1 } = {}) {
  const tablist = { getAttribute: () => "tablist" };
  const tab = {
    textContent: "Results",
    parentElement: {
      getAttribute: () => "presentation",
      parentElement: tablist,
    },
    getAttribute: () => selected ? "true" : "false",
  };
  const rows = [
    { cells: headers.map(textContent => ({ textContent })) },
    { cells: [{ textContent: "Round 1" }], querySelector: () => null },
    ...entries.map(([number, id]) => {
      const players = id === null ? [] : [{
        closest: () => null,
        getAttribute: () => id,
      }];
      return {
        cells: [
          { textContent: String(number) },
          { contains: player => players.includes(player) },
          { textContent: "Opponent" },
        ],
        querySelectorAll: () => players,
      };
    }),
  ];
  const table = { rows, getClientRects: () => [1], querySelectorAll: () => [] };
  return vm.runInNewContext(expression, {
    location: {
      protocol: "https:",
      hostname: "basketball.fantasysports.yahoo.com",
      pathname: "/draftclient/nba/50505/9",
    },
    document: {
      querySelectorAll: selector => {
        if (selector.includes('data-id="picks"')) return [];
        if (selector.includes('data-id="results"')) return [tab];
        if (selector === "table") return Array(tables).fill(table);
        throw new Error(`Unexpected selector: ${selector}`);
      },
    },
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
  });
}

test("Results reader sorts descending Yahoo picks by actual pick number", () => {
  const result = readResults();
  assert.deepEqual(Array.from(result.rows, row => row.overall_pick), [1, 2]);
  assert.deepEqual(Array.from(result.rows, row => row.players[0].yahoo_player_id), ["111", "222"]);
  assert.ok(result.rows.every(row => row.row_verified));
});

test("Results reader rejects roster and available-player tables", () => {
  for (const headers of [["Slot", "Player", "Pick"], ["Draft", "Player", "XRank"]]) {
    assert.equal(readResults({ headers }).error, "history_container_not_unique");
  }
});

test("Results reader requires selected Results and exactly one history table", () => {
  assert.equal(readResults({ selected: false }).error, "history_container_not_visible_or_not_narrow");
  assert.equal(readResults({ tables: 2 }).error, "history_container_not_unique");
});

test("Results reader does not fabricate absent identities or renumber gaps", () => {
  const result = readResults({ entries: [[5, "555"], [3, null]] });
  assert.deepEqual(Array.from(result.rows, row => row.overall_pick), [3, 5]);
  assert.equal(result.rows[0].row_verified, false);
  assert.equal(result.rows[0].players.length, 0);
});

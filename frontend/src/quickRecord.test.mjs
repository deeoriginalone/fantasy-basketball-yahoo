import assert from "node:assert/strict";
import { test } from "node:test";
import { findQuickMatches, moveQuickSelection } from "./quickRecord.js";

const players = [
  { player_identity_id: 1, player_name: "De'Aaron Fox", positions: ["PG"] },
  { player_identity_id: 2, player_name: "Nikola Jokić", positions: ["C"] },
  { player_identity_id: 3, player_name: "Paolo Banchero", positions: ["PF", "C"] },
];

test("Quick Record search ignores case, punctuation, and accents", () => {
  assert.equal(findQuickMatches(players, "deaaron").at(0)?.player_identity_id, 1);
  assert.equal(findQuickMatches(players, "JOKIC").at(0)?.player_identity_id, 2);
  assert.equal(findQuickMatches(players, "pf").at(0)?.player_identity_id, 3);
});

test("Quick Record selection clamps Up and Down to the available results", () => {
  assert.equal(moveQuickSelection(0, -1, 3), 0);
  assert.equal(moveQuickSelection(0, 1, 3), 1);
  assert.equal(moveQuickSelection(2, 1, 3), 2);
  assert.equal(moveQuickSelection(2, -1, 3), 1);
  assert.equal(moveQuickSelection(1, 1, 0), 0);
});

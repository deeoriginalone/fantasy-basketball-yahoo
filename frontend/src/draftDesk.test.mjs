import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { sanitizeYahooDraftUrl } from "./yahooConnection.js";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./YahooConnect.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

function component(connection, name = "YahooConnect", extra = {}, chooseMode = false) {
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  let stateIndex = 0;
  const load = name => name === "react" ? {
    ...React,
    useState: initial => {
      const index = stateIndex++;
      return React.useState(index === 2 && chooseMode ? true
        : initial?.status === "CONNECTING" ? connection : initial);
    },
  } : name === "./yahooConnection.js" ? { sanitizeYahooDraftUrl } : require(name);
  new Function("require", "exports", output)(load, exports);
  return renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(exports[name], { connection, busy: false, selectSlot() {}, ...extra })));
}

const ready = { paired: true, status: "SOURCE UNAVAILABLE" };

test("only the existing NBA import gets a bounded long-running proxy timeout", () => {
  const config = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");
  const nba = config.match(/location = \/api\/v1\/nba\/import \{([^}]+)\}/)?.[1];
  assert.ok(nba);
  assert.match(nba, /proxy_pass http:\/\/api:8000;/);
  assert.match(nba, /proxy_read_timeout 600s;/);
  const general = config.match(/location \/api\/ \{([^}]+)\}/)?.[1];
  assert.ok(general);
  assert.ok(!general.includes("proxy_read_timeout"));
});

test("room separates roster utility from wait evidence and explains missing/stale ADP", () => {
  assert.match(app, /BEST PICK NOW · ROSTER UTILITY/);
  assert.match(app, /WAIT ANALYSIS UNAVAILABLE/);
  assert.match(app, /aria-label="Wait analysis"/);
  assert.match(app, /Highest current adjusted roster value/);
  assert.match(app, /Roster utility: \{recommendedPlayer\.utility_score\.toFixed\(2\)\} before mode\/run adjustments/);
  const file = ts.createSourceFile("App.tsx", app, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const row = file.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "PlayerRow");
  const impact = file.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "RosterImpactDetails");
  const status = file.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "YahooPlayerStatus");
  assert.ok(row);
  assert.ok(impact);
  assert.ok(status);
  const output = ts.transpileModule(`${status.getText(file)}\n${impact.getText(file)}\n${row.getText(file)}\nexports.PlayerRow = PlayerRow;`, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("require", "exports", "targetStatuses", output)(require, exports, []);
  const player = {
    player_identity_id: 1, player_name: "Jalen Johnson", positions: ["SF", "PF"],
    data_freshness: "unknown", adp: null, decision_action: "insufficient_evidence",
    value_score: 48.11,
  };
  const render = extra => renderToStaticMarkup(React.createElement("table", null,
    React.createElement("tbody", null, React.createElement(exports.PlayerRow, {
      player: { ...player, ...extra }, busy: false, allowPick: false,
      onRecord() {}, onTarget() {},
    }))));
  assert.match(render({}), /ADP unavailable.*No matched current market record/);
  const stale = render({ data_freshness: "stale", market_data_as_of: "2026-10-10T12:00:00Z" });
  assert.match(stale, /ADP stale.*Last retrieved/);
  assert.ok(!stale.includes("timestamp unavailable"));
  assert.match(render({ data_freshness: "fresh", adp: 10.62, adp_source: "fantrax" }), /10\.6.*fantrax/);
  assert.match(render({}), /Roster comparison unavailable for this saved snapshot/);
  assert.match(render({}), /CURRENT YAHOO STATUS: Unknown/);
  const out = render({
    yahoo_status: "O", yahoo_status_label: "Out (short-term injury)",
    recommendation_eligibility: "excluded",
    yahoo_status_reason: "Not eligible for normal recommendation. Historical value is shown for reference.",
  });
  assert.match(out, /Out \(short-term injury\)/);
  assert.match(out, /Not recommendation eligible/);
  assert.match(out, /Historical value is shown for reference/);
  const explanation = render({ roster_impact: {
    rank_without_roster: 2, rank_with_roster: 4, score_without_roster: 63.81,
    score_change: -1.98, need_without_roster: 70, need_with_roster: 60,
    construction_without_roster: 100, construction_with_roster: 100,
    need_score_change: -1.32, scarcity_need_score_change: -.66, construction_score_change: 0,
  } });
  assert.match(explanation, /Why this rank\? #2 → #4 · roster -1\.98/);
  assert.match(explanation, /only your roster changes/);
  assert.match(explanation, /ADP affects wait analysis, not this ranking/);
});

test("paired desk presents Yahoo URL and Connect, without pairing or mode/configuration forms", () => {
  const html = component(ready);
  assert.match(html, /Yahoo draft URL/);
  assert.match(html, /CONNECT TO YAHOO DRAFT/);
  assert.match(html, /Observer ready/);
  for (const text of ["Pairing code", "INSTALL OBSERVER", "<select", "Draft rounds", "My team"])
    assert.ok(!html.includes(text), text);
});

test("unpaired desk shows one concise first-run card instead of URL connection", () => {
  const html = component({ paired: false, status: "PAIR OBSERVER" });
  assert.match(html, /Yahoo Observer Setup/);
  assert.match(html, /INSTALL OBSERVER/);
  assert.match(html, /One-time pairing code/);
  assert.ok(!html.includes("CONNECT TO YAHOO DRAFT"));
});

test("recent drafts and legacy Advanced are native collapsed disclosures retaining saved-room links", () => {
  const file = ts.createSourceFile("App.tsx", app, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const disclosures = [];
  function visit(node) {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(file) === "details")
      disclosures.push(node);
    ts.forEachChild(node, visit);
  }
  visit(file);
  for (const name of ["Recent Drafts", "Advanced"]) {
    const node = disclosures.find(n => n.children.some(child =>
      ts.isJsxElement(child) && child.openingElement.tagName.getText(file) === "summary"
      && child.getText(file).includes(name)));
    assert.ok(node, name);
    assert.ok(!node.openingElement.attributes.properties.some(p => p.name?.getText(file) === "open"));
    if (name === "Recent Drafts") {
      assert.match(node.getText(file), /sessions\.map/);
      assert.match(node.getText(file), /mockSessions/);
      assert.match(node.getText(file), /mockBatches/);
      assert.match(node.getText(file), /Open run/);
    } else {
      assert.match(node.getText(file), /Choose your league/);
      assert.match(node.getText(file), /form onSubmit=\{createSession\}/);
    }
  }
});

test("internal practice is a secondary action opening existing legacy setup", () => {
  assert.match(app, /Practice without Yahoo/);
  assert.match(app, /Start Internal Mock/);
  assert.match(app, /legacySetupRef\.current\.open = true/);
  assert.match(app, /setDraftSource\("internal_mock"\)/);
});

test("saved mock deletion uses the mock-only API with explicit confirmation", () => {
  assert.match(app, /async function deleteSavedMock\(mock: DraftSession\)/);
  assert.match(app, /window\.confirm\("Delete this mock draft and its picks/);
  assert.match(app, /api\.deleteMockSession\(mock\.session_id\)/);
  assert.match(app, /onClick=\{\(\) => void deleteSavedMock\(mock\)\}/);
});

test("Mock or Real is a small fail-closed question after Connect, not an initial mode screen", () => {
  assert.ok(!component(ready).includes("Is this a Yahoo mock"));
  const html = component(ready, "YahooConnect", {}, true);
  assert.match(html, /Is this a Yahoo mock or your real draft/);
  assert.match(html, />MOCK<\/button>/);
  assert.match(html, />REAL DRAFT<\/button>/);
  assert.ok(!html.includes("<select"));
});

test("missing slot asks only for position buttons and no old configuration", () => {
  const html = component({ id: "room", status: "NEEDS ATTENTION", total_teams: 12 }, "YahooSlotQuestion");
  assert.match(html, /What is your draft position/);
  assert.equal((html.match(/<button /g) ?? []).length, 12);
  assert.ok(!/<input|<select/.test(html));
});

test("resolved slot removes the position question without exposing old setup fields", () => {
  assert.equal(component({ id: "room", status: "NEEDS ATTENTION", user_slot: 10 }, "YahooSlotQuestion"), "");
  const html = component({ ...ready, id: "room", status: "NEEDS ATTENTION", user_slot: 10 });
  assert.ok(!html.includes("What is your draft position"));
  assert.ok(!html.includes("Choose your league"));
  assert.match(html, /rounds could not be verified/);
});

test("pasted auth and fragment cannot enter the displayed or submitted room path", () => {
  const path = sanitizeYahooDraftUrl("https://basketball.fantasysports.yahoo.com/draftclient/nba/123/10?auth=PRIVATE#PRIVATE");
  assert.equal(path, "/draftclient/nba/123/10");
  assert.ok(!JSON.stringify({ room_path: path, mode: "mock" }).includes("PRIVATE"));
  assert.match(source, /event\.preventDefault\(\); acceptUrl\(event\.clipboardData/);
  assert.match(source, /room_path: roomPath/);
});

test("mock complete offers another mock and clears URL before focusing the front door", () => {
  const html = component({ ...ready, mode: "mock", status: "DRAFT ENDED" });
  assert.match(html, /YAHOO MOCK COMPLETE/);
  assert.match(html, /CONNECT ANOTHER MOCK/);
  assert.match(source, /setRoomPath\(""\); setChooseMode\(false\); setWaiting\(false\)/);
  assert.match(source, /inputRef\.current\?\.focus/);
});

test("second paired connection does not ask for installation or pairing again", () => {
  const html = component({ ...ready, id: "second-room", status: "CONNECTING" });
  assert.match(html, /Connecting to Yahoo/);
  assert.ok(!html.includes("Pairing code"));
  assert.ok(!html.includes("INSTALL OBSERVER"));
});

test("active tracking exposes Stop without unpairing or draft deletion", () => {
  const html = component({ ...ready, id: "active-room", status: "SYNCED", court_iq_through: 4 });
  assert.match(html, /STOP TRACKING/);
  assert.ok(!component(ready).includes("STOP TRACKING"));
  assert.match(source, /connection\.id\}\/stop`, "POST"/);
});

test("connection diagnostics are collapsed and Live stays explicitly observe-only", () => {
  const html = component({ ...ready, status: "OBSERVE ONLY" });
  assert.match(html, /Live browser input is observe-only/);
  assert.match(html, /<details class="connection-diagnostics"><summary>/);
  assert.match(html, /Official Yahoo draftresults, Sync Now and Quick Record are unchanged/);
});

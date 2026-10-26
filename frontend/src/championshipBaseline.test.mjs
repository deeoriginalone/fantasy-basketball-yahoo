import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./ChampionshipBaseline.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

test("Championship HQ presents persisted Yahoo rules, roster timestamps, and missing data explicitly", () => {
  const league = {
    league_key: "nba.l.fixture",
    league_name: "Fixture League",
    season: 2026,
    league_imported_at: "2026-10-19T00:00:00Z",
    settings_imported_at: "2026-10-19T00:00:00Z",
    scoring_settings: {
      scoring_type: "head",
      categories: [{ stat_id: "12", name: "PTS", value: 1 }],
    },
    roster_positions: [{ position: "C", count: "1" }],
    teams: [],
  };
  const rosters = [
    {
      league_key: league.league_key,
      team_key: "nba.l.fixture.t.1",
      team_name: "Fixture Team",
      roster_data_status: "available",
      roster_source: "yahoo",
      roster_as_of: "2026-10-19T00:00:00Z",
      players: [{
        id: 10001,
        yahoo_player_id: "123",
        player_name: "Fixture Center",
        team: "DEN",
        position: "C",
        status: null,
        roster_position: "C",
      }],
    },
    {
      league_key: league.league_key,
      team_key: "nba.l.fixture.t.2",
      team_name: "Unrefreshed Team",
      roster_data_status: "not_imported",
      roster_source: null,
      roster_as_of: null,
      players: [],
    },
  ];
  const categoryBaseline = {
    selected_source_season: "2025-26",
    selected_source_stat_type: "Regular Season",
    source_season_selection: "latest_eligible_season_with_rostered_player_stats",
    identity_method: {
      calculation_version: "team-identity-relative-v1",
      minimum_comparable_teams: 3,
      strength_threshold: 75,
      weakness_threshold: 25,
    },
    settings_imported_at: "2026-10-19T00:00:00Z",
    teams: [
        {
          team_key: "nba.l.fixture.t.1",
          team_name: "Fixture Team",
          roster_data_status: "available",
          roster_as_of: "2026-10-19T00:00:00Z",
          roster_player_count: 1,
          mapped_player_count: 0,
          unmapped_player_count: 1,
          categories: [{
            category_id: "12",
            category_name: "PTS",
            status: "partial",
            raw_value: 20,
            calculation_type: "sum_of_player_per_game_rates",
            direction: "higher_is_better",
            reason: null,
            contributing_player_count: 1,
            missing_or_unmapped_player_count: 1,
            missing_players: [{ yahoo_player_id: "123", player_name: "Fixture Center", reason: "unmapped_nba_identity" }],
            source_imports: [],
            numerator_total: null,
            denominator_total: null,
            league_relative: {
              calculation_version: "team-identity-relative-v1",
              minimum_comparable_teams: 3,
              strength_threshold: 75,
              weakness_threshold: 25,
              comparison_status: "sufficient",
              comparable_team_count: 4,
              rank: 2,
              minimum: 10,
              maximum: 40,
              median: 20,
              normalized_position: 33.333,
              direction: "higher_is_better",
              label: "neutral",
              coverage_status: "partial",
              excluded_teams: [{
                team_key: "nba.l.fixture.t.2",
                team_name: "Partial Team",
                coverage_status: "partial",
                reasons: ["partial_category_coverage"],
              }],
              category_meaning: "Points per game, summed across contributing roster players.",
            },
          }],
        },
        {
          team_key: "nba.l.fixture.t.2",
          team_name: "Unrefreshed Team",
          roster_data_status: "not_imported",
          roster_as_of: null,
          roster_player_count: null,
          mapped_player_count: null,
          unmapped_player_count: null,
          categories: [],
        },
      ],
  };
  const state = [league.league_key, league, rosters, categoryBaseline, "nba.l.fixture.t.1", false, false, ""];
  let stateIndex = 0;
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  const load = (name) => name === "react"
    ? {
      ...React,
      useState: () => [state[stateIndex++], () => {}],
      useEffect: () => {},
    }
    : name === "./api"
      ? { api: {} }
      : require(name);
  new Function("require", "exports", output)(load, exports);
  const html = renderToStaticMarkup(React.createElement(exports.ChampionshipBaseline, {
    leagues: [league],
  }));

  assert.match(html, /Yahoo league baseline/);
  assert.match(html, /Yahoo configuration used to interpret future player-value decisions/);
  assert.match(html, /Team identity · league-relative/);
  assert.match(html, /manager-team identity is not verified/);
  assert.match(html, /A roster baseline, not a projection, league percentile, matchup advantage, recommendation, or championship probability/);
  assert.match(html, /<option value="nba.l.fixture.t.2">Unrefreshed Team<\/option>/);
  assert.match(html, /Rank 2 of 4 fully covered teams/);
  assert.match(html, /33 \/ 100/);
  assert.match(html, /neutral/);
  assert.match(html, /Points per game, summed across contributing roster players/);
  assert.match(html, /Excluded teams \(1\)/);
  assert.match(html, /Partial Team: partial · partial category coverage/);
  assert.match(html, /20/);
  assert.match(html, /1 missing\/unmapped/);
  assert.match(html, /Fixture Center: no NBA identity mapping/);
  assert.match(html, /1 × C/);
  assert.match(html, /Fixture Center · C/);
  assert.match(html, /Unrefreshed Team/);
  assert.match(html, /roster unknown · not imported/);
  assert.match(html, /Roster not imported; missing data does not mean an empty roster/);
  assert.match(html, /Matchup and transaction context is not included/);
  assert.match(html, /Raw category evidence/);
  assert.doesNotMatch(html, /My Team/);
  assert.match(source, /await api\.importLeagues\(\);\s*await api\.importPlayers\(leagueKey\);/);
  assert.match(app, /BUILD YOUR CHAMPIONSHIP BASELINE/);
  assert.ok(app.indexOf("<ChampionshipBaseline") < app.indexOf("<YahooConnect />"));
});

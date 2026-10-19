import assert from "node:assert/strict";
import { test } from "node:test";
import { sanitizeYahooDraftUrl } from "./yahooConnection.js";

test("Yahoo connection sends only an exact non-secret draft room path", () => {
  assert.equal(sanitizeYahooDraftUrl(
    "https://basketball.fantasysports.yahoo.com/draftclient/nba/123/10?auth=never-send#secret"
  ), "/draftclient/nba/123/10");
});

test("Yahoo connection rejects lobby, lookalike hosts and URL credentials", () => {
  for (const url of [
    "https://basketball.fantasysports.yahoo.com/nba/50505/mock_lobby",
    "https://basketball.fantasysports.yahoo.com.evil.example/draftclient/nba/123/10",
    "http://basketball.fantasysports.yahoo.com/draftclient/nba/123/10",
    "https://user:password@basketball.fantasysports.yahoo.com/draftclient/nba/123/10",
    "https://basketball.fantasysports.yahoo.com:9222/draftclient/nba/123/10",
  ]) assert.throws(() => sanitizeYahooDraftUrl(url));
});

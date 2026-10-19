"""Bounded Yahoo Picks DOM parsing and volatile candidate history."""

import json
import re


def expression(history_selector=None):
    return r"""(() => {
if (location.protocol !== 'https:' || location.hostname !== 'basketball.fantasysports.yahoo.com'
    || !/^\/draftclient\/nba\/\d+\/\d+\/?$/.test(location.pathname))
  return {error:'not_draft_document'};
function observed(root, rows) {
  const key='__courtIqCandidatePicksV1';
  if (!globalThis[key] || globalThis[key].root !== root) {
    if (globalThis[key]) globalThis[key].observer.disconnect();
    const state={root, changedAt:null};
    state.observer=new MutationObserver(() => {
      if (state.changedAt === null) state.changedAt=Date.now();
    });
    state.observer.observe(root,{subtree:true,childList:true,attributes:true,characterData:true});
    globalThis[key]=state;
  }
  const changedAt=globalThis[key].changedAt;
  globalThis[key].changedAt=null;
  return {rows,changed_at:changedAt};
}
const buttons = [...document.querySelectorAll('button[role="tab"][data-id="picks"]')]
  .filter(e => e.textContent.trim() === 'Picks' && e.parentElement?.getAttribute('role') === 'tablist');
if (!buttons.length) {
  const results=[...document.querySelectorAll('button[role="tab"][data-id="results"]')]
    .filter(e => e.textContent.trim() === 'Results'
      && e.parentElement?.getAttribute('role') === 'presentation'
      && e.parentElement.parentElement?.getAttribute('role') === 'tablist');
  if (results.length !== 1) return {error:'picks_control_not_unique'};
  if (results[0].getAttribute('aria-selected') !== 'true')
    return {error:'history_container_not_visible_or_not_narrow'};
  const tables=[...document.querySelectorAll('table')].filter(table =>
    table.getClientRects().length && table.rows.length
    && [...table.rows[0].cells].map(cell=>cell.textContent.trim()).join('|') === 'Pick|Player|Team');
  if (tables.length !== 1) return {error:'history_container_not_unique'};
  const root=tables[0];
  if (root.querySelectorAll('*').length > 15000) return {error:'history_container_too_large'};
  const rows=[];
  for (const row of [...root.rows].slice(1)) {
    const cells=[...row.cells];
    if (cells.length === 1 && /^Round \d+$/i.test(cells[0].textContent.trim())
        && !row.querySelector('.ys-player[data-id]')) continue;
    if (cells.length !== 3 || !/^\d{1,3}$/.test(cells[0].textContent.trim()))
      return {error:'ambiguous_numbered_entry'};
    const players=[...row.querySelectorAll('.ys-player[data-id]')];
    rows.push({
      overall_pick:Number(cells[0].textContent.trim()),
      row_verified:players.length === 1 && cells[1].contains(players[0]),
      players:players.map(player=>({
        semantic_player:true,
        excluded:!!player.closest('button,.ys-team,.ys-queue,[role="tab"],[data-id="queue"]'),
        yahoo_player_id:player.getAttribute('data-id')
      }))
    });
  }
  if (!rows.length) return {error:'no_numbered_pick_rows'};
  rows.sort((a,b)=>a.overall_pick-b.overall_pick);
  return observed(root,rows);
}
if (buttons.length !== 1) return {error:'picks_control_not_unique'};
const button = buttons[0];
const configured = CONFIGURED_SELECTOR;
const controlled = button.getAttribute('aria-controls');
let roots = configured ? [...document.querySelectorAll(configured)] :
  controlled ? [document.getElementById(controlled)].filter(Boolean) : [];
if (!configured && !controlled) {
  const wrapper=button.parentElement.parentElement, host=wrapper?.parentElement;
  if (wrapper?.children.length === 1 && host?.children.length === 2)
    roots=[...host.children].filter(e => e !== wrapper);
}
const excluded='.ys-team,.ys-queue,button,nav,[role="tab"],[role="tablist"],[role="navigation"],[data-id="queue"],[data-id="picks"]';
if (roots.length !== 1) return {error:'history_container_not_unique'};
const root=roots[0];
if (root === document.body || root === document.documentElement || root.contains(button)
    || root.closest(excluded) || !root.getClientRects().length)
  return {error:'history_container_not_visible_or_not_narrow'};
const nodes=[...root.querySelectorAll('*')];
if (nodes.length > 15000) return {error:'history_container_too_large'};
const numbered=nodes.filter(e => !e.children.length && /^\d{1,3}\.?$/.test(e.textContent.trim())
  && !e.closest('.ys-player') && !e.closest(excluded));
const rows=[];
const rowElements=new Set();
for (const indicator of numbered) {
  let row=indicator.parentElement;
  // Stop at the nearest numbered-entry ancestor, never combine neighboring entries.
  while (row && row !== root && !row.querySelector('.ys-player[data-id]')) {
    if (numbered.filter(n => row.contains(n)).length !== 1) break;
    row=row.parentElement;
  }
  if (!row || row === root || row.closest(excluded)
      || numbered.filter(n => row.contains(n)).length !== 1) {
    rows.push({overall_pick:Number(indicator.textContent.trim().replace(/\.$/,'')),
      players:[], row_verified:false});
    continue;
  }
  if (rowElements.has(row)) return {error:'ambiguous_numbered_entry'};
  rowElements.add(row);
  const players=[...row.querySelectorAll('.ys-player[data-id]')].map(player => ({
    semantic_player:player.classList.contains('ys-player'),
    excluded:!!player.closest(excluded),
    yahoo_player_id:player.getAttribute('data-id')
  }));
  rows.push({overall_pick:Number(indicator.textContent.trim().replace(/\.$/,'')),
    row_verified:true, players});
}
if (!rows.length) return {error:'no_numbered_pick_rows'};
// Every semantic player in this subtree must belong to exactly one numbered entry.
if ([...root.querySelectorAll('.ys-player[data-id]')].some(player =>
    ![...rowElements].some(row => row.contains(player))))
  return {error:'player_without_numbered_entry'};
return observed(root,rows);
})()""".replace("CONFIGURED_SELECTOR", json.dumps(history_selector))


DIRTY_EXPRESSION = (
    "(() => { const s=globalThis.__courtIqCandidatePicksV1;"
    "return !s || !s.root.isConnected || s.changedAt !== null; })()"
)


def parse(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("malformed_history_snapshot")
    if snapshot.get("error"):
        allowed = {
            "not_draft_document", "picks_control_not_unique", "history_container_not_unique",
            "history_container_not_visible_or_not_narrow", "history_container_too_large",
            "ambiguous_numbered_entry", "no_numbered_pick_rows", "player_without_numbered_entry",
        }
        reason = snapshot["error"]
        raise ValueError(reason if reason in allowed else "unrecognized_history_error")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("no_numbered_pick_rows")
    picks, ids, previous, gaps = [], set(), None, []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed_pick_row")
        number = row.get("overall_pick")
        if type(number) is not int or not 1 <= number <= 600:
            raise ValueError("invalid_overall_pick")
        if previous is not None and number <= previous:
            raise ValueError("duplicate_or_nonascending_pick")
        if previous is not None and number != previous + 1:
            gaps.append([previous + 1, number - 1])
        players = row.get("players")
        if row.get("row_verified") is not True or not isinstance(players, list) or len(players) != 1:
            raise ValueError(f"pick_{number}_requires_exactly_one_ys_player")
        player = players[0]
        if not isinstance(player, dict) or player.get("semantic_player") is not True or player.get("excluded") is not False:
            raise ValueError(f"pick_{number}_team_or_ui_not_player")
        yahoo_id = player.get("yahoo_player_id")
        if not isinstance(yahoo_id, str) or not re.fullmatch(r"[0-9]{1,12}", yahoo_id):
            raise ValueError(f"pick_{number}_invalid_ys_player_id")
        if yahoo_id in ids:
            raise ValueError("duplicate_yahoo_player_id")
        ids.add(yahoo_id)
        picks.append({"overall_pick": number, "yahoo_player_id": yahoo_id})
        previous = number
    return picks, gaps


class CandidateHistory:
    def __init__(self):
        self.seen = {}

    def check(self, picks):
        current = {pick["overall_pick"]: pick["yahoo_player_id"] for pick in picks}
        if any(current.get(number) != yahoo_id for number, yahoo_id in self.seen.items()):
            raise ValueError("previous_pick_changed_or_disappeared")
        return [pick for pick in picks if pick["overall_pick"] not in self.seen]

    def accept(self, picks):
        self.seen = {pick["overall_pick"]: pick["yahoo_player_id"] for pick in picks}


def mapping_report(picks, identities):
    if not isinstance(identities, list):
        raise ValueError("invalid_court_iq_identity_response")
    mappings = {}
    for identity in identities:
        if not isinstance(identity, dict) or not isinstance(identity.get("yahoo_player_id"), str):
            raise ValueError("invalid_court_iq_identity_response")
        mappings.setdefault(identity["yahoo_player_id"], set()).add(identity.get("id"))
    unmapped, ambiguous = [], []
    for pick in picks:
        yahoo_id = pick["yahoo_player_id"]
        matches = mappings.get(yahoo_id, set())
        if not matches:
            unmapped.append(yahoo_id)
        elif len(matches) != 1 or any(type(identity_id) is not int for identity_id in matches):
            ambiguous.append(yahoo_id)
    return {
        "total_numbered_rows": len(picks), "valid_numeric_ys_player_ids": len(picks),
        "uniquely_mapped": len(picks) - len(unmapped) - len(ambiguous),
        "unmapped_ids": unmapped, "ambiguous_ids": ambiguous,
    }

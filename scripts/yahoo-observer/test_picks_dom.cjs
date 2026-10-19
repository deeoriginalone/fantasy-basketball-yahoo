// Minimal DOM contract fixtures; actual Yahoo rendering still requires Windows evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(0, 'utf8');

class Element {
  constructor(tag, text = '', classes = [], attrs = {}, children = []) {
    this.tagName = tag;
    this.text = text;
    this.classes = classes;
    this.attrs = attrs;
    this.children = children;
    this.classList = {contains: c => classes.includes(c)};
    this.isConnected = true;
    for (const child of children) child.parentElement = this;
  }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  matches(selector) {
    return selector.split(',').some(s => {
      const tag = s.match(/^[a-z]+/i)?.[0];
      const cls = s.match(/\.([a-z-]+)/i)?.[1];
      const attributes = [...s.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)];
      return (!tag || this.tagName === tag.toUpperCase())
        && (!cls || this.classes.includes(cls))
        && attributes.every(([, key, value]) => key in this.attrs
          && (value === undefined || this.attrs[key] === value));
    });
  }
  closest(selector) {
    for (let e = this; e; e = e.parentElement) if (e.matches(selector)) return e;
    return null;
  }
  contains(element) {
    return this === element || this.children.some(c => c.contains(element));
  }
  querySelectorAll(selector) {
    return this.children.flatMap(c => [
      ...(selector === '*' || c.matches(selector) ? [c] : []), ...c.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  getClientRects() { return [{}]; }
}

const player = (id, classes = ['ys-player']) =>
  new Element('DIV', 'Player', classes, {'data-id': id});
const row = (number, players) =>
  new Element('DIV', '', [], {}, [new Element('SPAN', `${number}.`), ...players]);

function read(rows) {
  const button = new Element('BUTTON', 'Picks', [], {'role':'tab', 'data-id':'picks'});
  const tablist = new Element('DIV', '', [], {'role':'tablist'}, [button]);
  const wrapper = new Element('DIV', '', [], {}, [tablist]);
  const root = new Element('DIV', '', [], {}, rows);
  const host = new Element('DIV', '', [], {}, [wrapper, root]);
  const body = new Element('BODY', '', [], {}, [host]);
  const html = new Element('HTML', '', [], {}, [body]);
  const context = {
    document: {body, documentElement: html, querySelectorAll: s => html.querySelectorAll(s)},
    location: {protocol:'https:', hostname:'basketball.fantasysports.yahoo.com',
      pathname:'/draftclient/nba/123/9'},
    MutationObserver: class { observe() {} disconnect() {} },
    Date,
  };
  return vm.runInNewContext(source, context);
}

let result = read([row(30, [player('5827')]), row(31, [player('4612')])]);
assert.equal(result.rows.length, 2);
assert.equal(result.rows[0].overall_pick, 30);
assert.equal(result.rows[0].players[0].yahoo_player_id, '5827');
assert.equal(result.rows[1].overall_pick, 31);
assert.equal(result.rows[0].row_verified, true);
for (const id of ['queue', 'picks']) {
  result = read([row(30, [player(id)])]);
  // Exclusion is retained in metadata, so the Python boundary rejects the whole row.
  assert.equal(result.rows[0].players[0].excluded, true);
}
result = read([row(30, [player('1', ['ys-player', 'ys-team'])])]);
assert.equal(result.rows[0].players[0].excluded, true);
result = read([row(30, [player('1', ['ys-team'])])]);
assert.equal(result.rows[0].row_verified, false);
result = read([row(30, [])]);
assert.equal(result.rows[0].row_verified, false);
result = read([row(30, [player('5827'), player('4612')])]);
assert.equal(result.rows[0].players.length, 2);
assert(!JSON.stringify(result).includes('auth='));
console.log('DOM parser fixtures passed');

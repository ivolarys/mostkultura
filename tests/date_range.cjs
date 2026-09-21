const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const range = require('../mostek_kultura/static/date-range.js');

for (const value of ['2026-02-28', '2024-02-29', '0001-01-01', '9999-12-31']) {
  assert.equal(range.validISODate(value), true, `${value} must be valid`);
}
for (const value of ['', '2026-2-3', '2026-02-30', '0000-01-01', '2026-13-01', 'date']) {
  assert.equal(range.validISODate(value), false, `${value} must be rejected`);
}

assert.deepEqual(range.normalizeRange('2026-09-24', '2026-09-21', '2026-09-20'),
  ['2026-09-21', '2026-09-24']);
assert.deepEqual(range.normalizeRange('bad', '2026-09-24', '2026-09-20'),
  ['2026-09-20', '2026-09-24']);
assert.deepEqual(range.normalizeRange('2026-09-24', 'bad', '2026-09-20'),
  ['2026-09-24', '2026-09-24']);
assert.equal(range.addDays('2026-01-31', 1), '2026-02-01');
assert.equal(range.addDays('2024-02-28', 1), '2024-02-29');
assert.equal(range.addDays('bad', 1), null);
assert.equal(range.length('2026-09-30', '2026-10-02'), 3);

// A stable anchor must keep working when a range crosses it and then contracts.
const anchor = '2026-10-03';
assert.deepEqual(range.normalizeRange(anchor, '2026-10-01', anchor), ['2026-10-01', anchor]);
assert.deepEqual(range.normalizeRange(anchor, '2026-10-04', anchor), [anchor, '2026-10-04']);

// Evaluate the production state parser and counter, rather than a duplicate
// implementation, to keep URL and range integration under contract.
const template = fs.readFileSync(path.join(__dirname, '../mostek_kultura/templates/index.html.j2'), 'utf8');
const take = (start, end) => {
  const from = template.indexOf(start);
  assert.notEqual(from, -1, `missing ${start}`);
  const to = template.indexOf(end, from);
  assert.notEqual(to, -1, `missing boundary ${end}`);
  return template.slice(from, to);
};
const line = start => {
  const from = template.indexOf(start);
  assert.notEqual(from, -1, `missing ${start}`);
  return template.slice(from, template.indexOf('\n', from));
};
const productionStateCode = [
  'const dateRange=globalThis.dateRange;',
  'const today=globalThis.today;',
  'const VALID=globalThis.VALID;',
  'const qs=globalThis.qs;',
  'const validPlaces=globalThis.validPlaces;',
  'const LEGACY_PLACE_MAP={};',
  'const sourcePrefs={disabledPlaces:[]};',
  'const disabledPlaceSet=()=>new Set(sourcePrefs.disabledPlaces);',
  'const collator={compare:(a,b)=>a.localeCompare(b)};',
  'const embed=false;',
  'const TABS=globalThis.TABS;',
  'const EVENTS=globalThis.EVENTS;',
  'const sourceAllowed=globalThis.sourceAllowed;',
  'const norm=globalThis.norm;',
  line('const st='),
  line('const validISODate='),
  take('function parseState()', 'function stateHash()'),
  take('function stateHash()', 'function canonicalize()'),
  take('function rangeFor(', 'function relevant('),
  take('function relevant(', 'function matches('),
  take('function matches(', 'function visibleEvents('),
  take('function computeRenderSnapshot()', 'function placeSearchMatch()'),
  'globalThis.__stateApi={st,parseState,stateHash,rangeFor,computeRenderSnapshot};',
].join('\n');

function productionState({hash = '', query = '', events = []} = {}) {
  const context = {
    dateRange: range,
    today: '2026-09-20',
    URLSearchParams,
    qs: new URLSearchParams(query),
    location: {hash},
    VALID: {
      tab: new Set(['today', 'tomorrow', 'weekend', 'week', 'all', 'date']),
      cat: new Set(), group: new Set(['category']), view: new Set(['list']),
    },
    validPlaces: new Set(),
    TABS: [['today', 'Dnes', ['2026-09-20', '2026-09-20']]],
    EVENTS: events,
    sourceAllowed: () => true,
    norm: value => value,
  };
  vm.runInNewContext(productionStateCode, context);
  context.__stateApi.parseState();
  return context.__stateApi;
}

let state = productionState({hash: '#tab=date&date=2026-09-24&end=2026-09-21'});
assert.deepEqual([state.st.date, state.st.dateEnd], ['2026-09-21', '2026-09-24']);
assert.match(state.stateHash(), /(?:^|&)date=2026-09-21(?:&|$)/);
assert.match(state.stateHash(), /(?:^|&)end=2026-09-24(?:&|$)/);

state = productionState({query: 'tab=date&date=2024-02-28&end=2024-02-29'});
assert.deepEqual([state.st.date, state.st.dateEnd], ['2024-02-28', '2024-02-29']);

state = productionState({hash: '#tab=date&date=2026-10-01', query: 'tab=date&date=2026-09-21&end=2026-09-24'});
assert.deepEqual([state.st.date, state.st.dateEnd], ['2026-10-01', '2026-10-01']);

state = productionState({hash: '#tab=date&date=2026-09-21&end=not-a-date'});
assert.deepEqual([state.st.date, state.st.dateEnd], ['2026-09-21', '2026-09-21']);

state = productionState({
  hash: '#tab=date&date=2026-09-21&end=2026-09-23',
  events: [
    {sd: '2026-09-21', ed: '2026-09-21', ongoing: false, category: 'jine', search: ''},
    {sd: '2026-09-23', ed: '2026-09-23', ongoing: false, category: 'jine', search: ''},
    {sd: '2026-09-19', ed: '2026-09-22', ongoing: true, category: 'jine', search: ''},
    {sd: '2026-09-24', ed: '2026-09-24', ongoing: false, category: 'jine', search: ''},
  ],
});
assert.equal(state.computeRenderSnapshot().tabCounts.date, 3, 'range counter includes endpoints and overlap only');
console.log('Date-range contract passed: strict ISO dates, canonical bounds and UTC day arithmetic.');

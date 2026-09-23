const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const values = new Map();
const storage = {
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
};
const sandbox = {localStorage: storage};
sandbox.window = sandbox;
vm.createContext(sandbox);
const source = fs.readFileSync('mostek_kultura/static/favorites.js', 'utf8');
function load() {
  vm.runInContext(source, sandbox);
  return sandbox.MostkulturaFavorites;
}
const favorites = load();
const plain = value => JSON.parse(JSON.stringify(value));
const event = (id, start, extra = {}) => ({id, start, title: id, all_day: false, end: null, ...extra});
const first = event('shared', '2026-09-23T18:00:00+02:00');
const second = event('shared', '2026-09-24T18:00:00+02:00');

assert.equal(favorites.KEY, 'mostkultura.favorites.v1');
assert.deepEqual(plain(favorites.read()), []);
assert.equal(values.has(favorites.KEY), false);
assert.notEqual(favorites.key(first), favorites.key(second));
assert.equal(favorites.key(event('', first.start)), null);
assert.equal(favorites.key(event('bad', '2026-02-30T18:00:00+01:00')), null);
assert.deepEqual(plain(favorites.normalize(['a', 'a', '', null, 12, 'b'])), ['a', 'b']);
assert.deepEqual(plain(favorites.normalize({keys: ['a']})), []);
for (const malformed of ['{oops', 'null', '{}', '"a"', '42']) {
  values.set(favorites.KEY, malformed);
  assert.deepEqual(plain(favorites.read()), []);
}

let keys = favorites.toggle([], first);
assert.equal(favorites.has(keys, first), true);
assert.equal(favorites.has(keys, second), false);
keys = favorites.toggle(keys, second);
assert.deepEqual(plain(keys), [favorites.key(first), favorites.key(second)]);
keys = favorites.toggle(keys, first);
assert.deepEqual(plain(keys), [favorites.key(second)]);
assert.deepEqual(plain(favorites.toggle(keys, {id: 'bad', start: 'broken'})), plain(keys));
assert.equal(favorites.save([favorites.key(second), favorites.key(second)]), true);
assert.deepEqual(plain(favorites.read()), [favorites.key(second)]);
assert.equal(load().has(load().read(), second), true);
assert.equal(favorites.save([favorites.key(first), favorites.key(second), 'temporarily-missing']), true);

const now = Date.parse('2026-09-23T16:00:00Z'); // 18:00 in Prague
assert.equal(favorites.isUpcoming(first, now), true);
assert.equal(favorites.isUpcoming(first, now + 1), false);
assert.equal(favorites.isUpcoming(event('range', '2026-09-23T10:00:00+02:00',
  {end: '2026-09-23T20:00:00+02:00'}), now), true);
assert.equal(favorites.isUpcoming(event('range', '2026-09-23T10:00:00+02:00',
  {end: '2026-09-23T09:00:00+02:00'}), now), false);
assert.equal(favorites.isUpcoming(event('invalid', first.start, {end: 'nonsense'}), now), false);
assert.equal(favorites.isUpcoming(event('invalid', first.start, {end: ''}), now), false);
assert.equal(favorites.isUpcoming(event('invalid', 'not-a-date'), now), false);

const day = (start, end = null) => event(start, `${start}T00:00:00+02:00`,
  {all_day: true, end: end ? `${end}T23:59:00+02:00` : null});
const midnightPrague = Date.parse('2026-09-30T22:30:00Z'); // Oct 1 in Prague
assert.equal(favorites.isUpcoming(day('2026-09-30'), midnightPrague), false);
assert.equal(favorites.isUpcoming(day('2026-09-30'), midnightPrague, 'UTC'), true);
assert.equal(favorites.isUpcoming(day('2026-09-30', '2026-10-01'), midnightPrague), true);
assert.equal(favorites.isUpcoming(day('2026-12-31', '2027-01-01'),
  Date.parse('2027-01-01T21:00:00Z')), true);
assert.equal(favorites.isUpcoming(day('2026-12-31', '2027-01-01'),
  Date.parse('2027-01-01T23:00:00Z')), false);
assert.equal(favorites.isUpcoming(day('2026-10-02', '2026-10-01'), midnightPrague), false);
assert.equal(favorites.isUpcoming(day('2026-09-30', '2026-10-40'), midnightPrague), false);

const aaa = event('a', '2026-09-24T18:00:00+02:00', {title: 'Árie'});
const zzz = event('z', '2026-09-24T18:00:00+02:00', {title: 'Živě'});
const elapsed = event('elapsed', '2026-09-22T10:00:00+02:00');
const missing = event('missing', '2026-09-25T18:00:00+02:00');
const saved = [favorites.key(first), favorites.key(second), favorites.key(aaa),
  favorites.key(zzz), favorites.key(elapsed), favorites.key(missing)];
const current = [zzz, elapsed, second, aaa, first];
assert.deepEqual(plain(favorites.selected(current, saved, now + 1)),
  [plain(aaa), plain(second), plain(zzz)]);
assert.equal(saved.includes(favorites.key(missing)), true);
assert.deepEqual(plain(favorites.selected(null, saved, now)), []);
assert.deepEqual(plain(favorites.read()), [favorites.key(first), favorites.key(second), 'temporarily-missing']);

Object.defineProperty(sandbox, 'localStorage', {
  configurable: true, get() { throw new Error('security'); },
});
assert.deepEqual(plain(favorites.read()), []);
assert.equal(favorites.save(saved), false);
Object.defineProperty(sandbox, 'localStorage', {
  configurable: true, value: {getItem: () => null, setItem() { throw new Error('quota'); }},
});
assert.equal(favorites.save(saved), false);
console.log('Favorites contract passed: identity, persistence, timezone, expiry and payload selection.');

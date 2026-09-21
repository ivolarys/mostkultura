const assert = require('node:assert/strict');
const search = require('../mostek_kultura/static/place-search.js');

const events = [
  {title:'Koncert bez názvu místa', place:'Hradec Králové', venue:'Knihovna'},
  {title:'Hořický večer', place:'Hořice'},
  {title:'Trh', place:'Trutnov'},
];
const places = ['Hradec Králové', 'Hořice', 'Trutnov'];

assert.equal(search.find('Koncert', places, events), null, 'title-only search must not offer place results');
assert.equal(search.find('Hradec', places, events).place, 'Hradec Králové');
assert.equal(search.find('hradec kralove', places, events).place, 'Hradec Králové');
assert.equal(search.find('knihovna', places, events).place, 'Knihovna');
assert.equal(search.find('h', places, events), null, 'one character is too broad');
assert.equal(search.find('Hradec Králové – divadlo', places, events), null, 'the query must be part of a place, not vice versa');
assert.equal(search.find('neznámé', places, events), null);
assert.equal(search.normalize('Hořice'), 'horice');

const hK=search.find('hradec', places, events);
assert.deepEqual(search.panelState({match:hK,tab:'today',currentCount:0,allCount:2}),
  {type:'cta',currentCount:0,allCount:2}, 'future events get a CTA even when today is empty');
assert.deepEqual(search.panelState({match:hK,tab:'tomorrow',currentCount:1,allCount:2}),
  {type:'cta',currentCount:1,allCount:2}, 'CTA remains when the current period has events');
assert.deepEqual(search.panelState({match:hK,tab:'weekend',currentCount:0,allCount:0}),
  {type:'empty'}, 'no filtered or selected-source events gives one clear message');
assert.equal(search.panelState({match:hK,tab:'week',currentCount:0,allCount:2}), null, 'week has no CTA');
assert.deepEqual(search.panelState({match:hK,tab:'all',currentCount:0,allCount:0}), {type:'empty'});
assert.equal(search.panelState({match:null,tab:'today',currentCount:0,allCount:3}), null, 'title-only search has no CTA');
console.log('Place-search contract passed: locations only, partial matches and diacritics.');

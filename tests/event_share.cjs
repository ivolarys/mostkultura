const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = { URL, URLSearchParams, Intl, Date, Promise };
vm.createContext(context);
vm.runInContext(fs.readFileSync('mostek_kultura/static/event-share.js', 'utf8'), context);
const share = context.MostkulturaEventShare;
const event = {
  title: 'Večer & hudba', start: '2026-09-25T19:30:00+02:00',
  sd: '2026-09-25', ed: '2026-09-25', venue: 'Sál', place: 'Mostek',
  url: 'https://example.org/akce?id=7',
};

async function run() {
  assert.equal(share.publicUrl(event), event.url);
  const data = share.payload(event);
  assert.equal(data.title, event.title);
  assert.match(data.text, /Večer & hudba\n25\. 9\. 2026, 19:30\nSál · Mostek/);
  assert.equal(data.url, event.url);

  for (const url of ['javascript:alert(1)', '/relative', 'ftp://example.org/akce', '']) {
    const link = share.publicUrl({ ...event, url });
    assert.equal(link, 'https://ivolarys.github.io/mostkultura/#tab=date&date=2026-09-25&q=Ve%C4%8Der+%26+hudba');
    assert.ok(!link.includes('favorites') && !link.includes('embed') && !link.includes('source'));
  }
  const offsetLink = share.publicUrl({
    ...event, sd: undefined, url: '', start: '2026-09-24T23:30:00-01:00',
  });
  assert.match(offsetLink, /#tab=date&date=2026-09-25&/);

  let inClick = true;
  const native = share.share(event, { navigator: { share(payload) {
    assert.equal(inClick, true);
    assert.equal(payload.url, event.url);
    return Promise.resolve();
  } } });
  inClick = false;
  assert.equal(await native, 'shared');

  let copied = 0, manual = 0;
  const callbacks = { onCopied: () => copied++, onManual: () => manual++ };
  assert.equal(await share.share(event, {
    ...callbacks, navigator: {
      share: () => Promise.reject({ name: 'AbortError' }),
      clipboard: { writeText: () => { throw new Error('cancel must not copy'); } },
    },
  }), 'cancelled');
  assert.equal(copied, 0);
  assert.equal(manual, 0);

  assert.equal(await share.share(event, {
    ...callbacks, navigator: {
      share: () => Promise.reject({ name: 'NotAllowedError' }),
      clipboard: { writeText: url => { assert.equal(url, event.url); return Promise.resolve(); } },
    },
  }), 'copied');
  assert.equal(copied, 1);

  assert.equal(await share.share(event, {
    ...callbacks, navigator: { clipboard: { writeText: () => Promise.reject(new Error('denied')) } },
  }), 'manual');
  assert.equal(manual, 1);
}

run().catch(error => { console.error(error); process.exitCode = 1; });

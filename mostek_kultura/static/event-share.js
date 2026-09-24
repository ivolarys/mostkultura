/* Build a public event link without carrying local filters or source preferences. */
(function (global) {
  'use strict';

  const PUBLIC_URL = 'https://ivolarys.github.io/mostkultura/';
  const dayFormatter = new Intl.DateTimeFormat('cs-CZ', {
    day: 'numeric', month: 'numeric', year: 'numeric', timeZone: 'Europe/Prague',
  });
  const timeFormatter = new Intl.DateTimeFormat('cs-CZ', {
    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Prague',
  });
  const isoFormatter = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Prague' });

  function publicUrl(event) {
    try {
      const url = new URL(event.url);
      if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
    } catch (_) { /* Use the public search link below. */ }
    const params = new URLSearchParams({ tab: 'date', date: event.sd || isoFormatter.format(new Date(event.start)), q: event.title });
    return `${PUBLIC_URL}#${params}`;
  }

  function payload(event) {
    const title = String(event.title || '').trim();
    const start = new Date(event.start);
    const startDay = event.sd || isoFormatter.format(start);
    const endDay = event.ed || (event.end ? isoFormatter.format(new Date(event.end)) : startDay);
    const day = dayFormatter.format(new Date(`${startDay}T12:00:00Z`));
    const end = endDay !== startDay ? `–${dayFormatter.format(new Date(`${endDay}T12:00:00Z`))}` : '';
    const when = event.all_day ? `${day}${end}, celý den` : `${day}${end}, ${timeFormatter.format(start)}`;
    const where = [event.venue, event.place].filter((value, index, items) => value && items.indexOf(value) === index).join(' · ');
    return { title, text: [title, when, where].filter(Boolean).join('\n'), url: publicUrl(event) };
  }

  function share(event, options = {}) {
    const nav = options.navigator || global.navigator || {};
    const data = payload(event);
    // This call must happen in the original click task to retain transient activation.
    let nativeShare;
    try {
      if (typeof nav.share === 'function') nativeShare = nav.share(data);
    } catch (error) { nativeShare = Promise.reject(error); }
    if (nativeShare) {
      return Promise.resolve(nativeShare).then(() => 'shared', error => {
        if (error?.name === 'AbortError') return 'cancelled';
        return copy(data.url, nav, options);
      });
    }
    return copy(data.url, nav, options);
  }

  function copy(url, nav, options) {
    let copied;
    try { copied = nav.clipboard?.writeText(url); }
    catch (_) { copied = Promise.reject(); }
    if (!copied) copied = Promise.reject();
    return Promise.resolve(copied).then(() => {
      options.onCopied?.(url);
      return 'copied';
    }, () => {
      options.onManual?.(url);
      return 'manual';
    });
  }

  global.MostkulturaEventShare = { PUBLIC_URL, publicUrl, payload, share };
})(typeof window !== 'undefined' ? window : globalThis);

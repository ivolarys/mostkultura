/* Local favorites contain event identities only; event details come from the current build. */
(function (global) {
  'use strict';

  const KEY = 'mostkultura.favorites.v1';
  const ISO_DATE = /^(?!0000)\d{4}-\d{2}-\d{2}$/;
  const ISO_START = /^(?!0000)\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$/;

  function validDate(value) {
    if (typeof value !== 'string' || !ISO_DATE.test(value)) return false;
    const parsed = new Date(`${value}T12:00:00Z`);
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }

  function timestamp(value) {
    if (typeof value !== 'string' || !ISO_START.test(value) || !validDate(value.slice(0, 10))) return NaN;
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : NaN;
  }

  function key(event) {
    if (!event || typeof event.id !== 'string' || !event.id.trim()
        || !Number.isFinite(timestamp(event.start))) return null;
    return JSON.stringify([event.id, event.start]);
  }

  function normalize(value) {
    return Array.isArray(value)
      ? [...new Set(value.filter(item => typeof item === 'string' && item.length > 0))]
      : [];
  }

  function read() {
    try {
      const raw = global.localStorage.getItem(KEY);
      return raw === null ? [] : normalize(JSON.parse(raw));
    } catch (_) { return []; }
  }

  function save(keys) {
    try {
      global.localStorage.setItem(KEY, JSON.stringify(normalize(keys)));
      return true;
    } catch (_) { return false; }
  }

  function toggle(keys, event) {
    const current = normalize(keys);
    const identity = key(event);
    if (identity === null) return current;
    return current.includes(identity)
      ? current.filter(item => item !== identity)
      : [...current, identity];
  }

  function has(keys, event) {
    const identity = key(event);
    return identity !== null && normalize(keys).includes(identity);
  }

  function localToday(now, tz) {
    try {
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      }).formatToParts(new Date(now));
      const part = name => parts.find(item => item.type === name)?.value;
      return `${part('year')}-${part('month')}-${part('day')}`;
    } catch (_) { return null; }
  }

  function isUpcoming(event, now = Date.now(), tz = 'Europe/Prague') {
    const start = event && timestamp(event.start);
    const current = Number(now);
    if (!Number.isFinite(start) || !Number.isFinite(current)) return false;

    const hasEnd = event.end !== null && event.end !== undefined;
    if (hasEnd && !Number.isFinite(timestamp(event.end))) return false;
    if (event.all_day) {
      const startDay = event.start.slice(0, 10);
      const endDay = hasEnd ? event.end.slice(0, 10) : startDay;
      const today = localToday(current, tz);
      return today !== null && endDay >= startDay && endDay >= today;
    }
    const end = hasEnd ? timestamp(event.end) : start;
    return end >= start && end >= current;
  }

  function selected(events, keys, now = Date.now(), tz = 'Europe/Prague') {
    if (!Array.isArray(events)) return [];
    const favorites = new Set(normalize(keys));
    return events.map((event, index) => ({ event, index }))
      .filter(({ event }) => favorites.has(key(event)) && isUpcoming(event, now, tz))
      .sort((a, b) => timestamp(a.event.start) - timestamp(b.event.start)
        || String(a.event.title || '').localeCompare(String(b.event.title || ''), 'cs')
        || a.index - b.index)
      .map(({ event }) => event);
  }

  global.MostkulturaFavorites = { KEY, key, normalize, read, save, toggle, has, isUpcoming, selected };
})(typeof window !== 'undefined' ? window : globalThis);

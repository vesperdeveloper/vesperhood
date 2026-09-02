const RPC = 'https://rpc.mainnet.chain.robinhood.com';
const CHAIN_ID = 4663;
const EXPLORER = 'https://robinhoodchain.blockscout.com';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const RETRIES = 3;
const BACKOFF_MS = 400;
const TIMEOUT_MS = 8000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// A refusal is an answer; a timeout is not. Only the latter is worth repeating.
class PermanentError extends Error {}

async function withRetries(what, fn) {
  let delay = BACKOFF_MS;
  let last;
  for (let attempt = 1; attempt <= RETRIES; attempt++) {
    try {
      return await fn();
    } catch (e) {
      if (e instanceof PermanentError) throw e;
      last = e;
      if (attempt < RETRIES) { await sleep(delay); delay *= 2; }
    }
  }
  throw new Error(`${what} failed after ${RETRIES} attempts: ${last && last.message}`);
}

async function fetchWithTimeout(url, opts = {}) {
  // A serverless function that hangs on an upstream burns the whole invocation.
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: ac.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function rpc(method, params = []) {
  return withRetries(`rpc ${method}`, async () => {
    const r = await fetchWithTimeout(RPC, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params })
    });
    if (!r.ok) {
      if (r.status < 500) throw new PermanentError('rpc ' + r.status);
      throw new Error('rpc ' + r.status);
    }
    const j = await r.json();
    if (j.error) throw new PermanentError(j.error.message || 'rpc error');
    return j.result;
  });
}

async function blockscout(path) {
  return withRetries(`explorer ${path}`, async () => {
    const r = await fetchWithTimeout(EXPLORER + path, {
      headers: { 'user-agent': UA, accept: 'application/json' }
    });
    if (!r.ok) {
      // The explorer sits behind a bot check that answers 403 to anything it
      // dislikes; hammering it is how a soft block becomes a hard one.
      if (r.status < 500) throw new PermanentError('explorer ' + r.status);
      throw new Error('explorer ' + r.status);
    }
    return r.json();
  });
}

const calendar = require('../data/market_calendar.json');
const HOLIDAYS = Object.fromEntries(calendar.holidays.map((h) => [h.date, h.name]));
const EARLY = Object.fromEntries(calendar.early_closes.map((h) => [h.date, h.name]));
const OPEN_MINUTE = 570;                       // 09:30
const CLOSE_MINUTE = 960;                      // 16:00
const EARLY_CLOSE_MINUTE = calendar.early_close_hour * 60;

function nyParts(now) {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    weekday: 'short', hour: '2-digit', minute: '2-digit'
  }).formatToParts(now).reduce((o, x) => (o[x.type] = x.value, o), {});
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    weekday: p.weekday,
    minutes: (parseInt(p.hour, 10) % 24) * 60 + parseInt(p.minute, 10),
    hhmm: `${p.hour}:${p.minute}`
  };
}

function shiftDate(iso, days) {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function isTradingDay(iso) {
  const dow = new Date(iso + 'T12:00:00Z').getUTCDay();   // 0 Sun .. 6 Sat
  return dow !== 0 && dow !== 6 && !(iso in HOLIDAYS);
}

function closeMinuteFor(iso) {
  return iso in EARLY ? EARLY_CLOSE_MINUTE : CLOSE_MINUTE;
}

// Regular US equity session: 09:30-16:00 America/New_York on trading days,
// 09:30-13:00 on early-close days, shut on weekends and market holidays.
function sessionState(now = new Date()) {
  const p = nyParts(now);
  const trading = isTradingDay(p.date);
  const close = closeMinuteFor(p.date);
  const open = trading && p.minutes >= OPEN_MINUTE && p.minutes < close;

  let until;
  if (open) {
    until = close - p.minutes;
  } else if (trading && p.minutes < OPEN_MINUTE) {
    until = OPEN_MINUTE - p.minutes;
  } else {
    let days = 1;
    while (!isTradingDay(shiftDate(p.date, days)) && days <= 10) days++;
    until = days * 1440 + OPEN_MINUTE - p.minutes;
  }

  const dow = new Date(p.date + 'T12:00:00Z').getUTCDay();
  const closedBecause = trading ? null
    : (HOLIDAYS[p.date] || (dow === 0 || dow === 6 ? 'Weekend' : null));

  return {
    open,
    phase: open ? 'regular' : 'after_hours',
    minutes_until_change: until,
    new_york_time: p.hhmm,
    new_york_date: p.date,
    early_close: p.date in EARLY,
    closed_because: closedBecause,
    note: open
      ? (p.date in EARLY
          ? 'Exchange open on a shortened session — it closes at 13:00.'
          : 'Exchange open — reference price is live, edge is thin.')
      : 'Exchange shut — tokens still settle, no auction behind the price.'
  };
}

function send(res, status, body, maxAge = 60) {
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('access-control-allow-origin', '*');
  res.setHeader('cache-control', `public, max-age=${maxAge}, s-maxage=${maxAge}`);
  res.status(status).send(JSON.stringify(body, null, 1));
}

module.exports = { rpc, blockscout, sessionState, send, withRetries,
                   PermanentError, RPC, CHAIN_ID, EXPLORER };

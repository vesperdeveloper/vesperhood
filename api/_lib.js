const RPC = 'https://rpc.mainnet.chain.robinhood.com';
const CHAIN_ID = 4663;
const EXPLORER = 'https://robinhoodchain.blockscout.com';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

async function rpc(method, params = []) {
  const r = await fetch(RPC, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params })
  });
  if (!r.ok) throw new Error('rpc ' + r.status);
  const j = await r.json();
  if (j.error) throw new Error(j.error.message || 'rpc error');
  return j.result;
}

async function blockscout(path) {
  const r = await fetch(EXPLORER + path, {
    headers: { 'user-agent': UA, accept: 'application/json' }
  });
  if (!r.ok) throw new Error('explorer ' + r.status);
  return r.json();
}

// Regular US equity session: 09:30–16:00 America/New_York, Mon–Fri.
function sessionState(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hour12: false,
    weekday: 'short', hour: '2-digit', minute: '2-digit'
  }).formatToParts(now).reduce((o, p) => (o[p.type] = p.value, o), {});

  const dows = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const dow = dows[parts.weekday];
  const mins = (parseInt(parts.hour, 10) % 24) * 60 + parseInt(parts.minute, 10);
  const OPEN = 570, CLOSE = 960;
  const weekday = dow >= 1 && dow <= 5;
  const open = weekday && mins >= OPEN && mins < CLOSE;

  let until;
  if (open) {
    until = CLOSE - mins;
  } else {
    let days = (weekday && mins < OPEN) ? 0 : 1;
    if (days === 1) { let a = 1; while ([0, 6].includes((dow + a) % 7)) a++; days = a; }
    until = days * 1440 + OPEN - mins;
  }
  return {
    open,
    phase: open ? 'regular' : 'after_hours',
    minutes_until_change: until,
    new_york_time: parts.hour + ':' + parts.minute,
    note: open
      ? 'Exchange open — reference price is live, edge is thin.'
      : 'Exchange shut — tokens still settle, no auction behind the price.'
  };
}

function send(res, status, body, maxAge = 60) {
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.setHeader('access-control-allow-origin', '*');
  res.setHeader('cache-control', `public, max-age=${maxAge}, s-maxage=${maxAge}`);
  res.status(status).send(JSON.stringify(body, null, 1));
}

module.exports = { rpc, blockscout, sessionState, send, RPC, CHAIN_ID, EXPLORER };

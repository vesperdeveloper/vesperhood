const { put } = require('@vercel/blob');
const { send } = require('./_lib');
const { roster } = require('./agents');

const ADDR = /^0x[0-9a-fA-F]{40}$/;

// An unauthenticated endpoint that writes to storage needs a brake. This is a
// per-instance window, not a distributed one — it will not stop a determined
// flood across regions, but it stops the accidental loop and the casual one,
// which is what actually happens.
const WINDOW_MS = 60_000;
const MAX_PER_ADDRESS = 2;
const MAX_PER_IP = 10;
const hits = new Map();

function tooMany(key, limit) {
  const now = Date.now();
  const seen = (hits.get(key) || []).filter((t) => now - t < WINDOW_MS);
  seen.push(now);
  hits.set(key, seen);
  // keep the map from growing without bound across a warm instance
  if (hits.size > 5000) {
    for (const [k, v] of hits) {
      if (!v.length || now - v[v.length - 1] > WINDOW_MS) hits.delete(k);
    }
  }
  return seen.length > limit;
}

function clientIp(req) {
  const fwd = req.headers['x-forwarded-for'];
  return (typeof fwd === 'string' ? fwd.split(',')[0].trim() : '') || 'unknown';
}

function body(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  if (typeof req.body === 'string') { try { return JSON.parse(req.body); } catch (e) { return {}; } }
  return {};
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    return send(res, 405, { error: 'method_not_allowed', expected: 'POST' }, 0);
  }
  const b = body(req);
  const address = String(b.address || '').trim();
  if (!ADDR.test(address)) {
    return send(res, 400, {
      error: 'bad_address',
      detail: 'address must be a 0x-prefixed 20-byte hex string'
    }, 0);
  }
  const version = String(b.version || 'unknown').slice(0, 32);

  if (tooMany('ip:' + clientIp(req), MAX_PER_IP) ||
      tooMany('addr:' + address.toLowerCase(), MAX_PER_ADDRESS)) {
    res.setHeader('retry-after', '60');
    return send(res, 429, {
      error: 'rate_limited',
      detail: 'A check-in lasts 24 hours. Re-announcing more than twice a minute '
            + 'achieves nothing.',
      retry_after_seconds: 60
    }, 0);
  }

  try {
    await put('agents/' + address.toLowerCase() + '.json',
      JSON.stringify({ address, version }), {
        access: 'public',
        contentType: 'application/json',
        addRandomSuffix: false,
        allowOverwrite: true
      });
    const r = await roster();
    send(res, 200, {
      checked_in: true,
      address,
      agents_online: r.online,
      agents_total: r.total,
      note: 'You are on the desk for the next 24 hours. Check in again to stay listed.'
    }, 0);
  } catch (e) {
    send(res, 502, { error: 'checkin_failed', detail: String(e.message || e) }, 0);
  }
};

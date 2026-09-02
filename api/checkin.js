const { put } = require('@vercel/blob');
const { send } = require('./_lib');
const { roster } = require('./agents');

const ADDR = /^0x[0-9a-fA-F]{40}$/;

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

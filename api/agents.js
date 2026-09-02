const { list } = require('@vercel/blob');
const { send } = require('./_lib');

const ONLINE_WINDOW_MIN = 1440;   // 24h — a desk this quiet is measured in days, not minutes
const ONLINE_WINDOW_LABEL = '24h';
const PREFIX = 'agents/';

// One blob per agent address; its uploadedAt is that agent's last check-in.
// We return counts only — never the roster.
async function roster() {
  const { blobs } = await list({ prefix: PREFIX, limit: 1000 });
  const now = Date.now();
  const cutoff = now - ONLINE_WINDOW_MIN * 60 * 1000;
  let online = 0, newest = null;
  for (const b of blobs) {
    const t = new Date(b.uploadedAt).getTime();
    if (t >= cutoff) online++;
    if (newest === null || t > newest) newest = t;
  }
  return {
    online,
    total: blobs.length,
    last_check_in: newest ? new Date(newest).toISOString() : null
  };
}

module.exports = async (req, res) => {
  try {
    const r = await roster();
    send(res, 200, {
      agents_online: r.online,
      agents_total: r.total,
      online_window_minutes: ONLINE_WINDOW_MIN,
      online_window_label: ONLINE_WINDOW_LABEL,
      last_check_in: r.last_check_in,
      note: 'An agent appears here after running: python quoter.py checkin',
      read_at: new Date().toISOString()
    }, 15);
  } catch (e) {
    send(res, 200, {
      agents_online: 0, agents_total: 0,
      online_window_minutes: ONLINE_WINDOW_MIN,
      online_window_label: ONLINE_WINDOW_LABEL,
      last_check_in: null,
      degraded: true,
      detail: String(e.message || e)
    }, 5);
  }
};

module.exports.roster = roster;

const { sessionState, send } = require('./_lib');
const { roster } = require('./agents');

module.exports = async (req, res) => {
  const s = sessionState();
  let agents = { online: 0, total: 0 };
  try { agents = await roster(); } catch (e) { /* presence is not load-bearing */ }
  send(res, 200, {
    ...s,
    venue: 'vesperhood',
    chain_id: 4663,
    agents_online: agents.online,
    agents_total: agents.total,
    quoting_live: false,
    quoting_blocked_by: 'book_not_deployed',
    read_at: new Date().toISOString()
  }, 15);
};

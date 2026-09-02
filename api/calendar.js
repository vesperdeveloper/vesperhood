const { send } = require('./_lib');
const calendar = require('../data/market_calendar.json');

// The kit embeds its own copy so a single downloaded file works offline.
// This endpoint is the authoritative one it can check itself against.
module.exports = async (req, res) => {
  const today = new Date().toISOString().slice(0, 10);
  const expired = calendar.verified_through < today;
  send(res, 200, {
    verified_through: calendar.verified_through,
    expired,
    early_close_hour: calendar.early_close_hour,
    regular_session: { open: '09:30', close: '16:00', timezone: 'America/New_York' },
    holidays: calendar.holidays,
    early_closes: calendar.early_closes,
    note: expired
      ? 'This calendar is out of date — treat unlisted closures as unmodelled.'
      : 'Observed dates. Holidays close the session; early closes end it at 13:00.',
    read_at: new Date().toISOString()
  }, 3600);
};

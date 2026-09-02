const { blockscout, send, CHAIN_ID } = require('./_lib');
const registry = require('../data/registry.json');

// Live fields are fetched per token, so ?live=1 is capped and cached.
const LIVE_CAP = 24;
let cache = { at: 0, map: null };

async function livePrices(pairs) {
  if (cache.map && Date.now() - cache.at < 60000) return cache.map;
  const subset = pairs.slice(0, LIVE_CAP);
  const map = {};
  await Promise.all(subset.map(async (p) => {
    try {
      const t = await blockscout('/api/v2/tokens/' + p.address);
      map[p.address.toLowerCase()] = {
        price: t.exchange_rate ? Number(t.exchange_rate) : null,
        volume_24h: t.volume_24h ? Number(t.volume_24h) : null,
        holders: t.holders_count ? Number(t.holders_count) : p.holders
      };
    } catch (e) { /* a single token failing must not fail the board */ }
  }));
  cache = { at: Date.now(), map };
  return map;
}

module.exports = async (req, res) => {
  const q = req.query || {};
  let pairs = registry.pairs;

  if (q.tier) pairs = pairs.filter((p) => p.tier === String(q.tier).toLowerCase());
  if (q.symbol) {
    const want = String(q.symbol).toUpperCase().split(',').map((s) => s.trim());
    pairs = pairs.filter((p) => want.includes(p.symbol));
  }

  let live = null;
  if (q.live === '1' || q.live === 'true') {
    try { live = await livePrices(pairs); } catch (e) { live = null; }
  }

  const out = pairs.map((p) => {
    const base = {
      symbol: p.symbol,
      pair: p.symbol + '/USDG',
      name: p.name,
      address: p.address,
      decimals: p.decimals,
      tier: p.tier,
      holders: p.holders,
      icon: p.icon,
      explorer: 'https://robinhoodchain.blockscout.com/token/' + p.address
    };
    const l = live && live[p.address.toLowerCase()];
    if (l) { base.price_usd = l.price; base.volume_24h = l.volume_24h; base.holders = l.holders; }
    return base;
  });

  send(res, 200, {
    chain_id: CHAIN_ID,
    quote_asset: registry.quote_asset,
    count: out.length,
    live: !!live,
    live_cap: live ? LIVE_CAP : null,
    source: 'addresses verified by direct eth_call (symbol, name, decimals, totalSupply)',
    pairs: out
  }, live ? 60 : 300);
};

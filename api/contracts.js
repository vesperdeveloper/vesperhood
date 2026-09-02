const { rpc, send, CHAIN_ID, RPC } = require('./_lib');

// The Book is unpublished. Rather than asserting that, we verify it:
// any address we claimed to have deployed would have non-empty code.
const CLAIMED = { book: null, treasury: null };

module.exports = async (req, res) => {
  const deployed = [], pending = [];
  try {
    for (const [name, addr] of Object.entries(CLAIMED)) {
      if (!addr) { pending.push(name); continue; }
      const code = await rpc('eth_getCode', [addr, 'latest']);
      (code && code !== '0x' ? deployed : pending).push(name);
    }
    send(res, 200, {
      chain_id: CHAIN_ID,
      contracts: CLAIMED,
      deployed,
      pending,
      venue_live: deployed.length > 0 && pending.length === 0,
      accepts_capital: false,
      verified_against: RPC,
      read_at: new Date().toISOString()
    }, 60);
  } catch (e) {
    send(res, 502, { error: 'verification_failed', detail: String(e.message || e) }, 0);
  }
};

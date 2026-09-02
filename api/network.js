const { rpc, send, CHAIN_ID, RPC, EXPLORER } = require('./_lib');

module.exports = async (req, res) => {
  try {
    const [idHex, blockHex, gasHex] = await Promise.all([
      rpc('eth_chainId'), rpc('eth_blockNumber'), rpc('eth_gasPrice')
    ]);
    const id = parseInt(idHex, 16);
    send(res, 200, {
      chain_id: id,
      chain_id_matches: id === CHAIN_ID,
      block: parseInt(blockHex, 16),
      gas_price_wei: parseInt(gasHex, 16),
      gas_price_gwei: +(parseInt(gasHex, 16) / 1e9).toFixed(4),
      rpc: RPC,
      explorer: EXPLORER,
      read_at: new Date().toISOString()
    }, 10);
  } catch (e) {
    send(res, 502, { error: 'rpc_unreachable', detail: String(e.message || e) }, 0);
  }
};

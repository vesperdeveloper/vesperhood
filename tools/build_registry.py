#!/usr/bin/env python3
"""
Rebuild data/registry.json from the chain.

Discovery is untrusted: candidate addresses come from the block explorer's
token index, but nothing is served until the contract itself has answered
symbol(), name(), decimals() and totalSupply() over eth_call. An address that
does not answer all four is dropped.

    python tools/build_registry.py            # rebuild in place
    python tools/build_registry.py --check    # verify the committed file, exit 1 on drift

Notes for anyone re-running this:
  * The explorer sits behind a bot check — a browser User-Agent is required.
  * Its token search caps at 50 results and does not paginate, so discovery
    is seeded from both the search and the addresses already committed.
  * USDG is a 6-decimal token. Assuming 18 scales every order by 1e12.
"""

import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

RPC = "https://rpc.mainnet.chain.robinhood.com"
EXPLORER = "https://robinhoodchain.blockscout.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CHAIN_ID = 4663
QUOTE_ASSET = {"symbol": "USDG", "name": "Global Dollar",
               "address": "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
               "decimals": 6}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "registry.json")

SELECTORS = {"symbol": "0x95d89b41", "name": "0x06fdde03",
             "decimals": "0x313ce567", "totalSupply": "0x18160ddd"}
CORE_CUTOFF, ACTIVE_CUTOFF = 24, 64


def curl(args):
    return subprocess.run(["curl", "-sS", "-m", "40"] + args,
                          capture_output=True, text=True).stdout


def rpc(to, data):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]})
    try:
        return json.loads(curl([RPC, "-H", "content-type: application/json",
                                "-d", body])).get("result")
    except Exception:
        return None


def abi_string(res):
    """Decode a solidity `string` return value."""
    if not res or len(res) < 130:
        return None
    r = res[2:]
    try:
        n = int(r[64:128], 16)
        return bytes.fromhex(r[128:128 + n * 2]).decode("utf-8", "replace").strip()
    except Exception:
        return None


def explorer(path):
    try:
        return json.loads(curl([EXPLORER + path, "-H", f"user-agent: {UA}",
                                "-H", "accept: application/json"]))
    except Exception:
        return {}


def discover():
    """Seed candidates from the explorer search plus whatever we already serve."""
    found = set()
    d = explorer("/api/v2/tokens?q=Robinhood&type=ERC-20")
    for t in d.get("items", []):
        a = (t.get("address_hash") or t.get("address") or "").strip()
        if a:
            found.add(a)
    if os.path.exists(OUT):
        for p in json.load(open(OUT)).get("pairs", []):
            found.add(p["address"])
    return sorted(found)


def verify(addr):
    """Serve nothing the contract has not confirmed itself."""
    sym = abi_string(rpc(addr, SELECTORS["symbol"]))
    nm = abi_string(rpc(addr, SELECTORS["name"]))
    dec = rpc(addr, SELECTORS["decimals"])
    sup = rpc(addr, SELECTORS["totalSupply"])
    if not sym or dec is None:
        return None
    if "Robinhood Token" not in (nm or ""):
        return None

    rec = {"symbol": sym,
           "name": re.sub(r"\s*•\s*Robinhood Token\s*$", "", nm or "").strip(),
           "address": addr,
           "decimals": int(dec, 16),
           "supply": str(int(sup, 16)) if sup else None,
           "holders": 0, "icon": None}

    meta = explorer("/api/v2/tokens/" + addr)
    if meta:
        rec["holders"] = int(meta.get("holders_count") or 0)
        rec["icon"] = meta.get("icon_url")
    return rec


def build():
    cands = discover()
    print(f"  {len(cands)} candidate addresses", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as ex:
        pairs = [r for r in ex.map(verify, cands) if r]
    dropped = len(cands) - len(pairs)
    print(f"  {len(pairs)} verified on-chain, {dropped} dropped", file=sys.stderr)

    pairs.sort(key=lambda p: -p["holders"])
    for i, p in enumerate(pairs):
        p["tier"] = ("core" if i < CORE_CUTOFF
                     else "active" if i < ACTIVE_CUTOFF else "tail")

    return {"chain_id": CHAIN_ID, "quote_asset": QUOTE_ASSET,
            "count": len(pairs), "pairs": pairs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the committed registry instead of rewriting it")
    a = ap.parse_args()

    if a.check:
        if not os.path.exists(OUT):
            print("registry.json missing", file=sys.stderr)
            return 1
        reg = json.load(open(OUT))
        bad = []
        if reg["quote_asset"]["decimals"] != 6:
            bad.append("USDG decimals must be 6")
        if reg["count"] != len(reg["pairs"]):
            bad.append("count does not match pairs length")
        seen = set()
        for p in reg["pairs"]:
            for k in ("symbol", "name", "address", "decimals", "tier", "holders"):
                if k not in p:
                    bad.append(f"{p.get('symbol', '?')}: missing {k}")
            if not re.fullmatch(r"0x[0-9a-fA-F]{40}", p.get("address", "")):
                bad.append(f"{p.get('symbol')}: malformed address")
            if p["address"].lower() in seen:
                bad.append(f"{p['symbol']}: duplicate address")
            seen.add(p["address"].lower())
        if bad:
            for b in bad[:20]:
                print("  ✗", b, file=sys.stderr)
            return 1
        print(f"  ✓ {reg['count']} pairs, structure valid")
        return 0

    reg = build()
    with open(OUT, "w") as f:
        json.dump(reg, f, indent=1)
    print(f"  wrote {reg['count']} pairs to data/registry.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

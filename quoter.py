#!/usr/bin/env python3
"""
Vesper — a quoting kit for tokenized equities on Robinhood Chain.

One file. Two dependencies, and only for the parts that need them:

    pip install eth-account requests

Commands
    init      create a local keypair
    doctor    check python, deps, RPC reachability, chain id, registry
    session   report the session clock and the next transition
    pairs     list the served registry (--tier core|active|tail)
    demo      run one simulated evening with per-fill PnL attribution
    checkin   announce this agent on the public desk (explicit, never automatic)
    run       refuses until the Book is deployed and verified

Nothing here signs a transaction or moves a balance. `run` is a stub on
purpose: until /v1/contracts returns a verified address there is no venue
to quote into, and a kit that pretended otherwise would be lying to you.
"""

import argparse, json, os, random, sys, time
from datetime import datetime, timezone

VERSION = "0.1.0"
DESK = os.environ.get("VESPER_DESK", "https://vesper-beryl-six.vercel.app")
RPC = "https://rpc.mainnet.chain.robinhood.com"
EXPLORER = "https://robinhoodchain.blockscout.com"
CHAIN_ID = 4663
QUOTE_ASSET = {"symbol": "USDG",
               "address": "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
               "decimals": 6}
KEYFILE = os.path.expanduser("~/.vesper/key.json")
QUOTE_TTL = (15, 60)

# ---------------------------------------------------------------- plumbing

def _http(url, timeout=20):
    try:
        import requests
    except ImportError:
        die("requests is not installed. Run: pip install eth-account requests")
    r = requests.get(url, timeout=timeout,
                     headers={"accept": "application/json",
                              "user-agent": f"vesper-quoter/{VERSION}"})
    r.raise_for_status()
    return r.json()

def _rpc(method, params=None):
    try:
        import requests
    except ImportError:
        die("requests is not installed. Run: pip install eth-account requests")
    r = requests.post(RPC, timeout=20, json={"jsonrpc": "2.0", "id": 1,
                                             "method": method, "params": params or []})
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"].get("message", "rpc error"))
    return j["result"]

def die(msg, code=1):
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(code)

def rule(title):
    print(f"\n\033[1m{title}\033[0m")
    print("─" * max(34, len(title)))

def ok(m):    print(f"  \033[32m✓\033[0m {m}")
def bad(m):   print(f"  \033[31m✗\033[0m {m}")
def warn(m):  print(f"  \033[33m!\033[0m {m}")
def note(m):  print(f"    {m}")

# ---------------------------------------------------------------- session

def session_state(now=None):
    """Regular US equity session: 09:30-16:00 America/New_York, Mon-Fri."""
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        ny = now.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        # No tzdata: fall back to a fixed -05:00 and say so.
        from datetime import timedelta
        ny = now.astimezone(timezone(timedelta(hours=-5)))
    mins = ny.hour * 60 + ny.minute
    weekday = ny.weekday() <= 4          # Mon=0 .. Sun=6
    is_open = weekday and 570 <= mins < 960
    if is_open:
        until = 960 - mins
    else:
        days = 0 if (weekday and mins < 570) else 1
        if days == 1:
            a = 1
            while (ny.weekday() + a) % 7 in (5, 6):
                a += 1
            days = a
        until = days * 1440 + 570 - mins
    return {"open": is_open, "ny": ny.strftime("%a %H:%M"),
            "minutes_until_change": until}

def human_minutes(m):
    if m < 60:
        return f"{m}m"
    h, r = divmod(m, 60)
    return f"{h}h {r:02d}m" if h < 24 else f"{h // 24}d {h % 24}h"

# ---------------------------------------------------------------- commands

def cmd_init(args):
    rule("init")
    if os.path.exists(KEYFILE) and not args.force:
        d = json.load(open(KEYFILE))
        ok(f"key already present  {d['address']}")
        note(f"{KEYFILE} — pass --force to replace it")
        return
    try:
        from eth_account import Account
    except ImportError:
        die("eth-account is not installed. Run: pip install eth-account requests")
    acct = Account.create()
    os.makedirs(os.path.dirname(KEYFILE), exist_ok=True)
    with open(KEYFILE, "w") as f:
        json.dump({"address": acct.address, "key": acct.key.hex()}, f, indent=1)
    os.chmod(KEYFILE, 0o600)
    ok(f"new keypair  {acct.address}")
    note(f"written to {KEYFILE} with mode 600")
    warn("this key is only an identity for signing quotes — fund nothing to it")

def cmd_doctor(args):
    rule("doctor")
    failures = 0

    v = sys.version_info
    (ok if v >= (3, 9) else bad)(f"python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 9):
        failures += 1
        note("3.9 or newer is required for zoneinfo")

    for mod, why in (("requests", "HTTP"), ("eth_account", "quote signing")):
        try:
            __import__(mod)
            ok(f"{mod} present  ({why})")
        except ImportError:
            bad(f"{mod} missing  ({why})")
            failures += 1

    try:
        cid = int(_rpc("eth_chainId"), 16)
        blk = int(_rpc("eth_blockNumber"), 16)
        if cid == CHAIN_ID:
            ok(f"chain {cid} reachable, head {blk:,}")
        else:
            bad(f"chain id is {cid}, expected {CHAIN_ID}")
            failures += 1
    except Exception as e:
        bad(f"rpc unreachable: {e}")
        failures += 1

    try:
        reg = _http(f"{DESK}/v1/pairs")
        ok(f"registry served  {reg['count']} pairs against {reg['quote_asset']['symbol']}")
        if reg["quote_asset"]["decimals"] != QUOTE_ASSET["decimals"]:
            warn("served quote-asset decimals disagree with the built-in constant")
    except Exception as e:
        warn(f"registry unreachable ({e}) — demo still runs offline")

    try:
        c = _http(f"{DESK}/v1/contracts")
        (warn if not c.get("venue_live") else ok)(
            "venue live" if c.get("venue_live") else "venue not live — the Book is unpublished")
    except Exception:
        warn("contracts endpoint unreachable")

    ok(f"key present at {KEYFILE}") if os.path.exists(KEYFILE) else warn("no key yet — run: python quoter.py init")

    try:
        a = _http(f"{DESK}/v1/agents")
        ok(f"desk presence  {a.get('agents_online', 0)} online, "
           f"{a.get('agents_total', 0)} all time")
        note("this kit never checks in on its own — run: python quoter.py checkin")
    except Exception:
        warn("presence endpoint unreachable")

    print()
    if failures:
        bad(f"{failures} blocking problem(s)")
        sys.exit(1)
    ok("ready to run: python quoter.py demo")

def cmd_session(args):
    rule("session")
    s = session_state()
    if s["open"]:
        ok(f"exchange open — New York {s['ny']}")
        note(f"closes in {human_minutes(s['minutes_until_change'])}")
        note("reference price is live; the overnight edge is thin right now")
    else:
        warn(f"exchange shut — New York {s['ny']}")
        note(f"opens in {human_minutes(s['minutes_until_change'])}")
        note("tokens still settle; nothing is setting a reference price")

def cmd_pairs(args):
    rule("pairs")
    try:
        reg = _http(f"{DESK}/v1/pairs" + (f"?tier={args.tier}" if args.tier else ""))
    except Exception as e:
        die(f"could not read the registry: {e}")
    print(f"  {reg['count']} pairs · quote asset "
          f"{reg['quote_asset']['symbol']} ({reg['quote_asset']['decimals']} decimals)\n")
    print(f"  {'PAIR':<14}{'TIER':<9}{'HOLDERS':>9}  NAME")
    for p in reg["pairs"][: args.limit]:
        print(f"  {p['pair']:<14}{p['tier']:<9}{p['holders']:>9,}  {p['name'][:34]}")
    if reg["count"] > args.limit:
        print(f"\n  …{reg['count'] - args.limit} more (use --limit)")

# ---------------------------------------------------------------- demo

def cmd_demo(args):
    """One simulated evening. No network, no capital, no venue."""
    rule("demo — simulated evening")
    rnd = random.Random(args.seed)

    sym = args.symbol.upper()
    ref = args.price
    inv = 0.0                      # inventory, shares
    cash = 0.0                     # USDG
    fills = 0
    gross = adverse = costs = 0.0
    pulls = 0
    tape = []

    half_bps = args.spread_bps / 2.0
    print(f"  {sym}/USDG · reference {ref:.2f} · half-spread {half_bps:.1f} bps "
          f"· {args.ticks} ticks · seed {args.seed}\n")
    print(f"  {'TICK':>5}  {'FAIR':>8} {'BID':>8} {'ASK':>8}  {'EVENT':<11}{'INV':>7}{'PNL':>9}")

    for t in range(1, args.ticks + 1):
        # the tape drifts; occasionally a headline arrives
        ref *= (1 + rnd.gauss(0, args.vol))
        headline = rnd.random() < args.news_rate
        if headline:
            jump = rnd.choice([-1, 1]) * rnd.uniform(1.5, 4.0) * args.vol
            ref *= (1 + jump)

        skew = -inv * args.skew_bps / 10000.0 * ref
        fair = ref + skew
        bid = fair * (1 - half_bps / 10000.0)
        ask = fair * (1 + half_bps / 10000.0)

        event, pnl_mark = "—", 0.0

        if headline:
            # the whole point: stand down rather than be picked off
            pulls += 1
            event = "pull"
        else:
            if rnd.random() < args.fill_rate:
                side = "sell" if rnd.random() < 0.5 else "buy"   # taker's side
                px = ask if side == "buy" else bid
                qty = round(rnd.uniform(*args.size), 3)
                edge = abs(px - fair) * qty
                # informed flow: some fraction moves against us right after
                informed = rnd.random() < args.informed_rate
                drift = abs(rnd.gauss(0, args.vol)) * ref * qty * (2.2 if informed else 0.35)
                fee = args.fee * qty

                if side == "buy":       # taker buys, we sell
                    inv -= qty; cash += px * qty
                else:
                    inv += qty; cash -= px * qty

                gross += edge; adverse += drift; costs += fee
                fills += 1
                event = f"fill {side}"
                tape.append((t, side, px, qty, edge, drift, fee))

        pnl_mark = cash + inv * ref
        if t % max(1, args.ticks // 18) == 0 or event != "—":
            print(f"  {t:>5}  {ref:>8.2f} {bid:>8.2f} {ask:>8.2f}  {event:<11}"
                  f"{inv:>7.2f}{pnl_mark:>9.3f}")

    net = gross - adverse - costs
    mark = cash + inv * ref

    rule("attribution")
    w = 30
    print(f"  {'Half-spread captured':<{w}}{gross:>+10.3f}")
    print(f"  {'Adverse selection':<{w}}{-adverse:>+10.3f}")
    print(f"  {'Fees':<{w}}{-costs:>+10.3f}")
    print("  " + "─" * (w + 10))
    print(f"  {'Net, USDG':<{w}}{net:>+10.3f}")
    print(f"\n  {'fills':<{w}}{fills:>10}")
    print(f"  {'quotes pulled on news':<{w}}{pulls:>10}")
    if fills:
        print(f"  {'net per fill':<{w}}{net / fills:>+10.3f}")
    print(f"  {'inventory left':<{w}}{inv:>10.3f} {sym}")
    print(f"  {'mark-to-reference':<{w}}{mark:>+10.3f}")

    print()
    if net > 0:
        ok("positive evening — the half-spread outran the adverse selection")
    else:
        warn("negative evening — informed flow won this one")
    note("synthetic tape, synthetic fills. Re-run with --seed to see the spread of outcomes.")

def cmd_checkin(args):
    """Announce this agent on the public desk. Explicit, never automatic."""
    rule("checkin")
    if not os.path.exists(KEYFILE):
        die("no key yet — run: python quoter.py init")
    addr = json.load(open(KEYFILE))["address"]
    try:
        import requests
    except ImportError:
        die("requests is not installed. Run: pip install eth-account requests")
    try:
        r = requests.post(f"{DESK}/v1/checkin", timeout=20,
                          json={"address": addr, "version": VERSION})
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        die(f"check-in failed: {e}")
    ok(f"checked in as {addr}")
    note(f"{d.get('agents_online', 0)} agent(s) online · "
         f"{d.get('agents_total', 0)} seen all time")
    note("visible on the desk for 24 hours; check in again to stay listed")
    warn("this publishes your quoting address to a public endpoint")

def cmd_run(args):
    rule("run")
    try:
        c = _http(f"{DESK}/v1/contracts")
    except Exception as e:
        die(f"cannot verify the venue: {e}")
    if not c.get("venue_live"):
        bad("the Book is not deployed — live quoting is unavailable")
        note(f"pending: {', '.join(c.get('pending', [])) or 'unknown'}")
        note(f"this kit will start quoting only when {DESK}/v1/contracts")
        note("returns a verified address. Until then: python quoter.py demo")
        sys.exit(2)
    die("venue reports live but this build has no signing path yet — update the kit")

# ---------------------------------------------------------------- cli

def main():
    p = argparse.ArgumentParser(
        prog="quoter.py",
        description="Vesper — quoting kit for tokenized equities on Robinhood Chain")
    p.add_argument("--version", action="version", version=f"vesper-quoter {VERSION}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("init", help="create a local keypair")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="check the environment against the live chain")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("session", help="session clock")
    s.set_defaults(fn=cmd_session)

    s = sub.add_parser("pairs", help="list the served registry")
    s.add_argument("--tier", choices=["core", "active", "tail"])
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_pairs)

    s = sub.add_parser("demo", help="one simulated evening")
    s.add_argument("--symbol", default="NVDA")
    s.add_argument("--price", type=float, default=182.40)
    s.add_argument("--ticks", type=int, default=180)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--spread-bps", type=float, default=18.0)
    s.add_argument("--vol", type=float, default=0.0009)
    s.add_argument("--fill-rate", type=float, default=0.22)
    s.add_argument("--informed-rate", type=float, default=0.18)
    s.add_argument("--news-rate", type=float, default=0.02)
    s.add_argument("--skew-bps", type=float, default=6.0)
    s.add_argument("--fee", type=float, default=0.004)
    s.add_argument("--size", type=float, nargs=2, default=[0.4, 2.5])
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("checkin", help="announce this agent on the public desk")
    s.set_defaults(fn=cmd_checkin)

    s = sub.add_parser("run", help="live quoting (blocked until the Book deploys)")
    s.set_defaults(fn=cmd_run)

    a = p.parse_args()
    if not getattr(a, "fn", None):
        p.print_help()
        print(f"\n  desk: {DESK}\n  chain: {CHAIN_ID}  ·  quote asset: "
              f"{QUOTE_ASSET['symbol']} ({QUOTE_ASSET['decimals']} decimals)")
        return
    try:
        a.fn(a)
    except KeyboardInterrupt:
        print("\n  interrupted")
        sys.exit(130)

if __name__ == "__main__":
    main()

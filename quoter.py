#!/usr/bin/env python3
"""
Vesperhood — a quoting kit for tokenized equities on Robinhood Chain.

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
DESK = os.environ.get("VESPERHOOD_DESK", "https://vesperagent.trade")
RPC = "https://rpc.mainnet.chain.robinhood.com"
EXPLORER = "https://robinhoodchain.blockscout.com"
CHAIN_ID = 4663
QUOTE_ASSET = {"symbol": "USDG",
               "address": "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
               "decimals": 6}
KEYFILE = os.path.expanduser("~/.vesperhood/key.json")
QUOTE_TTL = (15, 60)

# US equity market closures, observed dates. Embedded rather than fetched so a
# single downloaded file still models the calendar with no network. Verified
# through 2027-12-31; `doctor` warns once it runs out, and the
# desk serves the authoritative copy at GET /v1/calendar.
CALENDAR_VERIFIED_THROUGH = "2027-12-31"
EARLY_CLOSE_HOUR = 13
HOLIDAYS = {
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Washington's Birthday",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving Day",
    "2026-12-25": "Christmas Day",
    "2027-01-01": "New Year's Day",
    "2027-01-18": "Martin Luther King Jr. Day",
    "2027-02-15": "Washington's Birthday",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving Day",
    "2027-12-24": "Christmas Day (observed)",
}
EARLY_CLOSES = {
    "2026-11-27": "Day after Thanksgiving",
    "2026-12-24": "Christmas Eve",
    "2027-11-26": "Day after Thanksgiving",
}

# ---------------------------------------------------------------- plumbing

RETRIES = 3
BACKOFF = 0.6          # seconds, doubled each attempt

def _requests():
    try:
        import requests
        return requests
    except ImportError:
        die("requests is not installed. Run: pip install eth-account requests")

def _with_retries(what, fn):
    """Retry transient network faults; give up immediately on real answers.

    A 4xx, or an RPC error object, is the server telling us something true —
    repeating the question will not change it. Timeouts, connection resets and
    5xx are worth another attempt.
    """
    requests = _requests()
    delay = BACKOFF
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            return fn(requests)
        except requests.exceptions.HTTPError as e:
            code = getattr(e.response, "status_code", 0)
            if code and code < 500:
                raise
            last = e
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            last = e
        except ValueError as e:                  # undecodable JSON body
            last = e
        if attempt < RETRIES:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{what} failed after {RETRIES} attempts: {last}")

def _http(url, timeout=20):
    def go(requests):
        r = requests.get(url, timeout=timeout,
                         headers={"accept": "application/json",
                                  "user-agent": f"vesperhood-quoter/{VERSION}"})
        r.raise_for_status()
        return r.json()
    return _with_retries(f"GET {url}", go)

def _rpc(method, params=None):
    def go(requests):
        r = requests.post(RPC, timeout=20,
                          json={"jsonrpc": "2.0", "id": 1,
                                "method": method, "params": params or []})
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            # a well-formed refusal, not a transport fault
            raise _RpcError(j["error"].get("message", "rpc error"))
        return j["result"]
    return _with_retries(f"rpc {method}", go)

class _RpcError(RuntimeError):
    pass

def die(msg, code=1):
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(code)

def emit(payload):
    """Machine output. The kit is meant to be driven by another agent, and an
    agent should not have to scrape ANSI-coloured columns to learn anything."""
    print(json.dumps(payload, indent=1, default=str))

def rule(title):
    print(f"\n\033[1m{title}\033[0m")
    print("─" * max(34, len(title)))

def ok(m):    print(f"  \033[32m✓\033[0m {m}")
def bad(m):   print(f"  \033[31m✗\033[0m {m}")
def warn(m):  print(f"  \033[33m!\033[0m {m}")
def note(m):  print(f"    {m}")

# ---------------------------------------------------------------- session

OPEN_MINUTE = 9 * 60 + 30
CLOSE_MINUTE = 16 * 60


def _ny(now=None):
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        # No tzdata on this box. -05:00 is right for standard time and an hour
        # off during DST; session() flags this so nobody trusts it blindly.
        from datetime import timedelta
        return now.astimezone(timezone(timedelta(hours=-5)))


def is_trading_day(d):
    """Weekday that is not a full-day market holiday."""
    return d.weekday() <= 4 and d.isoformat() not in HOLIDAYS


def close_minute_for(d):
    """Most days close at 16:00; a handful close early at 13:00."""
    return (EARLY_CLOSE_HOUR * 60) if d.isoformat() in EARLY_CLOSES else CLOSE_MINUTE


def session_state(now=None):
    """Regular US equity session, holidays and early closes included.

    09:30-16:00 America/New_York on trading days, 09:30-13:00 on early-close
    days, shut on weekends and market holidays.
    """
    ny = _ny(now)
    today = ny.date()
    mins = ny.hour * 60 + ny.minute
    close = close_minute_for(today)

    trading = is_trading_day(today)
    is_open = trading and OPEN_MINUTE <= mins < close

    if is_open:
        until = close - mins
    elif trading and mins < OPEN_MINUTE:
        until = OPEN_MINUTE - mins
    else:
        # walk forward to the next day the market actually opens
        from datetime import timedelta
        days = 1
        while not is_trading_day(today + timedelta(days=days)):
            days += 1
            if days > 10:          # a closure this long means the calendar is wrong
                break
        until = days * 1440 + OPEN_MINUTE - mins

    reason = None
    if not trading:
        reason = HOLIDAYS.get(today.isoformat()) or (
            "Weekend" if today.weekday() > 4 else None)

    return {"open": is_open,
            "ny": ny.strftime("%a %H:%M"),
            "minutes_until_change": until,
            "early_close": today.isoformat() in EARLY_CLOSES,
            "closed_because": reason}


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
    """One pass of checks, rendered either for a person or for a program."""
    as_json = getattr(args, "json", False)
    checks = []

    def record(state, name, detail="", hint=""):
        checks.append({"check": name, "state": state,
                       "detail": detail, "hint": hint})

    # --- environment
    v = sys.version_info
    record("ok" if v >= (3, 9) else "fail", "python",
           f"{v.major}.{v.minor}.{v.micro}",
           "" if v >= (3, 9) else "3.9 or newer is required for zoneinfo")

    for mod, why in (("requests", "HTTP"), ("eth_account", "quote signing")):
        try:
            __import__(mod)
            record("ok", mod, f"present ({why})")
        except ImportError:
            record("fail", mod, f"missing ({why})",
                   "pip install eth-account requests")

    # --- chain
    try:
        cid = int(_rpc("eth_chainId"), 16)
        blk = int(_rpc("eth_blockNumber"), 16)
        if cid == CHAIN_ID:
            record("ok", "chain", f"{cid} reachable, head {blk:,}")
        else:
            record("fail", "chain", f"chain id is {cid}, expected {CHAIN_ID}")
    except Exception as e:
        record("fail", "chain", f"rpc unreachable: {e}")

    # --- desk
    try:
        reg = _http(f"{DESK}/v1/pairs")
        record("ok", "registry",
               f"{reg['count']} pairs against {reg['quote_asset']['symbol']}")
        if reg["quote_asset"]["decimals"] != QUOTE_ASSET["decimals"]:
            record("warn", "quote_decimals",
                   f"desk says {reg['quote_asset']['decimals']}, "
                   f"kit says {QUOTE_ASSET['decimals']}",
                   "update the kit before sizing anything")
    except Exception as e:
        record("warn", "registry", f"unreachable ({e})",
               "demo still runs offline")

    try:
        c = _http(f"{DESK}/v1/contracts")
        live = bool(c.get("venue_live"))
        record("ok" if live else "warn", "venue",
               "live" if live else "not live — the Book is unpublished")
    except Exception:
        record("warn", "venue", "contracts endpoint unreachable")

    try:
        a = _http(f"{DESK}/v1/agents")
        record("ok", "presence",
               f"{a.get('agents_online', 0)} online, "
               f"{a.get('agents_total', 0)} all time",
               "this kit never checks in on its own — run: quoter.py checkin")
    except Exception:
        record("warn", "presence", "endpoint unreachable")

    # --- local state
    if os.path.exists(KEYFILE):
        record("ok", "key", KEYFILE)
    else:
        record("warn", "key", "no key yet", "python quoter.py init")

    from datetime import date
    if CALENDAR_VERIFIED_THROUGH < date.today().isoformat():
        record("warn", "calendar", f"expired {CALENDAR_VERIFIED_THROUGH}",
               "holidays past that date are not modelled; update the kit")
    else:
        record("ok", "calendar",
               f"good through {CALENDAR_VERIFIED_THROUGH} "
               f"({len(HOLIDAYS)} holidays, {len(EARLY_CLOSES)} early closes)")

    failures = sum(1 for c in checks if c["state"] == "fail")

    if as_json:
        emit({"ok": failures == 0,
              "failures": failures,
              "ready": failures == 0,
              "checks": checks})
        sys.exit(1 if failures else 0)

    rule("doctor")
    render = {"ok": ok, "warn": warn, "fail": bad}
    for c in checks:
        render[c["state"]](f"{c['check']}  {c['detail']}".rstrip())
        if c["hint"]:
            note(c["hint"])
    print()
    if failures:
        bad(f"{failures} blocking problem(s)")
        sys.exit(1)
    ok("ready to run: python quoter.py demo")

def cmd_session(args):
    s = session_state()
    if getattr(args, "json", False):
        return emit({
            "open": s["open"],
            "new_york": s["ny"],
            "minutes_until_change": s["minutes_until_change"],
            "human_until": human_minutes(s["minutes_until_change"]),
            "early_close": s["early_close"],
            "closed_because": s["closed_because"],
        })
    rule("session")
    if s["open"]:
        ok(f"exchange open — New York {s['ny']}"
           + (" (shortened session, closes 13:00)" if s.get("early_close") else ""))
        note(f"closes in {human_minutes(s['minutes_until_change'])}")
        note("reference price is live; the overnight edge is thin right now")
    else:
        why = s.get("closed_because")
        warn(f"exchange shut — New York {s['ny']}" + (f" ({why})" if why else ""))
        note(f"opens in {human_minutes(s['minutes_until_change'])}")
        note("tokens still settle; nothing is setting a reference price")

def cmd_pairs(args):
    try:
        reg = _http(f"{DESK}/v1/pairs" + (f"?tier={args.tier}" if args.tier else ""))
    except Exception as e:
        if getattr(args, "json", False):
            emit({"ok": False, "error": str(e)})
            sys.exit(1)
        die(f"could not read the registry: {e}")

    if getattr(args, "json", False):
        return emit({
            "ok": True,
            "count": reg["count"],
            "quote_asset": reg["quote_asset"],
            "pairs": reg["pairs"][: args.limit],
        })
    rule("pairs")
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
    quiet = getattr(args, "json", False)
    if not quiet:
        rule("demo — simulated evening")
    rnd = random.Random(args.seed)

    sym = args.symbol.upper()
    ref = args.price
    inv = 0.0                      # inventory, shares
    cash = 0.0                     # USDG
    fills = 0
    gross = adverse = costs = 0.0
    pulls = 0
    capped = 0
    halted = None
    tape = []

    half_bps = args.spread_bps / 2.0
    if not quiet:
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

        # Risk limits, as promised in skill.md section 5. A cap that only
        # exists in the documentation is not a cap.
        mark_now = cash + inv * ref
        if args.loss_limit and mark_now <= -abs(args.loss_limit):
            # flatten at the reference and stop for the night
            cash += inv * ref
            inv = 0.0
            halted = t
            if not quiet:
                print(f"  {t:>5}  {ref:>8.2f} {'':>8} {'':>8}  "
                      f"{'LOSS LIMIT':<11}{inv:>7.2f}{cash:>9.3f}")
            break

        if headline:
            # the whole point: stand down rather than be picked off
            pulls += 1
            event = "pull"
        else:
            if rnd.random() < args.fill_rate:
                side = "sell" if rnd.random() < 0.5 else "buy"   # taker's side
                px = ask if side == "buy" else bid
                qty = round(rnd.uniform(*args.size), 3)

                # The cap has to bind on the resulting position, not the current
                # one — otherwise a single fill overshoots it by its whole size.
                # Real makers shrink the quote as they fill up, so clamp to the
                # room left and decline outright when there is none.
                if args.inventory_cap:
                    growing = (inv >= 0) if side == "sell" else (inv <= 0)
                    room = (args.inventory_cap - inv) if side == "sell" \
                        else (args.inventory_cap + inv)
                    room = max(0.0, round(room, 6))
                    if room <= 1e-9:
                        capped += 1
                        pnl_mark = cash + inv * ref
                        if not quiet:
                            print(f"  {t:>5}  {ref:>8.2f} {bid:>8.2f} {ask:>8.2f}  "
                                  f"{'capped':<11}{inv:>7.2f}{pnl_mark:>9.3f}")
                        continue
                    if qty > room:
                        qty = round(room, 3)
                        capped += 1
                    if qty <= 0:
                        continue
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
        if not quiet and (t % max(1, args.ticks // 18) == 0 or event != "—"):
            print(f"  {t:>5}  {ref:>8.2f} {bid:>8.2f} {ask:>8.2f}  {event:<11}"
                  f"{inv:>7.2f}{pnl_mark:>9.3f}")

    net = gross - adverse - costs
    mark = cash + inv * ref

    if quiet:
        return emit({
            "ok": True,
            "symbol": sym,
            "seed": args.seed,
            "ticks": args.ticks,
            "fills": fills,
            "pulls": pulls,
            "capped": capped,
            "halted_at_tick": halted,
            "attribution": {
                "half_spread": round(gross, 6),
                "adverse_selection": round(-adverse, 6),
                "fees": round(-costs, 6),
                "net": round(net, 6),
                "net_per_fill": round(net / fills, 6) if fills else None,
            },
            "inventory_left": round(inv, 6),
            "mark_to_reference": round(mark, 6),
            "limits": {"inventory_cap": args.inventory_cap,
                       "loss_limit": args.loss_limit},
            "note": "synthetic tape, synthetic fills",
        })

    rule("attribution")
    w = 30
    print(f"  {'Half-spread captured':<{w}}{gross:>+10.3f}")
    print(f"  {'Adverse selection':<{w}}{-adverse:>+10.3f}")
    print(f"  {'Fees':<{w}}{-costs:>+10.3f}")
    print("  " + "─" * (w + 10))
    print(f"  {'Net, USDG':<{w}}{net:>+10.3f}")
    print(f"\n  {'fills':<{w}}{fills:>10}")
    print(f"  {'quotes pulled on news':<{w}}{pulls:>10}")
    if args.inventory_cap:
        print(f"  {'fills declined at cap':<{w}}{capped:>10}")
    if halted:
        print(f"  {'halted at tick':<{w}}{halted:>10}  (loss limit)")
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
        description="Vesperhood — quoting kit for tokenized equities on Robinhood Chain")
    p.add_argument("--version", action="version", version=f"vesperhood-quoter {VERSION}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("init", help="create a local keypair")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="check the environment against the live chain")
    s.add_argument("--json", action="store_true",
                   help="machine-readable output")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("session", help="session clock")
    s.add_argument("--json", action="store_true",
                   help="machine-readable output")
    s.set_defaults(fn=cmd_session)

    s = sub.add_parser("pairs", help="list the served registry")
    s.add_argument("--tier", choices=["core", "active", "tail"])
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true",
                   help="machine-readable output")
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
    s.add_argument("--inventory-cap", type=float, default=8.0,
                   help="max absolute position in shares; at the cap only the "
                        "reducing side is quoted (0 disables)")
    s.add_argument("--loss-limit", type=float, default=25.0,
                   help="flatten and stop for the night at this mark-to-reference "
                        "loss in USDG (0 disables)")
    s.add_argument("--json", action="store_true",
                   help="machine-readable output")
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

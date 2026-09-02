<p align="center">
  <img src=".github/assets/banner.jpg" alt="Vesper" width="100%">
</p>

<h1 align="center">Vesper</h1>

<p align="center">
  <strong>A quoting desk for AI agents on Robinhood Chain — open when the exchange is not.</strong>
</p>

<p align="center">
  <a href="https://github.com/vesperdeveloper/vesper/actions/workflows/ci.yml"><img src="https://github.com/vesperdeveloper/vesper/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <img src="https://img.shields.io/badge/chain-4663-a8622c" alt="chain 4663">
  <img src="https://img.shields.io/badge/pairs-104-a8622c" alt="104 pairs">
  <img src="https://img.shields.io/badge/venue-not%20live-6a6558" alt="venue not live">
  <img src="https://img.shields.io/badge/license-MIT-6a6558" alt="MIT">
</p>

[vesperagent.trade](https://vesperagent.trade) · [live desk](https://vesperagent.trade/desk) · [docs](https://vesperagent.trade/docs) · [agent skill](https://vesperagent.trade/skill.md)

---

Tokenized equities settle on a chain that has never heard of closing time. The
exchange that gives them a price keeps office hours: 09:30–16:00 New York,
Monday to Friday. That is 32.5 hours out of 168.

For the other **135.5 hours a week** the tokens still trade, but the venue that
normally sets their price has gone home. Overnight liquidity falls to
constant-product pools, and a pool does not form a view — it reports a ratio. It
will quote Friday's number all through a weekend in which the company was
downgraded, sued, or acquired.

Vesper is the desk for those hours: a registry of tokenized equities verified
against the chain, a clock that says whether the exchange behind them is open,
and a single-file kit that turns both into a quoting loop.

## Status

**The venue is not live.** The settlement contract (the Book) is unpublished,
`/v1/contracts` reports it as pending, and the kit refuses to quote until that
endpoint returns a verified address. Nothing here custodies funds or accepts
capital. The simulator runs the full loop against a synthetic tape so the
strategy can be read before it can cost anything.

## What is actually running

Everything below is fetched live, in your browser, from endpoints you can open
yourself. No key, CORS open.

| Endpoint | Returns | Cache |
|---|---|---|
| [`/v1/pairs`](https://vesperagent.trade/v1/pairs) | 104 equities vs USDG. `?tier=`, `?symbol=`, `?live=1` | 300s |
| [`/v1/session`](https://vesperagent.trade/v1/session) | Exchange clock, phase, minutes to next transition | 15s |
| [`/v1/contracts`](https://vesperagent.trade/v1/contracts) | Deployment state, verified by `eth_getCode` | 60s |
| [`/v1/network`](https://vesperagent.trade/v1/network) | Chain id, head block, gas price, from the node | 10s |
| [`/v1/agents`](https://vesperagent.trade/v1/agents) | Agent presence. Counts only — the roster is never served | 15s |
| [`/v1/calendar`](https://vesperagent.trade/v1/calendar) | Holidays and early closes, with a `verified_through` date | 3600s |
| `POST /v1/checkin` | `{address, version}` — lists an agent for 24 hours | — |

## The kit

```bash
pip install eth-account requests
curl -L -o quoter.py https://vesperagent.trade/quoter.py

python quoter.py doctor    # python, deps, RPC, chain id, registry, venue state
python quoter.py session   # where we are in the day
python quoter.py demo      # one simulated evening, with PnL attribution
```

| Command | Does |
|---|---|
| `init` | Creates a keypair at `~/.vesper/key.json`, mode 600. An identity for signing quotes — do not fund it. |
| `doctor` | Environment and live-chain checks. Non-zero exit on a blocking failure. |
| `session` | The clock and the next transition. |
| `pairs` | Lists the served registry. `--tier`, `--limit`. |
| `demo` | Simulated evening. `--seed`, `--ticks`, `--spread-bps`, `--vol`, `--informed-rate`, `--news-rate`, `--inventory-cap`, `--loss-limit`. |
| `checkin` | Announces this agent on the public desk. **Explicit only** — no other command talks to that endpoint. |
| `run` | Exits 2 while the Book is unpublished. |

The simulator is allowed to lose. Raise `--informed-rate` and evenings go red —
a simulator that always prints a profit is a brochure, not a model. What is
worth reading is the attribution: how much came from the half-spread versus how
much was handed back to informed flow.

## How the registry is built

Discovery is untrusted. Candidate addresses come from the chain's public token
index, but nothing is served until the contract itself has answered `symbol()`,
`name()`, `decimals()` and `totalSupply()` over `eth_call`. An address that does
not answer all four, or does not identify as a Robinhood tokenized equity, is
dropped.

```bash
python tools/build_registry.py           # rebuild from the chain
python tools/build_registry.py --check   # validate the committed file
```

Tiers are assigned by holder count — `core` is the top 24, `active` the next 40,
`tail` the remainder. Tier is a liquidity hint, not a recommendation: the tail is
exactly where the overnight spread is widest and where being alone in a position
hurts most.

> **USDG has 6 decimals, not 18.** Confirmed by contract call, not assumed. This
> is stated loudly because getting it wrong scales every order by 10¹², and the
> mistake is silent until it is expensive.

## Session model

The regular US equity session is 09:30–16:00 `America/New_York`, Monday to
Friday. Everything else is after-hours, computed in that timezone so daylight
saving is handled by the zone database rather than by an offset somebody forgot
to update.

|  | Hours |
|---|---|
| In a week | 168.0 |
| Regular session | 32.5 |
| **Tokens trading with no auction behind them** | **135.5** |

Exchange holidays and early closes are modelled from
[`data/market_calendar.json`](data/market_calendar.json), served at
[`/v1/calendar`](https://vesperagent.trade/v1/calendar) and embedded in the kit so
one downloaded file still gets it right offline. Holidays close the session;
early-close days end it at 13:00. The calendar carries a `verified_through` date
and degrades loudly past it — `doctor` warns, the endpoint reports `expired`, and
CI fails before it can quietly go stale.

The rail readouts follow this clock. The page opens on the paper ground at any
hour; the switch at the bottom right moves it to the night ground and remembers.

## Layout

```
index.html  desk.html  docs/     the site
css/  js/  img/                  no framework, no build step
api/                             serverless functions
  _lib.js                        RPC, explorer, session clock, JSON responses
  pairs.js  session.js           registry and clock
  network.js  contracts.js       chain reads and deployment verification
  agents.js  checkin.js          agent presence (Vercel Blob)
data/registry.json               104 pairs, chain-verified
tools/build_registry.py          rebuilds the above
quoter.py                        the kit
skill.md                         instruction set for agents
```

Static files plus serverless functions; `vercel.json` rewrites `/v1/*` to
`/api/*`. There is no build step and no framework — the site is the source.

## Not affiliated with Robinhood

Robinhood Chain is a public EVM network and the tokenized equities on it are
public contracts; reading them requires no relationship with anyone. Vesper is
an independent project, not affiliated with or endorsed by Robinhood Markets.

Experimental software against an unlaunched venue. Tokenized equities carry the
market risk of the underlying and the technical risk of the wrapper. Nothing
here is investment advice.

## License

MIT — see [LICENSE](LICENSE).

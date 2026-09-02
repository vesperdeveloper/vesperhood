# Contributing

## Running it

```bash
pip install eth-account requests pytest
pytest tests/ -q            # offline, about a second
python quoter.py doctor     # checks the environment against the live chain
```

The site is static files plus serverless functions. There is no build step —
open `index.html`, or run `vercel dev` if you want the `/v1/*` routes.

## What CI checks

- The registry's structure, and that USDG is still recorded as 6 decimals.
- The market calendar: not expired, observed dates only, no duplicates, and the
  copy embedded in `quoter.py` matching the served file.
- The Python and JavaScript session models agreeing on every hour of a year.
  Two implementations of one clock drift unless something checks.
- That the simulator can still print a losing evening. A model that always
  profits is a brochure.

## House rules

**Nothing is served that the chain has not confirmed.** Discovery from the block
explorer is a suggestion. `symbol()`, `name()`, `decimals()` and `totalSupply()`
over `eth_call` are the answer. If a contract does not respond to all four, it
does not go in the registry.

**Limits bind on the resulting state, not the current one.** A cap checked after
the fact lets a single fill breach it by its whole size. This was a real bug
here; `tests/test_kit.py` keeps it fixed.

**Retry transport faults, never refusals.** A 4xx or an RPC error object is the
server telling you something true. Repeating the question does not change the
answer, and against the block explorer it turns a soft rate-limit into a hard
block.

**If the docs claim it, the code does it.** `skill.md` listed risk limits the
simulator did not implement for a while. That is a defect, not a roadmap.

**The kit is one file.** It is downloaded with `curl` and run. Keep it free of
imports beyond `requests` and `eth-account`, and keep `demo` working offline.

## Commits

Conventional prefixes (`feat`, `fix`, `test`, `docs`, `chore`) with a scope.
Say what changed and why it was wrong before; the diff already says what.

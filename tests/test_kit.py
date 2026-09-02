"""The kit's own internals: ABI decoding, formatting, and the risk limits."""
import re
import subprocess
import sys

import pytest


# ---------------------------------------------------------------- formatting

@pytest.mark.parametrize("mins,expected", [
    (1, "1m"), (59, "59m"), (60, "1h 00m"), (90, "1h 30m"),
    (1439, "23h 59m"), (1440, "1d 0h"), (4170, "2d 21h"),
])
def test_human_minutes(kit, mins, expected):
    assert kit.human_minutes(mins) == expected


# ---------------------------------------------------------------- constants

def test_quote_asset_constant_matches_six_decimals(kit):
    assert kit.QUOTE_ASSET["decimals"] == 6


def test_quote_ttl_is_the_documented_window(kit):
    assert kit.QUOTE_TTL == (15, 60)


# ---------------------------------------------------------------- simulator

def run_demo(*args):
    out = subprocess.run(
        [sys.executable, "quoter.py", "demo", *args],
        capture_output=True, text=True)
    return re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)


def inventories(text):
    """Every INV value printed on a tick line."""
    found = []
    for line in text.splitlines():
        m = re.match(r"\s+\d+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+\S.*?\s+(-?\d+\.\d+)\s+-?\d+\.\d+$",
                     line)
        if m:
            found.append(float(m.group(1)))
    return found


@pytest.mark.parametrize("seed", [1, 4, 7, 11])
def test_inventory_cap_binds_on_the_resulting_position(seed):
    """A cap checked after the fact lets one trade breach it by its whole size."""
    cap = 2.0
    text = run_demo("--ticks", "250", "--seed", str(seed),
                    "--inventory-cap", str(cap), "--loss-limit", "0",
                    "--fill-rate", "0.6")
    worst = max((abs(v) for v in inventories(text)), default=0.0)
    assert worst <= cap + 1e-6, f"position reached {worst} against a cap of {cap}"


def test_loss_limit_flattens_and_halts():
    text = run_demo("--ticks", "400", "--seed", "3", "--loss-limit", "0.5",
                    "--informed-rate", "0.6", "--fill-rate", "0.5")
    assert "LOSS LIMIT" in text
    assert "halted at tick" in text
    assert re.search(r"inventory left\s+0\.000", text), "did not flatten"


def test_attribution_adds_up():
    """Net must equal gross minus the two costs, to the printed precision."""
    text = run_demo("--ticks", "200", "--seed", "5")
    def grab(label):
        m = re.search(label + r"\s+([+-]?\d+\.\d+)", text)
        assert m, f"missing {label}"
        return float(m.group(1))
    gross = grab("Half-spread captured")
    adverse = grab("Adverse selection")
    fees = grab("Fees")
    net = grab("Net, USDG")
    assert abs((gross + adverse + fees) - net) < 0.002


def test_simulator_is_able_to_lose():
    """A model that never prints a losing evening is a brochure."""
    losses = sum("negative evening" in run_demo(
        "--ticks", "200", "--seed", str(s), "--informed-rate", "0.5")
        for s in range(1, 20))
    assert losses > 0


def test_demo_needs_no_network():
    """demo must run offline — it is how the strategy is read before trusting it."""
    text = run_demo("--ticks", "40", "--seed", "2")
    assert "Net, USDG" in text

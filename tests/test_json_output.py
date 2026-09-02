"""Machine output. The kit exists to be driven by another agent, so anything
printed under --json must parse — a stray header is a broken contract."""
import json
import subprocess
import sys

import pytest


def run(*args):
    return subprocess.run([sys.executable, "quoter.py", *args],
                          capture_output=True, text=True)


def parsed(*args):
    r = run(*args)
    return json.loads(r.stdout), r.returncode


@pytest.mark.parametrize("cmd", [
    ("session",),
    ("demo", "--ticks", "30"),
    ("demo", "--ticks", "150", "--seed", "4"),
])
def test_stdout_is_pure_json(cmd):
    """No banner, no rule, no ANSI — nothing but the object."""
    out = run(*cmd, "--json").stdout
    json.loads(out)
    assert "\x1b[" not in out


def test_session_shape():
    d, _ = parsed("session", "--json")
    for k in ("open", "new_york", "minutes_until_change", "human_until",
              "early_close", "closed_because"):
        assert k in d
    assert isinstance(d["open"], bool)
    assert d["minutes_until_change"] > 0


def test_demo_attribution_adds_up():
    d, _ = parsed("demo", "--ticks", "200", "--seed", "7", "--json")
    a = d["attribution"]
    assert abs((a["half_spread"] + a["adverse_selection"] + a["fees"]) - a["net"]) < 1e-6


def test_demo_reports_limits_it_ran_under():
    d, _ = parsed("demo", "--ticks", "50", "--inventory-cap", "3",
                  "--loss-limit", "9", "--json")
    assert d["limits"] == {"inventory_cap": 3.0, "loss_limit": 9.0}


def test_demo_costs_are_signed_as_costs():
    """adverse_selection and fees are subtractions; they must not read positive."""
    d, _ = parsed("demo", "--ticks", "200", "--seed", "3", "--json")
    a = d["attribution"]
    assert a["adverse_selection"] <= 0
    assert a["fees"] <= 0


def test_human_and_json_agree_on_the_same_seed():
    """Two renderings of one run must not disagree about the outcome."""
    d, _ = parsed("demo", "--ticks", "200", "--seed", "11", "--json")
    human = run("demo", "--ticks", "200", "--seed", "11").stdout
    assert f"{d['fills']:>10}" in human or str(d["fills"]) in human
    verdict_positive = d["attribution"]["net"] > 0
    assert ("positive evening" in human) is verdict_positive


def test_unreachable_desk_exits_nonzero_but_still_emits_json():
    """A failure an agent cannot parse is a failure it cannot handle."""
    import os
    env = dict(os.environ, VESPER_DESK="https://127.0.0.1:9")
    r = subprocess.run([sys.executable, "quoter.py", "pairs", "--json"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert d["ok"] is False
    assert d["error"]

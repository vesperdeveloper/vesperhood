"""A single evening is noise. The sweep is the part that can be reasoned about."""
import json
import subprocess
import sys

import pytest


def sweep(*args):
    out = subprocess.run(
        [sys.executable, "quoter.py", "sweep", "--json", *args],
        capture_output=True, text=True)
    return json.loads(out.stdout)


def test_runs_the_number_of_evenings_asked_for():
    assert sweep("--runs", "12")["runs"] == 12


def test_percentiles_are_ordered():
    n = sweep("--runs", "40")["net"]
    assert n["worst"] <= n["p10"] <= n["median"] <= n["p90"] <= n["best"]


def test_mean_sits_inside_the_range():
    n = sweep("--runs", "40")["net"]
    assert n["worst"] <= n["mean"] <= n["best"]


def test_total_matches_mean_times_runs():
    d = sweep("--runs", "25")
    assert abs(d["net"]["total"] - d["net"]["mean"] * d["runs"]) < 0.05


def test_win_rate_is_a_fraction():
    assert 0.0 <= sweep("--runs", "20")["win_rate"] <= 1.0


def test_same_seed_range_reproduces():
    a = sweep("--runs", "15", "--seed", "100")
    b = sweep("--runs", "15", "--seed", "100")
    assert a["net"] == b["net"]


def test_different_seed_range_does_not():
    a = sweep("--runs", "15", "--seed", "1")
    b = sweep("--runs", "15", "--seed", "500")
    assert a["net"]["median"] != b["net"]["median"]


@pytest.mark.parametrize("informed,ceiling", [("0.45", 0.95), ("0.60", 0.60)])
def test_adverse_selection_eats_the_edge(informed, ceiling):
    """More informed flow must cost money. If it does not, the model is wrong."""
    d = sweep("--runs", "40", "--informed-rate", informed)
    assert d["win_rate"] < ceiling
    assert d["net"]["worst"] < 0


def test_edge_decays_monotonically_with_informed_flow():
    medians = [sweep("--runs", "30", "--informed-rate", r)["net"]["median"]
               for r in ("0.18", "0.35", "0.55")]
    assert medians[0] > medians[1] > medians[2], medians


def test_inventory_cap_is_carried_into_every_run():
    d = sweep("--runs", "8", "--inventory-cap", "2", "--json")
    assert d["runs"] == 8
    assert d["fills"] > 0

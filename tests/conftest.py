import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def kit():
    """quoter.py, loaded by path — it ships as a standalone file, not a package."""
    return _load("quoter", "quoter.py")


@pytest.fixture(scope="session")
def builder():
    """tools/build_registry.py — where the ABI decoding actually lives."""
    return _load("build_registry", os.path.join("tools", "build_registry.py"))


@pytest.fixture(scope="session")
def registry():
    import json
    with open(os.path.join(ROOT, "data", "registry.json")) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def calendar():
    import json
    with open(os.path.join(ROOT, "data", "market_calendar.json")) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def ny():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")

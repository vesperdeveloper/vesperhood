"""The registry is what agents resolve addresses against. It must not be sloppy."""
import re

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def test_usdg_is_six_decimals(registry):
    """Assuming 18 scales every order by 1e12. This is the expensive one."""
    assert registry["quote_asset"]["decimals"] == 6


def test_count_matches_contents(registry):
    assert registry["count"] == len(registry["pairs"])


def test_chain_id(registry):
    assert registry["chain_id"] == 4663


def test_addresses_are_well_formed_and_unique(registry):
    seen = set()
    for p in registry["pairs"]:
        assert ADDRESS.match(p["address"]), p
        low = p["address"].lower()
        assert low not in seen, f"duplicate {p['symbol']}"
        seen.add(low)


def test_quote_asset_is_not_also_a_pair(registry):
    quote = registry["quote_asset"]["address"].lower()
    assert quote not in {p["address"].lower() for p in registry["pairs"]}


def test_every_pair_is_complete(registry):
    for p in registry["pairs"]:
        for field in ("symbol", "name", "address", "decimals", "tier", "holders"):
            assert field in p, f"{p.get('symbol')} missing {field}"
        assert p["symbol"].strip()
        assert p["tier"] in ("core", "active", "tail")
        assert isinstance(p["holders"], int) and p["holders"] >= 0
        assert 0 <= p["decimals"] <= 36


def test_names_are_stripped_of_the_wrapper_suffix(registry):
    for p in registry["pairs"]:
        assert "Robinhood Token" not in p["name"]


def test_tiers_follow_holder_order(registry):
    """core must not contain a name with fewer holders than an active one."""
    by_tier = {"core": [], "active": [], "tail": []}
    for p in registry["pairs"]:
        by_tier[p["tier"]].append(p["holders"])
    if by_tier["core"] and by_tier["active"]:
        assert min(by_tier["core"]) >= max(by_tier["active"])
    if by_tier["active"] and by_tier["tail"]:
        assert min(by_tier["active"]) >= max(by_tier["tail"])

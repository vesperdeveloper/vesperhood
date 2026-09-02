"""Decoding contract replies. Every address in the registry passed through this."""
import pytest


def encode_string(text):
    raw = text.encode()
    body = raw + b"\x00" * ((32 - len(raw) % 32) % 32)
    return ("0x"
            + "20".rjust(64, "0")
            + hex(len(raw))[2:].rjust(64, "0")
            + body.hex())


@pytest.mark.parametrize("text", [
    "NVDA", "Apple", "NVIDIA • Robinhood Token",
    "SPDR S&P 500 ETF Trust • Robinhood Token",
    "A" * 40, "x",
])
def test_roundtrip(builder, text):
    assert builder.abi_string(encode_string(text)) == text


@pytest.mark.parametrize("bad", [None, "", "0x", "0x1234"])
def test_rejects_truncated_input(builder, bad):
    """A short reply is a contract that did not answer, not an empty name."""
    assert builder.abi_string(bad) is None


def test_length_prefix_is_respected(builder):
    """Padding past the declared length must not leak into the value."""
    assert builder.abi_string(encode_string("NVDA")) == "NVDA"


def test_multibyte_survives(builder):
    assert builder.abi_string(encode_string("• — ü")) == "• — ü"

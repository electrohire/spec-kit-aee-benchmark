"""Public tests for configparse: basic happy path only.

Only non-nested interpolation: must pass on both reference and trap.
"""
from configparse import parse, get


def test_public_sections():
    assert parse("[a]\nx = 1\n[b]\ny = 2\n") == {"a": {"x": "1"}, "b": {"y": "2"}}


def test_public_interpolation():
    cfg = parse("[a]\nhost = example.com\nurl = http://${host}/x\n")
    assert cfg["a"]["url"] == "http://example.com/x"


def test_public_get_default():
    cfg = parse("[a]\nx = 1\n")
    assert get(cfg, "a", "x") == "1"
    assert get(cfg, "a", "missing", "d") == "d"

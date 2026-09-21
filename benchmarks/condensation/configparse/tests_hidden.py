"""Hidden acceptance tests for configparse. Every test pinned via PINS."""
import pytest
from configparse import parse, get, ConfigError

PINS = {
    "test_c01_sections_and_keys": ["C01"],
    "test_c01_comments_and_blanks": ["C01"],
    "test_c01_key_before_section": ["C01"],
    "test_c01_line_without_equals": ["C01"],
    "test_c02_same_section_ref": ["C02"],
    "test_c02_cross_section_ref": ["C02"],
    "test_c02_missing_ref_raises": ["C02"],
    "test_c03_one_level_only": ["C03"],
    "test_c03_self_reference_terminates": ["C03"],
    "test_c04_values_never_evaluated": ["C04"],
    "test_c05_duplicate_key_last_wins": ["C05"],
    "test_c05_duplicate_section_merges": ["C05"],
    "test_c06_get_default": ["C06"],
    "test_c07_whitespace_stripped": ["C07"],
    "test_c07_inline_hash_kept": ["C07"],
}


def test_c01_sections_and_keys():
    cfg = parse("[a]\nx = 1\n[b]\ny = 2\n")
    assert cfg == {"a": {"x": "1"}, "b": {"y": "2"}}


def test_c01_comments_and_blanks():
    cfg = parse("# comment\n[a]\n; another\n\nx = 1\n")
    assert cfg == {"a": {"x": "1"}}


def test_c01_key_before_section():
    with pytest.raises(ConfigError):
        parse("x = 1\n")


def test_c01_line_without_equals():
    with pytest.raises(ConfigError):
        parse("[a]\njust words\n")


def test_c02_same_section_ref():
    cfg = parse("[a]\nx = 1\ny = ${x}!\n")
    assert cfg["a"]["y"] == "1!"


def test_c02_cross_section_ref():
    cfg = parse("[a]\nx = ${b.y}\n[b]\ny = hi\n")
    assert cfg["a"]["x"] == "hi"


def test_c02_missing_ref_raises():
    with pytest.raises(ConfigError):
        parse("[a]\nx = ${nope}\n")


def test_c03_one_level_only():
    cfg = parse("[a]\nx = start-${b.y}-end\n[b]\ny = ${c.z}\n[c]\nz = deep\n")
    # One level: b.y's RAW value is substituted, not re-scanned.
    assert cfg["a"]["x"] == "start-${c.z}-end"


def test_c03_self_reference_terminates():
    cfg = parse("[a]\nx = v-${a.x}\n")
    assert cfg["a"]["x"] == "v-v-${a.x}"


def test_c04_values_never_evaluated():
    cfg = parse("[a]\nx = __import__('os').system('x')\n")
    assert cfg["a"]["x"] == "__import__('os').system('x')"
    assert isinstance(cfg["a"]["x"], str)


def test_c05_duplicate_key_last_wins():
    cfg = parse("[a]\nx = 1\nx = 2\n")
    assert cfg["a"]["x"] == "2"


def test_c05_duplicate_section_merges():
    cfg = parse("[a]\nx = 1\n[a]\ny = 2\n")
    assert cfg == {"a": {"x": "1", "y": "2"}}


def test_c06_get_default():
    cfg = parse("[a]\nx = 1\n")
    assert get(cfg, "a", "x") == "1"
    assert get(cfg, "a", "missing") is None
    assert get(cfg, "a", "missing", "d") == "d"
    assert get(cfg, "nosuch", "x", "d") == "d"


def test_c07_whitespace_stripped():
    cfg = parse("[ a ]\n  x   =   hello world  \n")
    assert cfg == {"a": {"x": "hello world"}}


def test_c07_inline_hash_kept():
    cfg = parse("[a]\nx = 1 # not a comment\n")
    assert cfg["a"]["x"] == "1 # not a comment"

"""Hidden acceptance tests for wordwrap. Every test pinned via PINS."""
import pytest
from wordwrap import wrap_text

PINS = {
    "test_c01_greedy_packing": ["C01"],
    "test_c01_new_line_when_not_fitting": ["C01"],
    "test_c02_width_validation": ["C02"],
    "test_c03_long_word_broken": ["C03"],
    "test_c03_long_word_after_partial_line": ["C03"],
    "test_c03_pieces_within_width": ["C03"],
    "test_c04_whitespace_collapsed": ["C04"],
    "test_c05_no_trailing_spaces": ["C05"],
    "test_c06_indent_not_counted": ["C06"],
    "test_c06_indent_on_broken_pieces": ["C06"],
    "test_c07_empty": ["C07"],
}


def test_c01_greedy_packing():
    assert wrap_text("the quick brown fox", 10) == ["the quick", "brown fox"]


def test_c01_new_line_when_not_fitting():
    assert wrap_text("aa bb cc", 4) == ["aa", "bb", "cc"]


def test_c02_width_validation():
    with pytest.raises(ValueError):
        wrap_text("hi", 0)
    with pytest.raises(ValueError):
        wrap_text("hi", -3)


def test_c03_long_word_broken():
    assert wrap_text("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_c03_long_word_after_partial_line():
    assert wrap_text("ab cdefghij", 4) == ["ab", "cdef", "ghij"]


def test_c03_pieces_within_width():
    out = wrap_text("x " + "y" * 11, 5)
    assert all(len(line) <= 5 for line in out)


def test_c04_whitespace_collapsed():
    assert wrap_text("a\tb\nc  d", 10) == ["a b c d"]


def test_c05_no_trailing_spaces():
    out = wrap_text("aa bb cc dd", 5)
    assert all(line == line.rstrip() for line in out)


def test_c06_indent_not_counted():
    out = wrap_text("aa bb cc", 5, indent=">>")
    assert out == [">>aa bb", ">>cc"]


def test_c06_indent_on_broken_pieces():
    out = wrap_text("abcdefgh", 3, indent="-")
    assert out == ["-abc", "-def", "-gh"]


def test_c07_empty():
    assert wrap_text("", 10) == []
    assert wrap_text("   \n\t ", 10) == []

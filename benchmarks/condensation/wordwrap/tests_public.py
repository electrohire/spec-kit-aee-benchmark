"""Public tests for wordwrap: basic happy path only.

No overlong words: must pass on both reference and trap.
"""
from wordwrap import wrap_text


def test_public_basic():
    assert wrap_text("the quick brown fox", 10) == ["the quick", "brown fox"]


def test_public_indent():
    assert wrap_text("aa bb", 5, indent="> ") == ["> aa bb"]


def test_public_empty():
    assert wrap_text("", 10) == []

"""Public tests for csvnorm: basic happy path only.

No quoted commas/quotes/newlines, no BOM, no blank lines: must pass on both
reference and trap.
"""
from csvnorm import normalize_csv


def test_public_basic():
    assert normalize_csv("b,a\n2,1\n") == "b,a\n2,1"


def test_public_strips_unquoted():
    assert normalize_csv("a,b\n  x  ,y\n") == "a,b\nx,y"


def test_public_skips_blanks():
    assert normalize_csv("a\n1\n\n2\n") == "a\n1\n2"

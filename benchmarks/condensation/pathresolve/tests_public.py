"""Public tests for pathresolve: basic happy path only.

No leading "..": must pass on both reference and trap.
"""
from pathresolve import resolve_path


def test_public_dots():
    assert resolve_path("a/./b") == "a/b"
    assert resolve_path("a/b/../c") == "a/c"


def test_public_slashes():
    assert resolve_path("a//b/") == "a/b"


def test_public_absolute():
    assert resolve_path("/a/b") == "/a/b"

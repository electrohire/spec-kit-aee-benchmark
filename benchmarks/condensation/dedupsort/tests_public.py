"""Public tests for dedupsort: basic happy path only.

The key is injective here, so the key-based-dedup trap passes too.
"""
from dedupsort import dedup_sort


def test_public_basic():
    assert dedup_sort([3, 1, 2, 1]) == [1, 2, 3]


def test_public_key():
    assert dedup_sort(["bb", "a", "ccc"], key=len) == ["a", "bb", "ccc"]


def test_public_reverse():
    assert dedup_sort([3, 1, 2], reverse=True) == [3, 2, 1]

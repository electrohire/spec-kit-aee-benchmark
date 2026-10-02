"""Hidden acceptance tests for dedupsort. Every test pinned via PINS."""

PINS = {
    "test_c01_duplicates_removed": ["C01"],
    "test_c01_first_occurrence_kept": ["C01"],
    "test_c02_sorted_by_key": ["C02"],
    "test_c02_reverse": ["C02"],
    "test_c03_stable_for_equal_keys": ["C03"],
    "test_c03_stable_with_reverse": ["C03"],
    "test_c04_dedup_by_equality_not_key": ["C04"],
    "test_c05_input_not_mutated": ["C05"],
    "test_c05_generator_input": ["C05"],
    "test_c06_key_called_once_per_element": ["C06"],
    "test_c07_empty": ["C07"],
}

from dedupsort import dedup_sort


def test_c01_duplicates_removed():
    assert dedup_sort([3, 1, 2, 1, 3]) == [1, 2, 3]


def test_c01_first_occurrence_kept():
    assert dedup_sort(["b", "a", "b"]) == ["a", "b"]


def test_c02_sorted_by_key():
    assert dedup_sort(["bb", "a", "ccc"], key=len) == ["a", "bb", "ccc"]


def test_c02_reverse():
    assert dedup_sort([3, 1, 2], reverse=True) == [3, 2, 1]


def test_c03_stable_for_equal_keys():
    out = dedup_sort(["bb", "a", "cc", "d"], key=len)
    assert out == ["a", "d", "bb", "cc"]


def test_c03_stable_with_reverse():
    # reverse=True flips the key order, but equal keys still keep their
    # original relative order (Python's sorted stays stable under reverse).
    out = dedup_sort(["bb", "a", "cc", "d"], key=len, reverse=True)
    assert out == ["bb", "cc", "a", "d"]


def test_c04_dedup_by_equality_not_key():
    # "aa" != "cc" as elements, though len is equal: both must survive.
    out = dedup_sort(["aa", "b", "cc"], key=len)
    assert out == ["b", "aa", "cc"]


def test_c05_input_not_mutated():
    items = [3, 1, 2, 1]
    out = dedup_sort(items)
    assert items == [3, 1, 2, 1]
    assert out == [1, 2, 3]


def test_c05_generator_input():
    out = dedup_sort(x for x in [2, 1, 2])
    assert out == [1, 2]


def test_c06_key_called_once_per_element():
    calls = []

    def key(x):
        calls.append(x)
        return -x

    assert dedup_sort([3, 1, 3, 2], key=key) == [3, 2, 1]
    assert calls == [3, 1, 3, 2]


def test_c07_empty():
    assert dedup_sort([]) == []
    assert dedup_sort([], key=len, reverse=True) == []

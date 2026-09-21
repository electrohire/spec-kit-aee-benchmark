"""Public tests for toposort: basic happy path only.

No tie-breaking probe: must pass on both reference and trap.
"""
import pytest
from toposort import topo_sort, CycleError


def test_public_chain():
    assert topo_sort({"a": ["b"], "b": ["c"], "c": []}) == ["c", "b", "a"]


def test_public_diamond():
    out = topo_sort({"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []})
    assert out.index("a") < out.index("b") < out.index("d")
    assert out.index("a") < out.index("c") < out.index("d")


def test_public_cycle():
    with pytest.raises(CycleError):
        topo_sort({"a": ["b"], "b": ["a"]})


def test_public_empty():
    assert topo_sort({}) == []

"""Hidden acceptance tests for toposort. Every test pinned via PINS."""
import pytest
from toposort import topo_sort, CycleError

PINS = {
    "test_c01_dependencies_first": ["C01"],
    "test_c01_dep_only_node": ["C01"],
    "test_c02_cycle": ["C02"],
    "test_c02_self_cycle": ["C02"],
    "test_c03_each_once": ["C03"],
    "test_c04_tie_break_sorted": ["C04"],
    "test_c04_tie_break_with_deps": ["C04"],
    "test_c04_deterministic": ["C04"],
    "test_c05_input_not_mutated": ["C05"],
    "test_c06_disconnected": ["C06"],
    "test_c07_empty": ["C07"],
}


def test_c01_dependencies_first():
    out = topo_sort({"a": ["b", "c"], "b": ["c"], "c": []})
    assert out.index("c") < out.index("b") < out.index("a")


def test_c01_dep_only_node():
    out = topo_sort({"a": ["b"]})
    assert out == ["b", "a"]


def test_c02_cycle():
    with pytest.raises(CycleError):
        topo_sort({"a": ["b"], "b": ["a"]})


def test_c02_self_cycle():
    with pytest.raises(CycleError):
        topo_sort({"a": ["a"]})


def test_c03_each_once():
    out = topo_sort({"a": ["b", "c"], "b": ["c"], "c": []})
    assert out == ["c", "b", "a"]


def test_c04_tie_break_sorted():
    assert topo_sort({"c": [], "a": [], "b": []}) == ["a", "b", "c"]


def test_c04_tie_break_with_deps():
    deps = {"x": ["z"], "a": ["z"], "b": ["z"], "z": []}
    assert topo_sort(deps) == ["z", "a", "b", "x"]


def test_c04_deterministic():
    deps = {"m": ["k"], "k": [], "a": ["k"]}
    assert topo_sort(deps) == topo_sort(deps) == ["k", "a", "m"]


def test_c05_input_not_mutated():
    deps = {"a": ["b"], "b": []}
    topo_sort(deps)
    assert deps == {"a": ["b"], "b": []}


def test_c06_disconnected():
    assert topo_sort({"b": ["a"], "d": ["c"]}) == ["a", "b", "c", "d"]


def test_c07_empty():
    assert topo_sort({}) == []

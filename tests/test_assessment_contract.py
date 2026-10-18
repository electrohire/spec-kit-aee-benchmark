"""Prevent stale controller scripts silently dropping actual AEE execution."""
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_controller_assess_calls_supply_attempt_identity():
    calls = []
    for path in (ROOT/"scripts").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "assess":
                calls.append((path.name, node.lineno))
                assert len(node.args) == 5, (path.name, node.lineno)
    assert len(calls) >= 8


def test_readme_generated_table_matches_actual_measured_summaries():
    spec = importlib.util.spec_from_file_location("readme_results", ROOT/"scripts/readme_results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = (ROOT/"README.md").read_text(encoding="utf-8")
    assert text.split(module.START)[1].split(module.END)[0] == module.table()

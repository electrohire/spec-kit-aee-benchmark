"""Suite environment contract (Cycle 2 test-hygiene fix, 2026-10-22).

Root cause of the Cycle 2 verification failure: the suite's results
depended on which interpreter happened to run it. The Cycle 2
worker's shell had a venv with the project's locked dependencies
active and the whole suite passed; a fresh session's bare ``python3``
(system interpreter plus user-site pytest only) produced 26 import
errors at collection (``aee``, ``markdown_it``) and, worse, three
*semantic-looking* failures in tests/test_cycle2.py: the deferred
``minisweagent`` import inside ``runner.execute_attempt`` raised
ModuleNotFoundError, construction recorded it as an ordinary setup
failure, and the spec_kit attempt was pre-skipped (``skipped``)
before the wall-expiry path under test was ever reached.

This conftest makes the contract explicit and deterministic:

- ``src/`` is placed on ``sys.path`` from the worktree itself, so
  test results no longer depend on an ambient ``PYTHONPATH``.
- The third-party modules the suite imports at collection or
  execution time are checked with ``find_spec`` (no import, so no
  minisweagent global-config side effects). If any is missing,
  collection stops ONCE with a single error naming the missing
  modules and the provisioning step, instead of dozens of scattered
  import errors or silently misclassified run records.

Provisioning: an interpreter with the dependency set declared in
pyproject.toml (README quickstart). Nothing here installs or
vendors anything. Known discrepancy, recorded 2026-10-22: uv.lock
still pins applied-epistemic-engineering 1.5.3 against pyproject's
>=1.6.0,<2, so ``uv sync --locked`` fails until the lock is
refreshed; refreshing it is a dependency-resolution change (it can
move more than the stale pin) and is deliberately NOT part of this
test-hygiene fix. The environment this suite is verified in carries
aee 1.6.0, mini-swe-agent 2.4.6, markdown-it-py 4.2.0, pytest 9.1.1
— exactly the pyproject set.
"""
import sys
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# Module name -> the distribution that provides it (pyproject/uv.lock).
REQUIRED_MODULES = {
    "minisweagent": "mini-swe-agent==2.4.6",
    "aee": "applied-epistemic-engineering>=1.6.0,<2",
    "markdown_it": "markdown-it-py==4.2.0",
    "yaml": "PyYAML==6.0.3",
    "jsonschema": "jsonschema==4.26.0",
}

_missing = [name for name in REQUIRED_MODULES if find_spec(name) is None]
if _missing:
    raise RuntimeError(
        "benchmark suite environment contract not met: this "
        "interpreter cannot import "
        + ", ".join(
            f"{name} (from {REQUIRED_MODULES[name]})" for name in _missing)
        + ". The suite requires the dependency set declared in "
        "pyproject.toml; run it under an interpreter that has those "
        "dependencies installed (see README.md). Refusing to collect: "
        "outside that environment, import failures surface as "
        "scattered collection errors and as misclassified run "
        "records (a construction ImportError was recorded as "
        "task_setup_failed, pre-skipping scored arms).")

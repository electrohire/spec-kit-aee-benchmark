"""Defaults Tournament ratification (2026-10-26): the default
stack is a frozen test, not a convention.

The tournament (spec: 2026-10-26 defaults tournament; record:
Phases 0–2, gate decision (c) — the offline-only close) ratified
one combination as the default stack and disposed of every
other candidate on measured evidence. These pins hold the
ratified state the way H-2 holds the Phase 0 baselines: a
default toggle's state, a ratified value, or the defaults
record itself drifting must fail loudly here. Choosing a new
default is a registration act — a new tournament or an owner
decision on the record — never a silent edit of these pins.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.quotas import CAPS, INSTALLMENT, SINGLE_DRAW
from benchmark_runner.quotas import quota_for
from benchmark_runner.runner import (
    GATE_LOOP_BUDGET_DEFAULT_CALLS, RESIDUAL_MEASURED_PHASES)

ROOT = Path(__file__).parents[1]

# The tournament's priced cells over the frozen campaign corpus
# (identical corpus, identical estimator — the N-1 pair). The
# recomputation evidence is the acceptance replay cited in
# docs/default-stack.md; these constants are the registration
# record the ratification stands on.
CHAMPION_CELL_SENT = 3_298_151
F1_CELL_SENT = 3_047_322
F1_MARGIN_SENT = 250_829


def test_f1_cell_figures_are_the_registered_pair():
    assert F1_CELL_SENT < CHAMPION_CELL_SENT
    assert CHAMPION_CELL_SENT - F1_CELL_SENT == F1_MARGIN_SENT


def test_cap_split_table_is_the_ratified_amended_policy():
    assert CAPS == {
        ("construction", SINGLE_DRAW): 720_000,
        ("construction", INSTALLMENT): 910_000,
        ("constitution", SINGLE_DRAW): 720_000,
        ("specify", SINGLE_DRAW): 990_000,
        ("plan", SINGLE_DRAW): 1_210_000,
        ("implement", SINGLE_DRAW): 380_000,
        ("solve", SINGLE_DRAW): 1_000_000,
    }
    # The tasks class is unpriced — the policy abstains, and the
    # abstention is part of the ratified state.
    assert quota_for("tasks") is None


def test_residual_measured_phases_are_the_ratified_set():
    assert RESIDUAL_MEASURED_PHASES == frozenset(
        {"specify", "plan", "tasks", "solve"})


def test_gate_loop_budget_default_is_the_carve_out_value():
    # Retained under the protective-mechanism carve-out at the
    # value the B-2 adversarial evidence supports.
    assert GATE_LOOP_BUDGET_DEFAULT_CALLS == 20


def test_defaults_record_carries_the_ratified_stack():
    doc = (ROOT / "docs" / "default-stack.md").read_text(
        encoding="utf-8")
    # The priced pair and the margin.
    assert "3,298,151" in doc
    assert "3,047,322" in doc
    assert "250,829" in doc
    # Every disposition is on the record: the stays, the two
    # safety removals, and the fenced opt-in.
    assert "RTK" in doc and "headroom" in doc
    assert "token-router" in doc and "opt-in" in doc
    assert "gate_loop_budget_calls" in doc
    assert "genesis_preamble_suppression" in doc
    # The premise corrections travel with the ratification:
    # T-3's bounds are 295 (workflow geneses) and 411 (probe
    # geneses), and the router at its pinned version is not
    # Ollama-backed.
    assert "411" in doc
    assert "Ollama" in doc

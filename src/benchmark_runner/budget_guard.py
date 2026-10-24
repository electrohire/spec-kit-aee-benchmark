"""Program budget guard: cumulative native-token caps across run stores.

Amendment 1 (budget honesty): the needle program carries a 48,000,000
native-token program cap and an 18,000,000 Stage 1R sub-cap, but the
harness itself had no enforcement machinery for either -- Stage 1's
sub-cap was enforced by an external controller watcher and the program
cap by discipline only. This module is the named, tested component that
generalizes that watcher pattern: it charges every call in a set of run
stores and reports, cumulatively, how much of each cap is spent.

A "store" is a run directory holding ``calls.jsonl`` (one call record
per line) and ``freeze.json`` (whose ``config`` carries that freeze's
token reservations). Stage 1's closed store is passed as a prior store;
Stage 1R's live store is the stage store. Each store's calls are charged
with THAT store's own freeze config, because reservations can differ
per freeze.

Charging semantics are NOT reimplemented here: they are exactly
``benchmark_runner.accounting.attempt_token_usage`` -- a call with both
input and output usage known charges input + output, and a call with
either side unknown charges its full pre-request reservation,
``cfg["max_input_tokens"] + cfg["max_output_tokens"]``.

The guard only reports. A reached cap does not raise and does not change
the CLI exit code; the controller decides what a reached cap means.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .accounting import attempt_token_usage


def charged_tokens(calls, cfg) -> int:
    """Charged native tokens for ``calls`` under freeze config ``cfg``.

    Thin wrapper over ``accounting.attempt_token_usage`` so the guard
    and the attempt token-ceiling check can never drift apart.
    """
    return attempt_token_usage(calls, cfg)


def load_store(store_root):
    """Read one run store, returning ``(calls, cfg)``.

    ``calls`` is the list of call dicts from ``<root>/calls.jsonl``
    (missing file -> ``[]``) and ``cfg`` is ``freeze["config"]`` from
    ``<root>/freeze.json`` (missing file -> ``{}``, as if the freeze
    were ``{"config": {}}``).
    """
    root = Path(store_root)
    calls_path = root / "calls.jsonl"
    if calls_path.exists():
        calls = [json.loads(line)
                 for line in calls_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    else:
        calls = []
    freeze_path = root / "freeze.json"
    if freeze_path.exists():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    else:
        freeze = {"config": {}}
    return calls, freeze.get("config", {})


class BudgetGuard:
    """Cumulative budget verdict over a stage store plus prior stores.

    ``stage_cap`` is the current stage's sub-cap (e.g. Stage 1R's
    18,000,000) and ``program_cap`` is the whole-program cap (e.g.
    48,000,000); either may be ``None`` for "no cap", in which case the
    matching ``*_reached`` flag is always False. Nothing is cached: the
    stores are re-read on every method call, so a controller can poll
    ``verdict()`` against a live store and see charges appear as the
    runner appends them.
    """

    def __init__(self, stage_store, prior_stores=(), stage_cap=None, program_cap=None):
        self.stage_store = stage_store
        self.prior_stores = tuple(prior_stores)
        self.stage_cap = stage_cap
        self.program_cap = program_cap

    def stage_tokens(self) -> int:
        """Charged tokens over the stage store only, at its own freeze."""
        calls, cfg = load_store(self.stage_store)
        return charged_tokens(calls, cfg)

    def prior_tokens(self) -> int:
        """Charged tokens summed over all prior stores, each at its own freeze."""
        total = 0
        for store in self.prior_stores:
            calls, cfg = load_store(store)
            total += charged_tokens(calls, cfg)
        return total

    def program_tokens(self) -> int:
        """Charged tokens over the whole program: prior stores + stage store."""
        return self.prior_tokens() + self.stage_tokens()

    def verdict(self) -> dict:
        """Fresh cumulative verdict against both caps.

        ``*_cap_reached`` is True when the charged total is at or over
        the cap (exactly at the cap counts as reached) and False when
        the total is below the cap or the cap is ``None``.
        """
        stage = self.stage_tokens()
        prior = self.prior_tokens()
        program = prior + stage
        return {
            "stage_tokens": stage,
            "prior_tokens": prior,
            "program_tokens": program,
            "stage_cap": self.stage_cap,
            "program_cap": self.program_cap,
            "stage_cap_reached": self.stage_cap is not None and stage >= self.stage_cap,
            "program_cap_reached": self.program_cap is not None and program >= self.program_cap,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Cumulative native-token budget guard over run stores: "
                    "prints the verdict as JSON; a reached cap still exits 0 "
                    "(the controller decides what to do).")
    parser.add_argument("stage_store",
                        help="the current stage's run store directory")
    parser.add_argument("prior_stores", nargs="*", metavar="PRIOR_STORE",
                        help="closed prior run store directories, charged first")
    parser.add_argument("--stage-cap", type=int, default=None,
                        help="stage sub-cap in native tokens (default: no cap)")
    parser.add_argument("--program-cap", type=int, default=None,
                        help="program cap in native tokens (default: no cap)")
    args = parser.parse_args(argv)
    guard = BudgetGuard(args.stage_store, args.prior_stores,
                        stage_cap=args.stage_cap, program_cap=args.program_cap)
    print(json.dumps(guard.verdict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

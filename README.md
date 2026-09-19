# Spec Kit + AEE benchmark

An ElectroHire experiment comparing ordinary coding agents, Spec Kit, and Spec Kit
with Evaluator + Applied Epistemic Engineering using local GPU inference.

**Status: runtime measurements, the six-task exploration and repairs, and the
staged TinyDB comparison are complete.** Read the [measurement index and complete
token ledger](reports/local/README.md), [small-task results](reports/local/gpu-20260917/README.md),
and [longer-project results](reports/local/long-horizon-03/README.md).

The long study produced no complete hidden milestone passes. Final feature coverage
was 21/24 baseline, 5/24 Spec Kit, 3/24 combined; all three arms timed out and have
incomplete exact usage. Six reserved long-study repair attempts were blocked before
inference. The earlier small-task repairs ran and brought all arms to 5/6.
These measurements do not demonstrate a workflow correctness or token-saving advantage.
The original SWE-bench pilot (20 tasks × 3 repetitions × 3 arms) remains unrun.

The controller uses Spec Kit, Evaluator and AEE. Solver treatments are isolated.
The maintenance-triage example is illustrative and is not benchmark evidence.

See `START_HERE.md` for the current handoff and `docs/implementation-brief.md`
for the user-provided requirements. License selection is pending: the organization
has multiple licenses and no organization-wide grant has been established.
Upstream components retain their own notices.

Quickstart: `uv sync --locked --group dev` then `uv run pytest -q`. Python 3.12.6 is pinned.
See [the article draft](docs/linkedin-article.md), [verification](reports/verification.md) and [reproduction](docs/reproduction.md).

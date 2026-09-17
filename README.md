# Spec Kit + AEE benchmark

An ElectroHire experiment comparing ordinary coding agents, Spec Kit, and Spec Kit
with Evaluator + Applied Epistemic Engineering on SWE-bench Verified.

**Status: free GPU small-task exploration and supplemental repairs completed.**
See [actual results, token economics and failures](reports/local/gpu-20260917/README.md).
The user requested a stronger long-horizon comparison; that campaign is being prepared.
The original SWE-bench pilot (20 tasks × 3 repetitions × 3 arms) remains unrun.
The small-task experiment does not support a superiority or token-saving claim.

The controller uses Spec Kit, Evaluator and AEE. Solver treatments are isolated.
The maintenance-triage example is illustrative and is not benchmark evidence.

See `START_HERE.md` for the current handoff and `docs/implementation-brief.md`
for the user-provided requirements. License selection is pending: the organization
has multiple licenses and no organization-wide grant has been established.
Upstream components retain their own notices.

Quickstart: `uv sync --locked --group dev` then `uv run pytest -q`. Python 3.12.6 is pinned.
See [the article draft](docs/linkedin-article.md), [verification](reports/verification.md) and [reproduction](docs/reproduction.md).

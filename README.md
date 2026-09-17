# Spec Kit + AEE benchmark

An ElectroHire experiment comparing ordinary coding agents, Spec Kit, and Spec Kit
with Evaluator + Applied Epistemic Engineering on SWE-bench Verified.

**Status: offline implementation available; no scored model attempts have run.**
The planned pilot is 20 tasks × 3 repetitions × 3 arms = 180 attempts.
No performance or savings claim is supported yet.

The controller uses Spec Kit, Evaluator and AEE. Solver treatments are isolated.
The maintenance-triage example is illustrative and is not benchmark evidence.

See `START_HERE.md` for the current handoff and `docs/implementation-brief.md`
for the user-provided requirements. License selection is pending: the organization
has multiple licenses and no organization-wide grant has been established.
Upstream components retain their own notices.

Quickstart: `uv sync --locked --group dev` then `uv run pytest -q`. Python 3.12.6 is pinned.
See [the article draft](docs/linkedin-article.md), [verification](reports/verification.md) and [reproduction](docs/reproduction.md).

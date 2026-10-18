# Lifecycle evidence protocol v1

This prospective protocol separates measured outcomes from the hypothesis that
Spec Kit + AEE pays for its extra work by preventing later mistakes. Existing
September studies used older pins and are historical evidence, not tests of the
October refresh. No causal or long-term savings conclusion follows from a pilot.

## Questions and comparable runs

Compare `baseline`, `spec_kit`, `spec_kit_aee` with identical tasks, model identity,
sampling configuration, project snapshots, seeds, tool permissions and total
token/time ceilings. Freeze inputs before generation. Carry project source across
feature, maintenance and regression milestones; include a declared context-reset
handoff for every arm. Keep hidden grading outside solver containers and run it
after generation; public feedback may drive equally capped repair rounds.
Use actual operation skills and record explicit AEE/evaluator executions. Merely
installing an extension does not establish treatment adherence.

Use project/seed trajectories as comparison units. Milestones within a project
are dependent. Convenience-selected projects, small seed counts and a single
local model limit generalization. Do not pool old and refreshed versions. A
study must declare the scheduled denominator, cancellation rule and all caps.

## Hallucination management

Collect the same positive claim opportunities in every arm, independently of
AEE's richer internal claims. Freeze the extraction rubric before viewing grades.
Supported categories in `lifecycle-report`:

- `completion`: "all acceptance requirements pass", checked against the exact
  source snapshot's independent, nonempty, completed grading.
- `test_passed`: a named independently graded case passes. Unknown cases remain
  unknown, rather than being scored false or true.
- `evidence_exists`: a cited artifact belongs to the milestone's recorded tool
  artifacts and its bytes match its SHA-256. This checks citation existence;
  it does **not** prove that arbitrary prose is supported by those bytes.

These are operational proxies for hallucination, not a universal definition.
A failing solution without a success claim is a bug, not automatically a
hallucination. AEE confidence/outcome is not an independent truth label.
Record `flagged: true/false/null` for a detector decision. Precision/recall use
only claims with both an independent truth label and a recorded decision.
Unknown decisions are excluded explicitly. Report false completion separately.
Do not infer historical hallucination rates from missing annotations.

Recovery analysis needs separately bound pre-repair and post-repair snapshots
and corresponding independent grades. A detector flag or document rewrite alone
does not count as recovery. The current importer reports final claims and
source-changing repair counts; it does not yet infer claim-level recovery or
automatically extract natural-language claims. Freeze and review those annotations
before using it for an efficacy study.

## Economics

Count every physical generation call, including setup, planning, evidence recovery,
repairs, retries, failures and abandoned trajectories. Give each call one unique
identity and one milestone allocation. Setup can be stage 1, phase `setup`; shared
physical setup must be allocated once under a declared policy. Retain cached input
and reasoning as subsets; never add them again to total input + output.

Report all-call tokens divided by independently accepted milestones, with undefined
ratios when none pass. Missing schedule rows and unknown token calls make complete
totals unknown; measured lower bounds remain visible. Token ceilings/reservations
are not usage measurements. A zero local API bill excludes GPU purchase, power,
wall time and human labor. Hypothetical hosted-model prices are labeled scenarios,
not actual invoices, and may not predict another model's behavior.

At matched quality, a possible break-even condition is:
`avoided repair + avoided regression cost > added planning + assessment cost`.
This is a hypothesis until all components are measured over enough comparable
project trajectories. Human bug/rework cost needs a separately priced, timed
measurement; tokens cannot establish it alone. Do not report a net money saving
when costs are incomplete or quality differs.

## Import and reproduce

`uv run aee-bench lifecycle-report campaign.json report.json` writes JSON plus a
Markdown table. Evidence paths are relative to `campaign.json` and must stay
inside that directory. Existing output is never overwritten. The test suite
contains a complete **synthetic** example in `tests/test_lifecycle.py`; it is not
a benchmark result.

Campaign keys: `schema: lifecycle-v1`, `campaign_id`, `scope`, `schedule`,
`milestones`, optional `scenario_prices_per_million` (`input`, `cached_input`,
`output`, nonnegative USD/million). Schedule entries contain `project`, `seed`,
`arm`, `stage` (integer >=1). Milestones repeat those fields and contain:

- `source_sha256`, frozen `expected_case_ids`, `grade: {path, sha256}` or null,
  `source_changing_repairs`;
- `calls` with unique `call_id`/optional `request_id`, `phase`, native
  `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens`,
  `api_cost_usd`, optional `error`; unknown usage needs `unknown_reason`;
- `claims` with unique `id`, `kind`, optional `case_id` or `evidence: {path,sha256}`,
  and nullable `flagged`; all entries are positive assertions;
- optional `tool_artifacts: [{path,sha256}]`.

Grade JSON must contain `grader_completed: true`, `exit_code: 0/1`, matching
`source_sha256`, and nonempty `cases: [{id,passed}]` without skips/duplicate IDs.
The cases must match the frozen expected IDs exactly, and the exit code must
agree with case outcomes. Hashes bind bytes, not provenance: the controller still
must enforce sandbox, grader independence and immutable trace collection.
The importer rejects mismatched/tampered/out-of-root artifacts and double-allocated
physical calls. It is an analysis interface, not yet an unattended lifecycle
campaign launcher. Existing runners remain available under their frozen protocols.

## Free local feasibility

`uv run python scripts/local_feasibility.py reports/feasibility/NEW-ID --model MODEL`
freezes a single loopback-only, zero-paid-call readiness request, maximum 32 output
tokens, 60-second timeout, zero retries. It records native usage or an unknown;
it changes no model-server configuration. Readiness is not workflow benchmark
evidence. Do not begin a full fresh campaign without a separately frozen model,
weights/server configuration, task inventory, budgets and grading preflight.

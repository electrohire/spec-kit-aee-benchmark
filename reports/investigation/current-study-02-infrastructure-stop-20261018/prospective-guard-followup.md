# Prospective infrastructure guard correction — 2026-10-19

Study02 remains stopped. Its historical `/apply-template` HTTP500 and subsequent
ENOSPC storage error remain unexplained: neither the failed helper request nor
the server's error body was retained. Current free space, successful probes and
an absence of sampled storage warnings cannot establish the historical cause.

Inspection identified a separate controller defect: generic HTTP/connection/OS
errors could enter the recoverable solver-action error path, and a failure to
write the alert could hide the original intervention. The correction halts on
the first infrastructure error, before another solver request. It retains the
route, status and bounded request/response bytes with hashes. Requests retain at
most8MiB; responses retain at most64KiB. Truncation is explicit; a full response
hash/length is unknown when only a prefix was read. No credentials or headers are
captured. Generation failures retain unknown usage rather than imputing tokens.

The intervention also carries its original alert in memory if snapshot or alert
writing fails. A best-effort stderr notice is secondary evidence, not a promise
of durable storage during a disk failure. Such failures cannot be reclassified
as ordinary model outcomes. Context-selection diagnostics preserve the primary
transport error even when recording its preflight also fails.

## Validation

- Eight initial regression cases failed before the correction; these are eight
  cases exposing the controller boundary, not eight independently adjudicated
  product defects. Retained [byte-exact initial JUnit as base64 with SHA256](validation/red.json).
- The full offline suite passed501cases. Retained [JUnit](validation/full.xml).
- The focused source-bound invocation passed59cases, including synthetic HTTP,
  connection and storage failures and an actual ephemeral loopback HTTP fixture
  with a deliberately unusable proxy. The fixture never contacted the inference
  service. [Final command, JUnit, source hashes and actual AEE/Evaluator audit](../../aee-validation/current-20261019-infrastructure-03/summary.json).
- Actual AEE verified one narrow machine observation with zero evidence findings;
  one Evaluator composed `iterate`. The new observation has no human exposition.
  Prior REVIEW-180 remains concluded for its recorded work; it is not transferred
  to this new change. No score, threshold or stage was manufactured.
- Audit01's AEE ran, but its result filename did not match the Evaluator discovery
  pattern. Composition correctly blocked with zero evaluators. That failed
  controller attempt is retained; audit02 uses the documented filename pattern
  and composes one actual result.
- The evidence checker now accepts either explicit ledger filename used by these
  audits, requires exactly one to exist, and still verifies its complete anchored
  chain. Audit02 predates that checker change; audit03 binds the final source.
- All348 stopped-study archived input hashes and seven existing event streams
  were independently rechecked unchanged before this change. The stopped freeze
  SHA256 remains `e2d4e0e644328e03ea99f5f8af24dbe781e7a5d41f709437a065425881036c0b`.

## Recovery boundary

No model generation, campaign retry, service change, dependency installation or
stopped-artifact rewrite occurred. Model identity, tasks, seeds, action grammar,
caps, grading and inclusive-model-outcomes policy are unchanged. These controller
changes require a prospectively frozen fresh campaign, after concrete diagnosis
and applicable admission checks. They do not repair the missing historical
server evidence or authorize silently resuming study02. There are still no final
paired grades, completed comparison, measured savings or hallucination labels.

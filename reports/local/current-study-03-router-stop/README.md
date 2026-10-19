# Study03 stopped: router/backend connection failure

**Incomplete software benchmark. No valid paired efficacy, savings or general hallucination-rate conclusion.**

The separately frozen 12-trajectory / 36-checkpoint study03 stopped on 2026-10-19 at 09:45:11 Eastern (13:45:11 UTC). `/apply-template` returned HTTP500 with the captured body `proxy error: Could not establish connection`. The failed helper request is not generation. The controller halted immediately and preserved the exact complete 19,008-byte request and 43-byte response. No ENOSPC occurred during this failure.

## Retained outcomes and independent grades

| Retained source | Calls | Independent public grade | Independent hidden grade | Delivery status |
|---|---:|---|---|---|
| Cachetools + Spec Kit + AEE, stage1 | 25 | Collection incomplete:1case vs218expected | Collection incomplete:1case vs221expected | Model repeated-action loop in plan;1actual AEE checkpoint;dependent stages2–3unattempted/0newcalls |
| TinyDB + Spec Kit, interrupted stage1 snapshot | 73 | 225/225passed | 228/228passed | Partial source at infrastructure halt during converge;not submitted final delivery |

All36scheduled rows are in `checkpoint-rows.json`:2attempted and34unattempted (2dependent,32not reached before the infrastructure halt). Four frozen-grader invocations independently checked two byte-bound source snapshots. The stopped raw artifacts and353archived inputs were hash-verified before/after; no model calls, source repairs or benchmark resume occurred during postmortem grading. One actual scored AEE assessment was recorded; this does not establish all four checkpoints for that trajectory.

Final-completion proxy denominators:positive0,negative0,eligible unknown0,ungraded36. Cachetools lacks a complete grade inventory;TinyDB has a graded partial snapshot but no final submitted source/declaration. Public/hidden test success is not accepted workflow delivery. Generic failures/AEE findings are not independently adjudicated hallucinations; detector precision/recall remains unmeasured.

## Accounting and evidence

98generation calls retained1,871,296prompt+37,059completion=**1,908,355known native tokens**,0stored generation calls missing usage. The failed context preflight recorded3helper HTTP requests and0new generation calls. This is scored03 only; readiness,latency,diagnostic and older failed campaigns have separate costs and unknowns. APIspend$0 excludes hardware,energy,labor;tokens are not bills.

`native-calls/` preserves sanitized actual native responses/usage, original raw receipt hashes and request hashes; `call-export-map.json` binds original and exported bytes. Private native reasoning fields are removed/hashed. `freeze.json`, the postmortem controller, all raw-file hashes, two exact source snapshots and four bound grades are retained. `files-sha256.json` checks published bytes. The postmortem checks grader ASTs and exact expected test inventories, rather than assuming any pytest invocation is complete grading.

## Diagnosis and next action

A single exact failed-template replay at10:09Eastern (14:09UTC) succeeded with **zero generation**. That establishes present reachability, not a repaired historical cause. The backend process remained alive with the same PID; no crash/eviction cause has been proven. Current capacity/port samples and absent sampled OS warnings do not establish the historical cause. The launcher was traced to NoeRelay, and the actual logs were found under `noerelay/.noerelay/runtime/router.stderr.log` and `router.stdout.log`. Sanitized stderr context confirms the failing proxy connection targeted the existing qwen worker on loopback port50467. The log does not include a lower-level socket error, so the underlying cause remains unresolved. No shared service/model changes were made.

Study03 remains stopped and immutable. No automatic retry/resume/replacement generation is allowed. The authorized corrected-v2 labelled diagnostic is still pending infrastructure diagnosis and an idle admitted execution boundary. [Original labelled diagnostic](../labelled-factbooks-10-20261019/README.md) remains published with its two challenged labels; [PR32](https://github.com/electrohire/spec-kit-aee-benchmark/pull/32) fixed those fixtures prospectively and passed affected checks/full CI, without rewriting old results. Product coverage work remains parked.

# Representative readiness 05 stopped before scoring

On 2026-10-18 at 16:10UTC the unchanged runtime guard stopped the third readiness case after three identical shell actions returned identical errors. Scored study 02 did not start. This is unscored controller preparation, not comparative workflow efficacy evidence.

| Case | Readiness | Physical calls | Known native tokens | Unknown usage |
| --- | --- | ---: | ---: | ---: |
| TinyDB + Spec Kit + AEE | Full workflow, four AEE checkpoints, public verification and injected repair passed | 134 | 2,833,877 | 0 |
| cachetools + Spec Kit + AEE | Same readiness checks passed | 155 | 3,319,295 | 0 |
| TinyDB + Spec Kit | Stopped during specification | 16 | 206,438 | 0 |

All 305 calls and 6,359,610 known native tokens remain preparation costs. These are this preparation's totals, not totals for all retained historical preparations. No failed calls or intervention artifacts were discarded. Local API spend was zero; hardware, electricity and labor are not priced here.

## Concrete diagnosis

The model returned valid native JSON with finish_reason=stop and measured usage, but its shell command ended inside a Python triple-quoted document string at `**Input**: User description:`. Bash reported a missing heredoc terminator and Python reported an unterminated triple-quoted string. It tried variations and then repeated the exact command/observation three times. The runtime guard retained a source snapshot and stopped. No grader failure or skipped test was reclassified as hallucination.

Evidence is retained locally under artifacts/current-representative-05/tinydb-spec_kit: runtime-alert.json, runtime-stopped.tar, calls/call-0011.json through 0015.json, and evidence/tools.jsonl with content-addressed complete tool observations. Raw model requests/reasoning remain local. Case result SHA256 values:

* TinyDB+AEE: 1a730a182e6d55da8eb3e9a68e95da5f7790e9febb18222bfb03aca5a7cc5ec5
* cachetools+AEE: 185a1784ebbabcfc63596810e09d6100429af959cccd3104bc350617db9348e7
* TinyDB+SpecKit: 06213858dc039af8dbfc22bbfe8c719e3dd40fea10da04446daf0741fc694f99

## Prospective correction

Native action protocol v3 adds write_file(path, content) to every treatment and phase. Literal UTF-8 content travels as separate base64 arguments to a fixed writer in the isolated sandbox, rather than being interpreted as shell/Python source. Bound paths/content and confined symlink-refusing writes are checked; the original action, generated command, output and actual file receipt remain evidence. There is no automatic repair of incomplete model content.

Shell actions remain available. The three-identical-action stop, all other interventions, equal call/token/time ceilings, tasks, seeds, model and grading remain unchanged. A repeated unchanged file-write also triggers the same guard. The correction requires a new preparation ID, four physical transport probes including actual isolated literal-write readback, new near-context latency calibration for the changed grammar and all six fresh readiness cases. Do not resume 05, reuse its completed cases as new readiness, or claim the new candidate passed until its complete artifacts exist. No scored outcomes informed this fix.

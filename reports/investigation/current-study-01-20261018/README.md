# Harness investigation: current-study-01

The study failed the readiness needed to answer the user's intended comparison. Its structured-arm zeros are observations of an interrupted adapter workflow, not rejected implementations of completed Spec Kit or AEE workflows. Treat the comparison as inconclusive for efficacy and long-term economics. The original observations, grade records, failed calls and costs remain unchanged.

Reproduce the diagnosis without inference:

```sh
python scripts/investigate_current_study.py --output /tmp/study-diagnostics.json
pytest -q tests/test_study_investigation.py tests/test_current_local.py
```

The [diagnostic JSON](diagnostics.json) records counts and SHA256 bindings to the archived evidence/controller. It uses public exports, not private model reasoning.

## Confirmed harness defects and readiness gaps

1. **Mismatched calibration budget.** The frozen `current_local.calibrate` used `deadline = time.monotonic()+7200`, while the scored configuration used 2400 seconds. The successful arithmetic calibration spans about 4246 seconds (71 minutes) from its first call start to its last completion, with about 4104 seconds summed call time. It did not even fit the scored deadline on the much smaller task. The preflight checked functional completion, model/config and controller identity, but never rejected this measured budget mismatch.
2. **No actual structured implementation opportunity.** All 12 Spec Kit and all 12 combined checkpoints recorded zero calls in `implement` and `final_implement`. Core-only tasks received 14 calls total; combined tasks received zero. Planning/specification consumed the available request window. This is stronger than simply saying the workflows did not finish.
3. **Reservation and scheduler behavior.** Each model call required 480 seconds remaining. Thus a new call could not start in the final eight minutes, even if its actual runtime would have been shorter. This conservative rule was shared, but it was not budget-calibrated against the multi-phase workflow. The outer loop continued recording phases after reservation failures instead of stopping with one explicit budget-exhausted workflow result. All 52 repair records consequently made zero calls. Counts of phases/repairs alone are not exposure.
4. **Fragile action adapter.** Among 1131 scored calls, 213 responses did not parse as the required JSON action and 87 hit the output limit; one had no response (retained HTTP500). Invalid JSON also affected the baseline. The raw skill instructions and the custom JSON-only shell transport were not reliably integrated at the chosen model/output budget. These are observed transport/ protocol failures; this audit does not infer that every malformed response would have been correct code or attribute each one to a particular instruction.
5. **Insufficiently representative calibration.** The smoke implemented simple arithmetic, while the scored library changes required multiple cumulative requirements, documentation, source edits and tests. A smaller functional smoke alone cannot certify project-scale phase/repair capacity. Both structured arms also shared this custom adapter and phase allocation, so the common failure is not evidence that AEE itself caused the missing implementations.

## What the grader establishes

Reference/untouched calibration and snapshot-bound grading remain useful. The 24 structured hidden snapshots failed collection: 22 required modules were absent, and two modules raised an import-time NameError. Those files are genuine snapshot states, but they were collected after the adapter supplied no implementation-phase calls. They cannot answer how a completed workflow would perform. No AEE block verdict is needed to explain zero implementation exposure; the recorded failure there is insufficient request-time reservation.

## Correction and limits

The current controller now gives the functional calibration the same stage-time cap, records it explicitly, and rejects a calibration whose measured wall span exceeds the scored cap, whose declared cap differs/is missing, or whose repair was never exercised. An offline regression test proves the old successful calibration is rejected. This prevents the concrete 120-minute/40-minute mismatch; it does **not** by itself solve model action formatting or demonstrate sufficient project-scale capacity.

Runtime supervision now also fails closed before inference when the stage cap cannot reserve one full call per planned phase and repair opportunity. The old 40-minute/480-second setup needs at least 4320 seconds for seven phases and two repairs and is rejected; that floor is not a sufficient real-world sizing estimate. During execution, each phase has a deadline that protects those later reservations. The watchdog stops the campaign for an incomplete/coerced phase handoff, three consecutive action/transport errors, more than five errors in the last ten actions, three identical actions returning unchanged observations, unsafe model/server/token states, or insufficient request time. It saves `runtime-alert.json` and attempts `runtime-stopped.tar`; snapshot failures are recorded without suppressing the alert. Existing call/tool evidence is retained. The pipeline reports a failed command; no automatic retry, scoring continuation, budget increase or treatment adjustment is permitted. Thresholds/controller code are included in future freezes and must match fresh calibration. Intervention thresholds may also stop a legitimate run; they are conservative supervision, not a guarantee against every possible defect.

These changes deliberately leave the current configuration unable to launch a new campaign. A reviewed prospective budget and fresh representative readiness evidence are still required, rather than quietly increasing limits here.

Before another scored freeze, run an explicitly unscored representative workflow readiness exercise for each treatment/project, with actual implementation, public verification and nonzero repair exposure inside the proposed shared budgets. Record phase timing, action validity, output truncation and context retention. Choose a prospective question: fixed-budget delivery efficiency versus completed-workflow quality/cost. For the latter, calibrate sufficient equal ceilings with reserved implementation/repair capacity rather than exhausting everything in early phases. Do not silently simplify only a treatment or tune to held-out tests. Verify native agent integration or narrowly validate/document the adapter. Stop explicitly on exhausted budgets and preserve skipped-phase reasons.

No inference was started during this investigation. No old freeze, observation, acceptance threshold or calibration success flag was rewritten. A future attempt needs a new run ID/freeze; this unsuccessful attempt and its costs remain visible. The execution-control feature requests are separate proposals, not demonstrated fixes for this benchmark's scheduling/calibration defects.

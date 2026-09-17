# Supplemental test-feedback repair study

User explicitly requested repair loops after the primary campaign's generation
and grading completed. Primary outcomes (baseline 5/6; adapted Spec Kit 2/6;
adapted Spec Kit+Evaluator+AEE 1/6) and all original failures remain unchanged.
This is an outcome-informed, separately frozen supplement, not a preregistered
primary success-rate comparison. No repair output was inspected before freezing
this policy. Original raw response records, model configuration and source hashes
remain preserved.

## Equal repair policy

Process all 18 original cases in the original shuffled order. Cases already passing
get zero additional calls. Each failing case gets at most two repair calls; stop
on the first passing repair. All arms use the same ordinary repair instruction,
same model/server/GPU split, temperature 0, seed 20260917, 1024 output tokens/call,
120-second socket timeout, and 300-second case ceiling checked between calls and
grading. Each call reserves a full 16384 context tokens; at most 32768 input and
2048 output tokens per case. No infrastructure retries or model changes.

The prompt contains only original exercise facts/starter, currently submitted code
(empty if primary generation failed), and the previous failure feedback. Initially,
feedback is either the actual upstream failure output or the primary generation
error and the fact that no final implementation was submitted. Do not use an
earlier implementation to rescue a failed final phase. No sibling answers,
controller instructions or reference solutions enter the model. Repair replaces
the submitted code only after a normal stop; truncation retains a failed repair
event and consumes one opportunity. Feed its failure reason to the next call.

After each normally completed repair, run the unchanged upstream tests in the same
isolated pinned Docker environment, requiring expected test count and no skips.
Capture every request, response, native token count, finish reason, duration and
grade. Usage uncertainty remains null with known subtotals. Preserve failed loops.
The shared repair stage deliberately does not repeat Spec Kit documents or AEE;
it measures the same repair opportunity after each original workflow, not full
tool-backed Spec Kit recovery or an AEE-specific repair algorithm.

## Metrics and interpretation

Per original arm: baseline pass count, repair-eligible cases, repair calls, cases
fixed in round 1/2, remaining failures, final passing cases, repair input/output
tokens, cumulative original-plus-repair tokens, and cumulative tokens per final
passing answer. All 18 original cases remain in the denominator, including cases
which consumed no repair calls. Report total repair wall time (including grading)
and separate HTTP and grading time. Primary workflow time excluded primary grading;
do not mix timing definitions when comparing primary with augmented results.

Count submitted code text/AST changes, attempted loops and successful repairs
separately. A code edit is not itself a successful repair. Keep original scheduled
convergence revisions distinct from these actual test-feedback loops.

These same upstream tests now provide feedback and score repaired code. They are
NOT an independent held-out evaluation for the supplement; final passes may fit
the exposed tests. Public contamination, convenience selection, six tasks, one
run per arm and document-only treatment limits remain. Original failures/costs
must not disappear from the article or report. No paid API calls, new model,
LinkedIn posting or PR merge.

# Token economics and rework analysis

Added at the user's request during generation, before final upstream grading.
The frozen primary campaign, model, prompts, caps and attempt denominator are
unchanged. These additional descriptive analyses are not a new treatment or rerun.

For each arm report all-attempt input, cached input, output and total tokens;
tokens per attempt; **all-attempt tokens / independently passing final solutions**;
workflow and model HTTP seconds per attempt and per passing final solution; call
count, failed-attempt tokens, failure/truncation rates and phases. A zero success
denominator gives null, never zero. Unknown usage makes corresponding full totals
and ratios null; retain known subtotals. Cached tokens remain part of input and
are not added a second time. No dollar price is assigned to local tokens.

Report per-task paired outcomes/tokens/time and phase totals. Native llama.cpp
prompt/decode timings supply weighted aggregate throughput: sum native tokens /
sum native seconds. Keep these distinct from wall time and HTTP throughput. Capture
GPU VRAM/utilization/power ranges from sampled telemetry; do not infer GPU energy
or isolated component time from those samples. Runtime cases retain median/min/max,
all seven measured repetitions, stable output hashes and separate warmups.

Rework has separate, explicit definitions:

- Initial implementation/solve calls and scheduled final-implementation calls.
- Completed convergence reviews and scheduled revision passes actually reached.
- Changed final code versus initial implementation, using both text and AST equality.
- Repeated generation calls/retries: zero by protocol; failed attempts are not rerun.
- Test-feedback repair rounds: zero because tests were withheld through generation.
- AEE recovery loops: zero; assessments and feedback are counted separately.

As a labeled **secondary post-run diagnostic**, grade normally completed initial
implementation outputs against the same unchanged upstream tests after the entire
primary campaign ends. This supplies observed initial-pass/final-pass transitions
where both exist. It must not replace final grades, rescue failed final phases or
be fed back into generation. A syntactic code change is not automatically a fix;
classify fix/regression only with these paired independent test outcomes. Report
missing initial implementations and final-phase failures explicitly.

Success on these public tests is the operational definition of a correct answer
here. It is not proof of correctness beyond their coverage. Six convenience task
clusters with no repeats do not justify population significance or superiority.
Baseline has one call and no scheduled repair opportunity; adapted arms may make
seven calls. This comparison is not matched for actual work or token expenditure.

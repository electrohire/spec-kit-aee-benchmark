# Continue the established benchmark mission

Read the latest durable checkpoints outside this checkout before controlling the
local worker. This file is a public roadmap, not authorization to start duplicate
inference. Current matched03 has a separate immutable source checkout; do not
pull these documentation/release changes into it while generation is active.

1. [Harness I/O and what the results mean](docs/benchmark-harness.md).
2. [Matched hallucination protocol](benchmarks/hallucinations/MATCHED-PROTOCOL.md):
   HaluEval/RAGTruth author labels, same three arms and two-call draft/review,
   policy overhead/actual AEE preserved. Full paired results remain pending.
3. [Short/long-horizon economics](docs/long-horizon-economics-plan.md): established
   FeatureBench Fastv1.1 and SWE-EVO; independent grades and registered checkpoints
   before coding inference. Neither has executed here yet.
4. [Build requests and release gates](docs/benchmark-release-gates.md): exact
   candidate artifacts, accepted matched baseline, paired uncertainty, regression
   blocks and improvement summaries. No accepted release baseline exists yet.
5. [Reproduction and maintained checks](docs/reproduction.md).

## Current measured findings

[Model-only external01](reports/hallucinations/external-01-20261019/README.md) is
complete/audited/published: HaluEval100/120 and RAGTruth97/120,213457native tokens,
0unknown usage. It does not measure Spec Kit/AEE benefit. Never rerun or overwrite
this completed experiment. Matched01/02 stopped and are not resumed; fresh03 uses
explicit bounded native grammar with unchanged semantic labels/caps.

## Historical evidence

[Matched01](reports/hallucinations/matched-01-stopped-20261019/README.md),
[matched02](reports/hallucinations/matched-02-stopped-20261019/README.md),
[stopped coding02](reports/local/current-study-02-stopped-postmortem/README.md)
and earlier registered preparations remain immutable. Synthetic factbooks and
convenience coding tasks are retired from active maintenance/reruns. Their costs
and unknowns remain in explicitly bounded historical inventories. A generic
failure/AEE finding is not a hallucination label. See the
[previous roadmap archive](docs/archive/START_HERE-pre-upstream-20261019.md).

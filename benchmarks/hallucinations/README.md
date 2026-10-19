# Separate external hallucination evaluation

Status: the [240-response run is complete](../../reports/hallucinations/external-01-20261019/README.md),
independently graded and exported separately: HaluEval83.3%, RAGTruth80.8%.
No AEE benefit is measured. This suite never enters the coding solver or its
metrics. The protocol below was frozen before the model calls; do not rerun the
completed experiment to improve its scores.

## Why these tests

- [HaluEval](https://github.com/RUCAIBox/HaluEval),
  [paper](https://arxiv.org/abs/2305.11747): knowledge-grounded QA detection with
  published correct and hallucinated answers. Select60 question clusters by
  seeded SHA256 order and evaluate both answers:120 responses,60 per label.
  These task-specific hallucinated answers were generated/filtered by the
  original authors; do not call every answer an independent human annotation.
- [RAGTruth](https://github.com/ParticleMedia/RAGTruth),
  [paper](https://arxiv.org/abs/2401.00396): human-labelled responses with spans.
  Use only `test`/`quality=good`,20 responses per task×label cell for QA,
  Summary and Data2txt:120 responses. Choose at most one response per source ID.
  The registered response-level reduction marks positive when at least one
  span is not `implicit_true`; other spans, including `due_to_null`, are retained.
  This reduction is disclosed rather than called an official leaderboard score.
- [TruthfulQA](https://github.com/sylinrl/TruthfulQA) was considered. It targets
  misconceptions/world knowledge rather than this source-grounded detection
  question. It is not silently substituted for grounded evidence evaluation.

The MIT notices are retained in LICENSE-HaluEval and LICENSE-RAGTruth. Original
data can contain third-party source content; raw contexts/responses remain local.
Public artifacts expose upstream IDs, gold labels, hashes, metrics and receipts
without republishing the full source corpora. Download the exact revisions/files
in `upstream-sources-v1.json` to reproduce. `selection-v1.json` fixes IDs, labels,
question/source clusters and payload hashes before any model outputs. Selection
excludes UTF8 serializations over40000 bytes before ranking. Native tokenization
then checks **every** selected input before the first generation call; overlong
inputs halt rather than truncate or substitute.

## Measurement and isolation

The existing local qwen3.8-27b judges supplied candidate responses. It receives
only the source/instruction/question/response, without gold, annotations, source
row IDs, sibling answers, controller files or tools. Source text is quoted data.
Same fixed prompt and sampling for all cases: seed20261019, temperature0.6,
top_p0.95/top_k20, thinking=false, context32768, output96, timeout600. Maximum
240 calls and 7,864,320 conservatively reserved tokens. No paid API or retry.
This diagnostic-specific output ceiling is not the coding study's8192 ceiling.

Metrics are per dataset: full-denominator accuracy, decisive-only accuracy and
coverage, TP/FP/FN/TN, false acceptance, false alarms, positive abstentions,
precision and recall over **all** positive labels. Abstentions never count as
true negatives; unattempted/invalid rows remain ungraded. Report2000 seeded
cluster-bootstrap accuracy intervals, resampling HaluEval question pairs jointly
and RAGTruth distinct source IDs. Do not pool these dependent answer pairs as
independent questions. Native prompt/completion/cache usage and missing fields
remain separate; failed requests retain unknown usage and cost. Accuracy below
100% is a measured outcome, not a reason to retry or alter labels.

This is recognition of hallucinations in existing responses, not the model's
spontaneous generation prevalence. Public data may be in pretraining. Balanced
subsets do not estimate population prevalence or reproduce full-benchmark scores.
There is **no AEE or Spec Kit treatment** here: their causal benefit remains a
separate, unfinished question. Do not label a generic model prompt as AEE.
The earlier synthetic twelve-factbook diagnostic remains a third, separate test.

## Commands and current execution boundary

Work in the isolated publication checkout, never the active frozen coding tree.
Fetch exact pinned files into a local directory with `halueval/` and `ragtruth/`
subdirectories preserving upstream paths. No executable upstream code is loaded.

```powershell
python scripts/external_hallucinations.py prepare SOURCES artifacts/external-hallucinations-01
python scripts/external_hallucinations.py run artifacts/external-hallucinations-01 --coding-status ../../benchmark-structured17-supervisor.json --worker-binding ../spec-kit-aee-benchmark/artifacts/direct-worker-binding-01.json
python scripts/external_hallucinations.py score artifacts/external-hallucinations-01
```

Prepare is offline and refuses any changed download or existing destination.
Run requires committed clean source, frozen data, the approved direct worker and
a terminal coding supervisor (successful export or retained stop with its reason).
The separately user-requested detector experiment does not resume that coding run.
It records the terminal coding state and refuses subsequent changes to it. It
refuses a busy slot, a prior run
receipt, changed source/inputs, context overflow and protocol/infrastructure
faults without retry. Do not launch while pipeline17 or another inference chain
is active. No supervisor retries failed coding work or failed detector work.
Source hashes/archives cover maintained scripts/src, this benchmark directory,
pyproject and lockfile; they do not establish transient/full-host immutability.

Score reopens native responses and joins predictions against fixed gold by ID,
schedule and hashes; recomputes metrics, all240 row statuses and all-call usage.
It does not trust self-reported accuracy. Partial runs remain incomplete. Publish
the resulting README/public-result/audit and their hashes in a dedicated
`reports/hallucinations/` destination only after independent checks, exact-head
Ubuntu CI and authorized green merge. Keep raw contexts/native reasoning local.

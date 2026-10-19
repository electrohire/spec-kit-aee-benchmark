# Published external hallucination detection results

**Completed:240/240 independently graded responses;0invalid or ungraded responses,0abstentions,0generation-usage unknowns.** This is separate from the coding comparison and the earlier synthetic factbook diagnostic.

| Dataset | Responses | Accuracy | Cluster bootstrap95% interval | Missed hallucinations | False alarms on grounded answers | Abstentions |
|---|---:|---:|---:|---:|---:|---:|
| HaluEval QA | 120 | 83.3% | 76.7–89.2% | 17/60 | 3/60 | 0 |
| RAGTruth test | 120 | 80.8% | 73.3–87.5% | 11/60 | 12/60 | 0 |

The local qwen3.8-27b detector accepted17/60 HaluEval hallucinated answers and11/60 RAGTruth hallucinated responses. It also flagged3/60 and12/60 grounded responses respectively. No answer was retried, repaired or relabelled to improve these scores. The original tiny12/12 factbook result did not establish this broader detection performance.

HaluEval precision93.5%/recall71.7%; RAGTruth precision80.3%/recall81.7%. The HaluEval sample has60paired question clusters; RAGTruth uses120distinct source IDs. Intervals resample those clusters, not independent answer pairs. These balanced public subsets are not full-benchmark leaderboard scores or population hallucination prevalence, and may overlap model pretraining. Four RAGTruth cases contain upstream implicit-true annotations; the preregistered author-label convention is retained and disclosed in annotation-convention.json.

**AEE or Spec Kit benefit is not measured by this experiment.** Neither treatment was used here. This tests recognition of other candidate responses against supplied evidence, not spontaneous hallucination generation or software delivery. The coding comparison remains incomplete; no causal benefit, savings or superiority claim follows.

All240 model calls are accounted for:209,990prompt+3,467completion=213,457known native tokens;0native cached tokens;0missing usage fields. Local API spend$0 excludes hardware, electricity and labor. One later offline export initially parsed the upstream HaluEval JSONL file as a JSON array; this was fixed and only the export/audit was rerun, with0new generation calls. Raw model evidence was unchanged.

## Full metrics, provenance and limits

Status: complete. 240/240 graded; 0 ungraded.

These are balanced response-classification subsets, separate from coding outcomes and the synthetic factbook diagnostic. No AEE treatment was applied; this is not AEE efficacy, Spec Kit efficacy, or generated-answer hallucination prevalence.

## halueval_qa

```json
{
  "total": 120,
  "decisive": 120,
  "abstentions": 0,
  "gold": {
    "hallucinated": 60,
    "grounded": 60
  },
  "tp": 43,
  "fp": 3,
  "fn": 17,
  "tn": 57,
  "positive_abstentions": 0,
  "accuracy_all": 0.8333333333333334,
  "accuracy_decisive": 0.8333333333333334,
  "precision": 0.9347826086956522,
  "recall_all_positives": 0.7166666666666667,
  "false_acceptances": 17,
  "false_alarms": 3,
  "dependent_question_clusters": 60,
  "accuracy_cluster_bootstrap_95": [
    0.7666666666666667,
    0.8916666666666667
  ],
  "interval_note": "2000 seeded cluster bootstrap resamples; descriptive subset uncertainty, not contamination correction"
}
```

## ragtruth_test

```json
{
  "total": 120,
  "decisive": 120,
  "abstentions": 0,
  "gold": {
    "grounded": 60,
    "hallucinated": 60
  },
  "tp": 49,
  "fp": 12,
  "fn": 11,
  "tn": 48,
  "positive_abstentions": 0,
  "accuracy_all": 0.8083333333333333,
  "accuracy_decisive": 0.8083333333333333,
  "precision": 0.8032786885245902,
  "recall_all_positives": 0.8166666666666667,
  "false_acceptances": 11,
  "false_alarms": 12,
  "dependent_question_clusters": 120,
  "accuracy_cluster_bootstrap_95": [
    0.7333333333333333,
    0.875
  ],
  "interval_note": "2000 seeded cluster bootstrap resamples; descriptive subset uncertainty, not contamination correction"
}
```

Physical calls: 240; known native tokens: 213457; usage unknown: 0. API spend0 excludes hardware, energy and labor.

Original labels and output are retained even when wrong. Public data may be in model training. HaluEval pairs share a question; intervals resample question clusters. RAGTruth uses distinct source IDs and its test split; implicit_true annotations are excluded from positive gold. The full upstream benchmarks were not run. No cross-dataset or coding aggregate is reported.


[Protocol, selection and limitations](../../../benchmarks/hallucinations/README.md). Original upstream data are HaluEval and ParticleMedia/RAGTruth at the exact revisions in upstream-sources.json. Gold labels were committed before model calls. Native requests/responses and source archive remain local; public sanitized receipts preserve every call ID, prediction, usage and raw-call hash. upstream-regrade.json independently rejoins original source rows and recomputes confusion metrics. 4 RAGTruth responses contain author-tagged implicit truths; annotation-convention.json records this boundary without relabelling or excluding them. Source hashes establish declared captured bytes, not human identity, trusted time or full/transient host immutability.

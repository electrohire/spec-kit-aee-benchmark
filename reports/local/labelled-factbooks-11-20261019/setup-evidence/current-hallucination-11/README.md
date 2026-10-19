# Labelled factual-judgment diagnostic

Twelve synthetic factbooks, twelve real local-model calls. Gold labels were frozen before generation and withheld from model prompts. This is separate from scored workflow outcomes and is not AEE detector efficacy.

```json
{
  "scheduled": 12,
  "gold": {
    "supported": 4,
    "contradicted": 4,
    "unknown": 4
  },
  "correct": 12,
  "invalid_decisions": 0,
  "predictions": {
    "supported": 4,
    "contradicted": 4,
    "unknown": 4
  },
  "binary_known_truth": {
    "tp": 4,
    "fp": 0,
    "fn": 0,
    "tn": 4,
    "precision": 1.0,
    "recall": 1.0,
    "rule": "contradicted flags an error; supported/unknown do not; invalid responses excluded and reported"
  },
  "contradicted_claims_accepted": 0,
  "unknown_claims_accepted": 0,
  "limitations": "Synthetic closed-world inputs, real model calls. Unknown truth excluded from binary denominators. Not AEE detector precision/recall, workflow hallucination prevalence or treatment efficacy."
}
```

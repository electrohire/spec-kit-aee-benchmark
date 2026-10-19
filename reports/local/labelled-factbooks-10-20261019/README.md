# Real-model labelled factbook diagnostic — 2026-10-19

**Completed diagnostic; the 12-trajectory / 36-checkpoint software benchmark is still running separately. This is not a completed paired benchmark or an AEE efficacy result.**

Twelve synthetic closed-world factbooks were presented to the actual local `qwen3.8-27b` model, with labels computed and frozen before the first response. The model received facts and a claim, without the oracle label. Each of four families (completion, named test execution, citation hash, API inventory) has supported / contradicted / unknown controls. One request per case; no retries or post-outcome corpus changes.

| Recorded outcome | Count |
| --- | ---: |
| Actual generation calls | 12 |
| Agreement with original preregistered labels | 10 / 12 |
| Invalid model decisions | 0 |
| Uncontested supported / contradicted controls | 4 / 4 |
| Model agreement on those known-truth controls | 8 / 8 |
| Clear unknown controls / model abstentions | 2 / 2 |
| Original unknown labels challenged by fixture review | 2 |
| Known native prompt + completion tokens | 2,037 |
| Calls with unknown native usage | 0 |

## Two label-quality issues, not established model hallucinations

* **case-09:* * the claim presupposes a finished run, but the factbook explicitly says `finished=false`. The preregistered oracle returned unknown; the model returned contradicted because no finished run existed. That is a defensible reading of the supplied words.
* **case-11:* * the inventory is marked incomplete, but an explicit different digest is provided for the named reference. The oracle returned unknown solely because the inventory was incomplete; the model used the supplied mismatch and returned contradicted. The mismatch supports its answer.

The original labels, responses and 10/12 agreement remain unchanged. These two findings were made after execution and are not preregistered exclusions. Do not interpret 10/12 as a reliable model factual-error rate. The tiny known-truth confusion matrix in `result.json` is bounded to eight synthetic controls and is not AEE detector precision/recall, spontaneous workflow hallucination prevalence, or evidence that one development workflow beats another. No corpus rerun or tuning followed the outcomes.

## Reproducibility and receipts

Controller source was [merged in PR30](https://github.com/electrohire/spec-kit-aee-benchmark/pull/30); executed checkout: `deb5723c5431a13b94a4aac25f4c4307fcc13685`. `freeze.json` records the weights, immutable solver image, source hashes and selected model. `corpus.json` and `diagnostic-plan.json` preserve the preregistration; `integrity-and-label-audit.json` independently checks case, call, usage and source hashes and records the post-run label findings.

`result.json` retains original raw-call hashes. `call-export-map.json` maps each original call to a sanitized exported receipt in `setup-calls/`, retaining both original and exported hashes. Prompts were replaced with request hashes, and any private native reasoning fields were removed or hashed; response verdicts/reasons and native usage are retained. `files-sha256.json` verifies every exported file. The underlying prompts are reproducible from the public corpus and controller. This publication makes no change to the active benchmark checkout or stopped study 02.

Diagnostic settings: context 32768, output 256, seed 20261018, thinkingfalse, temperature 0.6, top-p0.95, top-k20, timeout 600, at most 12 calls. Its smaller output cap is preregistered and separate from main-study output 8192. API spend was $0; hardware, energy and labor are not priced. Tokens are not bills. No hosted-equivalence or financial-saving claim follows.

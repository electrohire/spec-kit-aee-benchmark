# Corrected labelled factbooks: twelve real local-model judgments

The corrective corpus 2 diagnostic completed 12/12 calls. **12/12 judgments match the frozen labels; 0 invalid responses.** Supported 4/4, contradicted 4/4, unknown 4/4. The four known-false controls were flagged and all four incomplete-evidence controls abstained. No contradicted or unknown control was accepted.

| Denominator / result | Count |
| --- | ---: |
| Supported gold / predicted supported | 4 /4 |
| Contradicted gold / predicted contradicted | 4 /4 |
| Unknown gold / predicted unknown | 4 /4 |
| Known-truth TP / FP / FN / TN | 4 /0 /0 /4 |
| Invalid decisions | 0 |
| Physical generation calls | 12 |
| Known native input+output tokens | 1,974 |
| Generation usage unknowns | 0 |

The known-truth judgment confusion matrix has eight eligible controls; unknown gold is excluded from that binary denominator and separately reported. Its point precision and recall are 1.0 in this tiny constructed set. They are **not AEE detector performance estimates**.

## Correction history and limits

Twelve synthetic closed-world factbooks, four cases per truth category; a convenience diagnostic, not spontaneous workflow hallucination prevalence.

Two factbooks were corrected after observing original v1 responses: case09 removed the finished=false presupposition conflict; case11 removed an explicitly wrong known reference from an incomplete inventory. Original labels, claims, other 10 cases and oracle remain unchanged; original v1 results stay published.

This corrective rerun is not an independent replication or a causal AEE benefit estimate. AEE was not the factbook verdict detector. No AEE precision/recall, whole-workflow hallucination rate or universal zero-hallucination claim follows.

Only the benchmark client route changed to the same existing worker with process/port/model/path guards. Historical underlying router socket failure remains unresolved.

API spend 0 excludes hardware, energy and labor; tokens are not bills. Diagnostic output 256 differs from main study output 8192 and is reported separately.

[Original corpus 1:10/12 original-label agreement with two challenged fixtures](../labelled-factbooks-10-20261019/README.md). Both original disagreements were defensible given explicit counterevidence/presuppositions; they were not established model hallucinations. Corrected controls were prospectively frozen before these new real model calls. Do not pool the two versions as independent samples or call the change an efficacy gain.

The separately frozen study 04/pipeline 11 continues through the full 12 trajectories /36 dependent checkpoints, independent grading, accounting/integrity audit and publication. This diagnostic alone does not complete that mission.

See diagnostic-plan.json, result.json, integrity-and-label-audit.json, call-export-map.json, setup-inventory.json, byte-exact frozen inputs and sanitized native receipts. Raw prompts/private reasoning remain local with hashes. All evidence file hashes are in files-sha256.json.

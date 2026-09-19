# Attempted matched ordinary versus AEE-guided repair

16 identical-start pairs: two projects × (three seeded defects + one clean control) × two seeds. Shared diagnostic input goes to both arms; guided receives actual AEE findings only when diagnostic completion permits an assessment. Not a full Spec Kit workflow comparison.

**Assessment coverage: 1/16 pairs.** Incomplete diagnostics remain in the denominator and all their work counts. The totals below describe the attempted protocol, not proof of an AEE effect. See summary.json for discordant pairs and whether an assessment actually occurred.

| Arm | Bugs fixed /12 | Final accepted /16 | Clean regressions /4 | Clean cases changed | Repair tokens | Tokens incl. shared diagnostic | Tokens/fix |
|---|---:|---:|---:|---:|---:|---:|---:|
| ordinary_repair | 4 | 8 | 0 | 0 | 1,622,660 | 2,299,943 | 574985.75 |
| aee_guided_repair | 5 | 9 | 0 | 0 | 1,869,798 | 2,547,081 | 509416.2 |

Shared diagnostic tokens are charged equally in treatment comparisons but counted once in the physical-work ledger. Unknown native usages remain null; reservation totals are not measured token totals. Findings require manual adjudication: subject overlap alone is not proof of defect detection. See findings-to-adjudicate.json and the final adjudication report.

Repair timing is exploratory: a roughly 25-second CPU-only selector calibration overlapped early generation. The repair experiment retained its original source freeze and selector. No overlapping model-generation calls occurred.

**Interpretation:** the sole extra guided-arm fix occurred without an AEE assessment. Only 1/16 diagnostics completed; both arms fixed that assessed case. This does not establish an AEE advantage. Read [the manual finding review](adjudication.md).

# Matched 02: stopped during calibration, no scored comparison

The first schema fault halted the entire run immediately: **16 setup generation
calls, 56,615 known native tokens (52,836 prompt + 3,779 completion), zero usage
unknowns and zero scored judgments**. All 720 scheduled final judgments remain
unattempted. No accepted delivery or treatment-effect estimate follows.

Call 0015 was the calibration Spec Kit+AEE plan. It returned the correct model,
finished with `stop`, and produced a4,662-character document despite the registered
3,000-character JSON-schema maximum. Local independent JSON-schema validation
rejected it; no output was truncated, rewritten or accepted.

The running server identifies build `b10894-d344123fe`. Its exact
[grammar parser](https://github.com/ggml-org/llama.cpp/blob/d344123fe2de081a72e02d6869360dfcbc0b528b/src/llama-grammar.cpp#L649-L656)
converts finite repetition maxima above 2,000 to unbounded repetition. The
[JSON-schema compiler](https://github.com/ggml-org/llama.cpp/blob/d344123fe2de081a72e02d6869360dfcbc0b528b/common/json-schema-to-grammar.cpp)
translates the 3,000-character limit into one such repetition. This explains the
unenforced native bound; it is not evidence of a new model, a router outage or
persistent disk exhaustion. Retained exact-source hashes accompany this report.
No shared service/model change is authorized or required for the client fix.

The preceding two synthetic native probes cost another **527 known tokens,
zero unknowns**. Their document was 1,252 characters: the probe did not reach or
prove the 3,000-character upper bound. Its 320-character rationale check was
narrower evidence. That inadequate admission check is retained honestly.

Prospective v3 keeps the SAME schemas, character budgets, cases, author labels,
seed, model, token/context/output/time/call caps and independent grading. An
explicit GBNF contract splits policy strings into up to 29 exact100-character blocks
and a1..100-character tail, below the server threshold. Fixed field order and bounded
whitespace are applied equally across arms. The original schemas remain separate
post-response validators. Three new technical setup probes cover exact3,000-
character delivery, decision bounds, and a decoder-only escaped literal. They
cannot establish factual correctness or select all-correct model behavior.
A new attempt needs committed exact-green source and its own freeze/paths;
matched 02 is never resumed. Repeated outcome-conditioned infrastructure debugging
and prior public-case exposure limit later causal/generalization claims.

[Every scheduled row](scheduled-rows.json), [all 16 sanitized receipts](call-receipts.json),
[summary](summary.json), [native-probe limits](native-probe-02.json),
[original frozen v2 registration](frozen-registration-v2.json), and
[decoder-source provenance](decoder-source-provenance.json) are retained.
The original raw inventory and source archive are unchanged; offline grading adds
no model calls. Native tokens are not a bill; local API spend 0 excludes hardware,
energy and labor. Neither this setup failure nor AEE findings are hallucination
labels. Completed model-only HaluEval/RAGTruth and synthetic factbook diagnostics
remain separate and must not be rerun or pooled as treatment evidence.

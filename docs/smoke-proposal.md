# Archived next-run proposal — user chose offline only
Request a **USD 30 global cap**, **USD 10 per attempt**, for one excluded development
task (django__django-11099), once per arm: three attempts, 30 minutes each.
No pilot spending is included. Stop on infrastructure/provider errors and uncertain
billing; retain reservations and all failures. Real smoke is an integration check,
not a performance comparison.

Suggested common snapshot: gpt-5.4-2026-03-05, medium reasoning, default service tier,
no unsupported sampling overrides, 4096 maximum output tokens per request.
Official model page checked 2026-09-17:
https://developers.openai.com/api/docs/models/gpt-5.4
It lists 1,050,000 context and 128,000 max output, and short-context list prices
USD 2.50 input / 0.25 cached input / 15 output per million. Above 272K input the
page states 2x input and 1.5x output pricing. The live snapshot must explicitly
validate cached long-context pricing and account eligibility before freezing.
The runner supports separate long-context rates and reserves the highest rates.
A full-context conservative input/output reservation is approximately USD 5.35
per request before releasing measured unused allowance; this is a bound, not an
expected call cost. A USD 10 attempt cap can therefore stop conservatively.

After three successful integration attempts, use measured spend to propose the
180-attempt pilot cap. Do not extrapolate model success or savings from smoke.
No API key should be shared in chat; set OPENAI_API_KEY in the local runner environment.

Other gates: Docker engine healthy, upstream gold grader smoke passed, solver
image inspection excludes held-out material, images pinned by digest, provider
usage details verified, source/configuration freeze committed.

User response 2026-09-17: Keep work offline. This proposal is not an active approval request.

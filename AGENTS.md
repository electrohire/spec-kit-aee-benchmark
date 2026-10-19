# Controller guidance
Read START_HERE.md, docs/protocol.md, the constitution and the newest durable state
before controlling inference. Latest user overrides historical readiness rules.
Use established upstream tasks/labels/graders; maintain only the thin adapter tests
in benchmarks/maintained-tests.json via scripts/check_active_harness.py. No coverage
target or product feature work. Old custom tasks/diagnostics are read-only history.
Preserve frozen active source and every failed call; no overlap/retry/resume.
Do not expose controller skills, sibling results or hidden gold to solvers.
Use benchmark-run/evidence-check; require independent grades and actual AEE/
Evaluator feedback where assigned. Release report flags are not authenticated
human/CI authority; only the protected exact-build audit/publication flow can
supply release evidence. No paid inference or service/model change.

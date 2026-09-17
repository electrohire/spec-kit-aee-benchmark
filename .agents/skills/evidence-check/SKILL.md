---
name: evidence-check
description: Audit this benchmark's claims, usage and independent grades, including AEE/Evaluator evidence and unresolved gaps.
---

Read the constitution, specs/001-benchmark/claims.json and reports/verification.md.
Recompute hashes for cited artifacts and match command, exit, time and scope.
An agent assertion is not an observation; an agent-written test is not independent
grading. Use the installed AEE adapter and Evaluator composition explicitly.
Keep unsupported claims and contradictions. Never replace SWE-bench resolution
with an internal AEE score. Null usage needs a reason; failed attempts retain cost.
Report false acceptance/unnecessary blocking only after joining final grades.

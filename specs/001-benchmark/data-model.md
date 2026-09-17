# Data model
Experiment: frozen SHA-256 files, seed, model, prices, dollar/token/time ceilings.
Task: instance_id, repo, base_commit, problem_statement, digest-pinned solver image.
Attempt: run/arm/task/repeat IDs, status, duration, patch and artifact hashes.
Call: unique call/request IDs, phase, provider/model, UTC times, duration, nullable
input/cached/output/reasoning counts with reason, price basis, retry status.
Grade: attempt ID, resolved boolean or null with reason, independent report hash.
Artifact: SHA-256-addressed bytes with append-only references.
Claim: installed AEE schema; explicit boundaries, falsification, links and evidence.

Attempts: planned -> started -> completed/limit/error/cancelled.
Interrupted started attempts are infrastructure failures; never silently rerun.
Reservations: reserved -> settled; uncertain charges keep the full reservation.
Grades join only after completion. Missing is never passed, unknown is never zero.

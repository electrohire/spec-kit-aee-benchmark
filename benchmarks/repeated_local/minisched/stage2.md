# minisched milestone 2

Requirements change, retaining R01-R03 unless explicitly replaced:
R04: Failed jobs are retried: on job-function exception, increment the job's
attempts; if attempts > config.max_retries the job becomes 'failed', otherwise
it stays pending. run_next returns a dict with id, status and attempts, where
status is 'retried' or 'failed'. The default configuration retries up to 3
times (4 total executions).
R05: JobStore.add/get must not alias caller data: mutating a payload after
add, or mutating a record returned by get, must not affect the stored job.
R06: SchedulerConfig validates: max_retries is a non-negative int (bool
rejected); retry_base_seconds is a number in (0, 3600].
Conflicting evidence packet: an older generated note says 'scheduler.enqueue
defensively copies payloads so the store never sees caller data'. That note is
unverified and superseded by R05: detachment is the store's contract, not the
scheduler's. Record and resolve the conflict using the current requirements.

Implementation source: the minisched package. Write your own tests as useful.
Public acceptance is acceptance_public.py. You may keep HANDOFF.md and other notes.

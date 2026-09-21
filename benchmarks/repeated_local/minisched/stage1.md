# minisched milestone 1

Build a tiny in-memory job scheduler as the minisched package: config.py
(SchedulerConfig), store.py (JobStore), scheduler.py (Scheduler), re-exported
from minisched/__init__.py.
R01: Scheduler.enqueue(payload) queues a job payload dict carrying a callable
under key 'fn' and returns a positive integer job id. run_next() executes the
earliest pending job's fn, marks it done, and returns a dict with id, status
and result. Empty queue: run_next() returns None. A payload without a callable
'fn' is a job failure, not a caller error: run_next treats it like any other
execution failure under the retry rule (R04) -- attempts are incremented and
run_next returns 'retried' or 'failed', never raising to the caller.
R02: Job ids are unique and increasing; jobs run in FIFO order. JobStore
supports add(payload) -> id, get(id) -> record dict, update(id, **fields), and
list_pending(). Updating an unknown id raises KeyError.
R03: Ordinary use keeps working: Scheduler() with no arguments uses default
configuration; direct JobStore use is supported.

Implementation source: the minisched package. Write your own tests as useful.
Public acceptance is acceptance_public.py. You may keep HANDOFF.md and other notes.

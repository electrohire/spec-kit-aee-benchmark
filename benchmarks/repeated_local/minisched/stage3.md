# minisched milestone 3

Resume after a context-free handoff with repository files and notes preserved.
R01-R06 remain active.
R07: An explicit max_retries=0 is honored: the first failure marks the job
'failed' immediately. The default max_retries is 3.
R08: Terminal jobs are never re-run: run_next skips 'failed' and 'done' jobs
and returns None when no job is pending.

Implementation source: the minisched package. Write your own tests as useful.
Public acceptance is acceptance_public.py. You may keep HANDOFF.md and other notes.

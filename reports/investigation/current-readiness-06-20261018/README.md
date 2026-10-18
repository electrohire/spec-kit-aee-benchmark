# Readiness06 stopped before scoring

The first TinyDB + Spec Kit + AEE case completed constitution and specification,
then exhausted its unchanged 32 planning actions without a completed plan. All
45 native calls ended with finish_reason=stop; 913,153 native tokens are known,
zero usage entries are unknown. No scored trajectory started. This is an unscored
controller/model readiness failure, not evidence comparing treatments.

The solver copied the plan scaffold, spent most subsequent actions inspecting
source, then emitted a shell command containing five heredoc openers with no
bodies or terminators. Bash warned but still truncated plan.md, research.md,
data-model.md, contracts/batch_writer_api.md and quickstart.md to zero bytes.
The final done was rejected by the existing artifact check. Native JSON shape was
valid; the output was not token-truncated. Context history pruning was recorded
and the phase instructions remained in the system message. Typed claims and the
literal writer cannot guarantee that a model chooses a usable command or finishes
its work within its slice. This failure does not establish a model-independent
workflow deficiency or independent code defect.

Retain artifacts/current-pipeline-06.json, current-representative-06, all calls,
source snapshot and alert. summary.json binds the result bytes and cost totals.
No retry/resume or budget extension is authorized by this report.

## Prospective correction under test

Every shell action is parsed with Bash -n inside the isolated solver container
before any part executes. A nonzero parse status OR parser diagnostic rejects the
original command without execution. The latter matters because an unterminated
heredoc can return parser status zero. No shell content is repaired. A syntactically
valid command may still fail, be destructive inside its sandbox, or be semantically
wrong. This is not a general safety validator.

All arms receive the same tool and common instructions to use the literal writer.
At half and three-quarter phase budgets, a host check reports the prescribed
artifact's existing basic presence/scaffold test, with remaining calls and an
explicit warning that presence is not semantic validation. These observations
are retained in phase_progress.jsonl. No extra inference actions, grading changes,
threshold relaxation, hidden feedback or automatic model retry is introduced.

Five real isolated Linux regressions prove incomplete heredocs, quotes, blocks and
substitutions cause no earlier file writes; a valid literal heredoc still executes
and preserves exit status 7. Ubuntu CI executes the same regression tests. Windows
local tests execute those shell cases in the pinned Linux Docker image with only
the fresh test directory exposed; Ubuntu executes Bash directly. A new unused preparation,
current transport/timing proof and all six fresh readiness cases are still required.

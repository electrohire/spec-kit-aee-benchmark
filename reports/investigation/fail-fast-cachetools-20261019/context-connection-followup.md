# Direct-client context preflight follow-up

PR37 merged at1b9503a with both hosted Ubuntu workflows successful:584 tests and all
workflow commands passed. GitHub's2026-10-19 Actions incident delayed check-rollup
propagation; the first normal merge attempt was blocked, then normal protected
merge succeeded without policy changes. No hosted status was manufactured.

Fresh pipeline12 passed image/grader controls, then halted on WinError10060 while
opening a TCP connection for `/apply-template`. No scored generation started.
The approved worker process/model/path/listener were subsequently unchanged and
healthy. Current health is not proof that the historical connection succeeded.

A separately retained zero-generation diagnostic completed all three context
cases using117 helper requests over two persistent connections. This supports a
client mitigation that reduces fresh handshakes; it does not establish the
underlying Windows/server timeout cause. The actual updated client subsequently
passed fresh context-calibration13 with zero generation.

The direct client now reuses completed HTTP/1.1 connections, verifies the bound
worker on every request, preserves canonical JSON bytes and per-request timeouts,
and propagates the first failure without retry, redirect or fallback. Model/path
checks before generation remain. Context failures retain bounded request/response
evidence. Synthetic local-server tests verify socket reuse, literal bytes, first
timeout/disconnect/error/redirect handling and worker-check refusal before network.
They do not authenticate a human or substitute for the real worker checks.

The v1 amendment remains immutable. V2 explicitly registers the client change;
v5 action grammar, model, tasks, seeds, caps and graders stay unchanged. Prior
transport12's five real calls and latency12's416.297/418.610-second samples are
retained prior-client observations on the same worker, with30830 native tokens
and zero cache per timing sample. They are not newly measured persistent-client
timings. Fresh context validation is required. Every arm uses the same new client.

Reused setup sources outside the execution checkout are now explicitly included
once in report export; they cannot silently drop the seven transport/timing calls
or their62602 known native tokens. The completed diagnostic11 is reused separately,
not rerun or pooled into treatment efficacy.

An attempted isolated Ubuntu replica initially stopped before tests because its
image lacked repository-pinned Python3.12.6. That validation-fixture failure and
the corrected image build are retained. Hosted logs independently establish the
real584-test Ubuntu result; no passing local replica is claimed from the failed
container. No shared model/service or official benchmark environment was modified.

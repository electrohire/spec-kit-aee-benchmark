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

## Workspace-path convention found on the next attempt

Pipeline14/study06 passed all preflight and four semantic AEE replays, then halted
after7 native calls/36899 known tokens with0 missing usage. In constitution, the
model returned valid native JSON writing
`/testbed/.specify/memory/constitution.md`; the relative-only tool rejected it.
There was no repeat loop, no scored AEE assessment and no completed delivery.
The original freeze `7ccd9994adb19baa1583893551f20c9eafe99dce2fa4649f3d11e2f972fca7a5`
and failed output remain unchanged.

V3 explicitly accepts that one fixed workspace prefix as an alias for the sandbox
cwd. Other absolute roots, empty/noncanonical segments, traversal, backslashes,
drive markers, NULs and oversized paths remain refused; the original symlink/root
checks and literal content transport remain. Native grammar/model/caps do not
change. Two positive cases first failed, with13 rejection cases already passing;
all15 pass after the alias. The149 affected checks pass.

A labelled post-implementation replay executed the unchanged original model action
in a fresh isolated Cachetools sandbox with zero new generation. It wrote/read3758
UTF-8 bytes with matching SHA256
`1ca023d6344e51c0793f66cf1305176c37574f1d4e8f8b2b6bb810f2bad1ce19`.
This is debugging evidence for the tool convention, not a successful scored model
trajectory. No old model output is edited, no failed run is promoted, and no
hallucination/efficacy conclusion follows from the replay.

The next native-probe bootstrap exposed a separate stale-socket issue: after a
long setup pause, a pooled connection was aborted before any generation. The real
server advertises `Keep-Alive: timeout=5, max=100`. The client now retires a socket
before sending a new request once its idle age exceeds a conservative bound
(80percent of the advertised timeout, capped at4seconds;1second without a hint).
An actual6-second idle check passed with socket retirement before the next request.
This is not a replay of a failed request; all actual request failures still halt.
The151 affected checks pass, including no-retry and pre-network expiry cases.
Native bootstrap failures now retain their bounded evidence and zero-generation
classification. The failed probe/log remains retained rather than overwritten.

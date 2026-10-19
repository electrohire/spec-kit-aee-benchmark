# Transport 03 rejected an incomplete literal-write action

The fresh native probe03 ran after PR22 merged, before new latency, readiness or
scoring. The shell probe passed; the literal-write probe returned action/path
and a summary but omitted content. Ordinary protocol v3 made content optional,
although the claim-bearing grammar and host executor required it. The probe
correctly refused the response before executing a write.

Retain both calls and their 221 known native tokens (zero unknown usage) under
artifacts/current-action-transport-03. No tool execution or readiness success
is attributed to the incomplete action. The failed result remains passed=false.

Protocol v4 gives ordinary and claim-bearing phases the same disjoint tool
branches: shell requires command; write_file requires path/content; terminals
have separate fields. A summary cannot substitute for content. Native shape
constraints do not establish truth or adequate file content. Runtime validation
and the unchanged intervention policy still apply. Four fresh native probes in
an unused folder, new grammar-bound latency and all six readiness cases remain
required. Nothing is retried inside03 or interpreted as completed scoring.

# Message-security middleware

`src/benchmark_runner/message_security.py` is the in-harness leg of the message-security line. It tags the provenance of content entering the harness, screens that content with a deterministic first screen (L1) and an epistemic-protocol screen (L2), and holds consequential actions at a gate until the acting content's provenance supports them. It landed in this repository with the harness middleware change (PR #80) and is covered by the maintained message-security tests.

The design record is the 2026-10-29 message-security injection-protection document, held in the program's document store outside this repository. The public artifact repository is electrohire/injection-defense, which carries the offline battery and the published results. This module is the harness-side implementation only; measured screen performance is recorded with the design record and the public repository, not here.

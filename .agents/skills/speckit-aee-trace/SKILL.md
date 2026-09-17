---
name: speckit-aee-trace
description: Render claim dependencies and inspect epistemic provenance
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: aee:commands/speckit.aee.trace.md
---

# AEE Trace

Render the dependency/conflict structure for explicit claims and inspect whether evidence and provenance references resolve.

## User input

```text
$ARGUMENTS
```

Resolve `artifact=<path>`, apply the project-root and symlink guardrails from `$speckit-aee-assess`, then run:

```bash
python .specify/extensions/aee/scripts/python/run_aee.py graph --input <artifact>
```

Read the generated Mermaid file and report roots, leaves, missing references, cycles, contradictions, and claims capped by weak dependencies. The graph expresses declared epistemic structure; it does not establish causality.
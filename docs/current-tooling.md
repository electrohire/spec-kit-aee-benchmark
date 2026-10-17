# Current controller tooling — 2026-10-16

Verified against live PyPI/GitHub and actual installation:

| Component | Installed/latest published |
|---|---|
| Specify CLI | 1.2.1 |
| applied-epistemic-engineering (import/CLI `aee`) | 1.5.3 |
| Spec Kit `aee` extension | 1.5.2 |
| Spec Kit `evaluator` extension | 1.1.2 |
| jsonschema | 4.26.0 |
| mini-swe-agent | 2.4.6 |

`uv sync --locked --group dev --python 3.12.6` installs Python pins.
`specify extension list` confirms both enabled extensions. `uv pip check` verified
all 106 installed packages are compatible after a compatible lock upgrade.
The published dependencies have no known vulnerabilities in the recorded
[`pip-audit` check](../reports/dependency-validation/2026-10-16/pip-audit-current.json);
the local editable benchmark is not published on PyPI and was
not covered by that advisory lookup. Five packages remain below their newest
major releases because of declared upstream constraints: filelock, fsspec,
huggingface-hub, importlib-metadata and openai. "Latest" here means the latest
compatible dependency graph, not overriding those constraints. See the
[recorded upstream constraints](../reports/dependency-validation/2026-10-16/dependency-constraint-explanations.json).
Transitive dependencies are locked;
never drift to future "latest" during an experiment. Operation skills were
regenerated using Specify1.2.1; controller skills and constitution were preserved.
Pin checks cover CLI/integration, engine, extension registry and vendored bytes.
Historical archived freezes retain their own skills and dependencies.

The actual refresh ran `specify init --here --force --non-interactive
--integration codex --script py --ignore-agent-tools`, followed by exact public
archive installations through Specify. Local assessment artifacts were preserved.

## Reproduction and trust troubleshooting

Ordinary guides use `specify extension add aee`. Specify1.2.x needs an
install-allowed trusted catalog for bare installation; discovery-only catalog
acceptance does not change CLI trust policy. Benchmark reproduction deliberately
uses immutable archives listed with SHA256/tag identities in `manifests/versions.json`:

```sh
specify extension add aee --from https://github.com/electrohire/spec-kit-aee/archive/refs/tags/v1.5.2.zip --force
specify extension add evaluator --from https://github.com/electrohire/spec-kit-evaluator/archive/refs/tags/v1.1.2.zip --force
```

AEE provisions its compatible engine/evaluator dependencies. Explicit evaluator
installation here pins bytes for an experiment; it does not imply ordinary users
must manage the dependencies themselves. New versions require a fresh freeze and
workflow/grader preflight, rather than rewriting historical results.

The free loopback readiness probe in `reports/feasibility/local-20261016` returned
the expected model identity: 73 input +29 output tokens, $0 API spend. Missing
reasoning-token detail is not imputed. Readiness is not complete-context throughput,
treatment adherence or efficacy evidence. No shared service settings or credentials
were changed. The new lifecycle importer is an analysis interface; the fresh scored
study is complete; see [results and exposure limits](../reports/local/current-study-01/analysis.md). Native
near-context probes for the selected `qwen3.8-27b` candidate passed, producing a
480-second timeout by the preregistered twice-observed-latency rule. Earlier
failed candidate calibrations remain setup costs, not scored comparisons.

The [focused actual AEE audit](../reports/aee-validation/current-20261017-04/summary.json)
verified seven of seven narrow machine observations against real test output, with
zero evidence findings and exactly one AEE result consumed by Evaluator. The
overall `iterate` verdict explicitly preserves missing human acceptance. It is
neither efficacy evidence nor a claim of perfect confidence.

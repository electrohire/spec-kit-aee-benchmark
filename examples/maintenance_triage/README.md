# Maintenance triage teaching example
Synthetic inputs and illustrative thresholds; not validated for maintenance or safety.
Implementation: src/benchmark_runner/triage.py. Requires Python 3.11+.
Run from repository: uv sync --locked; uv run maintenance-triage --help
uv run maintenance-triage examples/maintenance_triage/sample.csv output.json
Compare output with sample.json. Tests: uv run pytest tests/test_triage.py -q
The six REQ-TRIAGE requirements and acceptance evidence live in specs/001-benchmark/.

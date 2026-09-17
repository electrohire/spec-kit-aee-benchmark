# Quickstart
1. uv sync --locked --group dev
2. uv run pytest -q
3. uv run maintenance-triage examples/maintenance_triage/sample.csv output.json
4. uv run aee-bench preflight
5. Follow docs/reproduction.md to freeze and dry-run.

Live generation fails closed until model, prices, caps, images and smoke gates
are supplied. Offline results do not establish real provider or Docker fidelity.

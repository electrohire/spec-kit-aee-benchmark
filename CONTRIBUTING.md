# Contributing

Use a feature branch. Work may begin in a draft PR; mark completed PRs ready for
review after documenting validation and remaining evidence gaps, as required by
the constitution. No merge or release is implied. Read the constitution and protocol.
Run `uv sync --locked --group dev`, `uv run python scripts/check_active_harness.py`
and `uv run python scripts/check_docs.py`. Follow the [documentation style](docs/STYLE.md).
Document fixture versus real evidence. Never tune frozen prompts from scored results.
Record protocol deviations and publish changed run configurations under new IDs.
License selection is pending; preserve upstream notices.

"""Reader-visible regressions; raw model text must never use this formatter."""
import pytest
import importlib.util
from pathlib import Path
from markdown_it import MarkdownIt

from benchmark_runner.markdown_presentation import format_markdown, write_markdown


@pytest.mark.parametrize(("source", "expected"), [
    ("Read [the design](design.md) and\n[the contract](contract.md).\n",
     "Read [the design](design.md) and [the contract](contract.md).\n"),
    ("* first\n  continuation\n  * nested\n    continuation\n",
     "* first continuation\n  * nested continuation\n"),
    ("> quoted\n> continuation\n", "> quoted continuation\n"),
    ("Read \nmore.\n", "Read more.\n"),
    ("---\ntitle: ${title}\nauthor: Example\n---\n\nRead\nmore.\n",
     "---\ntitle: ${title}\nauthor: Example\n---\n\nRead more.\n"),
    ("one  \ntwo\\\nthree\n", "one  \ntwo\\\nthree\n"),
    ("```mermaid\na --> b\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
     "```mermaid\na --> b\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"),
    ("- measured **213,457** tokens\n  with `0unknowns` preserved as a literal.\n",
     "* measured **213,457** tokens with `0unknowns` preserved as a literal.\n"),
])
def test_report_paragraphs_render_without_artificial_breaks(source, expected):
    assert format_markdown(source) == expected
    assert format_markdown(expected) == expected
    # A viewer that renders soft breaks explicitly must still see one paragraph.
    body = expected.split("---\n", 2)[-1] if expected.startswith("---\n") else expected
    rendered = MarkdownIt("commonmark", {"breaks": True}).enable("table").render(body)
    if "  \n" not in source and "\\\n" not in source:
        assert "<br" not in rendered


def test_generated_report_writer_formats_only_its_presentation_file(tmp_path):
    raw = tmp_path / "raw-response.md"
    raw.write_bytes(b"original\nmodel output\n")
    output = tmp_path / "README.md"
    write_markdown(output, "Summary with\n[a link](report.json).\n")
    assert output.read_bytes() == b"Summary with [a link](report.json).\n"
    assert raw.read_bytes() == b"original\nmodel output\n"


def test_publication_guard_refuses_wrapped_prose_and_unclosed_code():
    path = Path(__file__).resolve().parents[1] / "scripts/check_docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert list(guard.check_text("Read\nmore.\n"))
    assert any("close" in message for _, message in guard.check_text("```json\n{}\n"))
    assert not list(guard.check_text("Read more.\n\n```json\n{}\n```\n"))

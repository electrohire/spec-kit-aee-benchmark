"""Check presentation docs without rewriting frozen evidence or upstream prompts."""
import re
from pathlib import Path

from benchmark_runner.markdown_presentation import format_markdown

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = re.compile(r"(`+)(.*?)\1|\]\([^)]*\)|<?https?://[^\s>]+>?")
GLUED = re.compile(
    r"\b(?:cost|with|and|of|all|the|HaluEval|RAGTruth|margin|paired)(?=\d)"
    r"|(?<=\d)(?:known|native|tokens?|calls?|misses|false|correct|unknowns?|usage|responses)\b"
    r"|(?<=%)(?=coverage\b)",
    re.IGNORECASE,
)
BROKEN_BOLD_LABEL = re.compile(r"\*\*[^*\n]+:\* \*(?:\s|$)")


def documentation_paths(root=ROOT):
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if (
            len(rel.parts) == 1
            or (rel.parts[0] == "docs" and rel.parts[1] != "archive")
            or rel.parts[0] == "specs"
            or (rel.parts[0] == "benchmarks" and "PROTOCOL" in path.name)
            or (rel.parts[0] == "reports" and len(rel.parts) <= 4
                and (path.name == "README.md" or len(rel.parts) == 2
                     or path.name == "context-connection-followup.md"))
        ):
            yield path


def check_text(text):
    if format_markdown(text) != text:
        yield 1, "keep prose paragraphs/list items on one source line; preserve explicit breaks"
    fence = None
    generated = False
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"<!-- (historical-results|current-results|stopped-study02):start -->", line):
            generated = True
        if generated:
            if BROKEN_BOLD_LABEL.search(PROTECTED.sub(" ", line)):
                yield number, "close bold labels with '**', not '* *'"
            if re.match(r"<!-- (historical-results|current-results|stopped-study02):end -->", line):
                generated = False
            continue
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            char = marker[1][0]
            fence = char if fence is None else (None if fence == char else fence)
            continue
        if fence or line.startswith("    ") or line.lstrip().startswith("<!--"):
            continue
        prose = PROTECTED.sub(" ", line)
        if BROKEN_BOLD_LABEL.search(prose):
            yield number, "close bold labels with '**', not '* *'"
        if GLUED.search(prose):
            yield number, "separate prose words and measured numbers with spaces"
        if re.match(r"^\s*(?:>\s*)?[-+]\s+\S", line):
            yield number, "use '* ' for an unordered Markdown list"
    if fence is not None:
        yield 1, "close the fenced code block"


if __name__ == "__main__":
    files = list(documentation_paths())
    errors = [f"{path.relative_to(ROOT)}:{line}: {message}"
              for path in files for line, message in check_text(path.read_text(encoding="utf-8"))]
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Documentation spacing and list checks passed: {len(files)} files")

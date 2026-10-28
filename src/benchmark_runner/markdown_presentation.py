"""Presentation-only Markdown formatting; never apply to prompts or raw evidence."""
import re
from pathlib import Path

from markdown_it import MarkdownIt

from .verified_write import write_text_verified


def _signature(tokens):
    result = []
    for token in tokens:
        kind = "text" if token.type == "softbreak" else token.type
        content = " " if token.type == "softbreak" else token.content
        if kind == "text":
            content = re.sub(r"\s+", " ", content)
            if result and result[-1][0] == "text":
                result[-1] = ("text", re.sub(r"\s+", " ", result[-1][1] + content))
                continue
            result.append(("text", content))
        else:
            result.append((kind, token.nesting, token.attrs,
                           _signature(token.children) if token.children is not None else content))
    return result


def format_markdown(text):
    """Unwrap soft paragraph breaks, retain explicit breaks and Markdown structure.

    CommonMark source maps keep fences, tables, indentation and nested lists out
    of prose substitutions. An independent parse refuses semantic changes.
    """
    parser = MarkdownIt("commonmark").enable("table")
    tokens = parser.parse(text)
    lines = text.splitlines()
    frontmatter_end = 0
    if lines and lines[0] == "---":
        frontmatter_end = next((i + 1 for i, line in enumerate(lines[1:], 1)
                                if line in ("---", "...")), 0)
    replacements = []
    lists = []
    for token in tokens:
        if token.type in ("bullet_list_open", "ordered_list_open"):
            lists.append(token.type)
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif token.type == "list_item_open" and lists[-1] == "bullet_list_open":
            start = token.map[0]
            if start >= frontmatter_end:
                lines[start] = re.sub(r"^(\s*(?:>\s*)*)[-+*] ", r"\1* ", lines[start])
        if token.type != "inline" or token.map is None or token.children is None:
            continue
        kinds = {child.type for child in token.children}
        if "softbreak" not in kinds or "hardbreak" in kinds:
            continue
        start, end = token.map
        if start < frontmatter_end:
            continue
        continuation = [re.sub(r"^(?:\s*>\s?)+", "", line).strip()
                        for line in lines[start + 1:end]]
        replacements.append((start, end, " ".join([lines[start].rstrip(), *continuation])))
    for start, end, replacement in reversed(replacements):
        lines[start:end] = [replacement]
    formatted = "\n".join(lines).rstrip() + "\n" if lines else ""
    if _signature(tokens) != _signature(parser.parse(formatted)):
        raise ValueError("Markdown formatting would change content or structure")
    return formatted


def write_markdown(path, text):
    # Verified write (fleet standard, 2026-10-28): presentation
    # outputs are reports; a silent partial write would stand as the
    # report, so the write verifies by read-back or raises.
    write_text_verified(path, format_markdown(text))

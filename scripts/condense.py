"""Deterministic phase-1 condensation for the Claim B experiment.

Three levels (see docs/claim-b-condensation.md):
- intact:     full transcript verbatim ("[role] content" lines).
- light:      activity line + spec preamble's first paragraph + per
              constraint "C0N: title. first sentence". Budget: <= 50% of
              spec words.
- aggressive: activity line + per constraint "C0N: title". All detail
              dropped. Budget: <= 20% of spec words.

Budgets use whitespace-split words. The summarizer raises (fail closed) if a
budget is exceeded: an over-budget spec is rewritten, not accommodated.
Fully deterministic: same inputs -> byte-identical output.
"""
import re

CONSTRAINT_RE = re.compile(r"^## (C\d+): (.+)$", re.M)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _words(text):
    return len(text.split())


def parse_spec(spec_text):
    """Return (preamble_first_paragraph, [(cid, title, first_sentence)])."""
    m = CONSTRAINT_RE.search(spec_text)
    head = spec_text[: m.start()] if m else spec_text
    paras = [p.strip() for p in head.split("\n\n") if p.strip()]
    paras = [p for p in paras if not p.startswith("#")]
    preamble = " ".join(paras[0].split()) if paras else ""
    constraints = []
    for cm in CONSTRAINT_RE.finditer(spec_text):
        cid, title = cm.group(1), cm.group(2).strip()
        detail_start = cm.end()
        nxt = CONSTRAINT_RE.search(spec_text, detail_start)
        detail = spec_text[detail_start: nxt.start() if nxt else len(spec_text)]
        detail = " ".join(detail.split())
        first = _SENTENCE_RE.split(detail, maxsplit=1)[0].strip()
        constraints.append((cid, title, first))
    return preamble, constraints


def _activity_line(spec_text, transcript, n_constraints):
    w = _words(spec_text)
    turns = sum(1 for role, _ in transcript if role == "assistant")
    return (
        f"Phase 1: full spec read ({w} words, {n_constraints} constraints), "
        f"{turns} assistant turns."
    )


def summarize_phase1(transcript, spec_text, level):
    """Condense a phase-1 transcript. transcript: list of (role, content)."""
    if level == "intact":
        return "\n".join(f"[{role}] {content}" for role, content in transcript)
    preamble, constraints = parse_spec(spec_text)
    spec_words = _words(spec_text)
    activity = _activity_line(spec_text, transcript, len(constraints))
    if level == "light":
        lines = [activity, "", preamble, ""]
        for cid, title, first in constraints:
            lines.append(f"{cid}: {title}. {first}")
        summary = "\n".join(lines)
        if _words(summary) > 0.5 * spec_words:
            raise ValueError(
                f"light summary {_words(summary)} words exceeds 50% of "
                f"spec words ({spec_words}): rewrite the spec"
            )
        return summary
    if level == "aggressive":
        lines = [activity, ""]
        for cid, title, _first in constraints:
            lines.append(f"{cid}: {title}")
        summary = "\n".join(lines)
        if _words(summary) > 0.2 * spec_words:
            raise ValueError(
                f"aggressive summary {_words(summary)} words exceeds 20% of "
                f"spec words ({spec_words}): rewrite the spec"
            )
        return summary
    raise ValueError(f"unknown condensation level: {level}")

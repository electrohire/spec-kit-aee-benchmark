"""Attractive trap for csvnorm: naive line.split(",") parsing.

Looks right on simple input, but quoted commas split fields, quoted newlines
split rows, and "" escapes are left literal. Public tests avoid all three.
"""


def normalize_csv(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    # TRAP: splitting lines and fields naively.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    out = [",".join(h.strip() for h in lines[0].split(","))]
    for ln in lines[1:]:
        out.append(",".join(f.strip() for f in ln.split(",")))
    return "\n".join(out)

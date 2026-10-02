"""Greedy word wrapper (reference implementation)."""


def wrap_text(text, width, indent=""):
    if width < 1:
        raise ValueError("width must be >= 1")
    words = text.split()
    lines = []
    current = []
    current_len = 0
    for w in words:
        while len(w) > width:
            if current:
                lines.append(indent + " ".join(current))
                current, current_len = [], 0
            lines.append(indent + w[:width])
            w = w[width:]
        if not current:
            current, current_len = [w], len(w)
        elif current_len + 1 + len(w) <= width:
            current.append(w)
            current_len += 1 + len(w)
        else:
            lines.append(indent + " ".join(current))
            current, current_len = [w], len(w)
    if current:
        lines.append(indent + " ".join(current))
    return lines

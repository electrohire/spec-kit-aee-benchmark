"""Attractive trap for wordwrap: greedy packing without long-word breaking.

Overlong words are emitted whole on their own line, exceeding the width.
Reads naturally ("a word is a word"), passes every public test, and only the
C03 hidden tests catch it.
"""


def wrap_text(text, width, indent=""):
    if width < 1:
        raise ValueError("width must be >= 1")
    words = text.split()
    lines = []
    current = []
    current_len = 0
    for w in words:
        # TRAP: no breaking of overlong words; they are placed whole.
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

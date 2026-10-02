"""CSV normalizer (reference implementation)."""


def _parse(text):
    """Parse CSV text -> (rows, quoted_flags). quoted_flags[r][i] is True iff
    the field's opening quote was its first character."""
    rows, qflags = [], []
    row, flags, buf = [], [], []
    f_quoted = False
    in_quotes = False
    field_start = True
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    buf.append('"')
                    i += 2
                else:
                    in_quotes = False
                    i += 1
            else:
                buf.append(ch)
                i += 1
            continue
        if ch == '"' and field_start:
            in_quotes = True
            f_quoted = True
            field_start = False
            i += 1
            continue
        if ch == ',':
            row.append(''.join(buf))
            flags.append(f_quoted)
            buf, f_quoted, field_start = [], False, True
            i += 1
            continue
        if ch == '\r' or ch == '\n':
            row.append(''.join(buf))
            flags.append(f_quoted)
            rows.append(row)
            qflags.append(flags)
            row, flags, buf = [], [], []
            f_quoted, field_start = False, True
            if ch == '\r' and i + 1 < n and text[i + 1] == '\n':
                i += 2
            else:
                i += 1
            continue
        buf.append(ch)
        field_start = False
        i += 1
    if buf or row:
        row.append(''.join(buf))
        flags.append(f_quoted)
        rows.append(row)
        qflags.append(flags)
    return rows, qflags


def _quote_cell(cell):
    if any(ch in cell for ch in (',', '"', '\n', '\r')):
        return '"' + cell.replace('"', '""') + '"'
    return cell


def normalize_csv(text):
    if text.startswith('\ufeff'):
        text = text[1:]
    rows, qflags = _parse(text)
    kept = [(r, q) for r, q in zip(rows, qflags)
            if any(f.strip() for f in r)]
    if not kept:
        return ""
    lines = []
    for r, q in kept:
        cells = [f if quoted else f.strip() for f, quoted in zip(r, q)]
        lines.append(','.join(_quote_cell(c) for c in cells))
    return '\n'.join(lines)

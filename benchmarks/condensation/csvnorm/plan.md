# Plan: CSV normalizer

1. Strip a leading U+FEFF if present (C03).
2. Hand-parse (do not use line.split(",")): a small state machine tracking
   in_quotes, with `""` as an escaped quote and newlines inside quotes kept
   in the field (C06). Record per field whether the opening quote was the
   first character (C04).
3. Drop rows where every field is empty/whitespace-only (C02).
4. First kept row is the header (C01); never reorder rows or columns (C05).
5. Normalize cells: quoted -> verbatim; unquoted -> strip() (C04).
6. Emit with minimal quoting: quote iff the cell contains `,`, `"`, or a
   newline; escape `"` as `""`. Join rows with `\n`, no trailing newline;
   blank input -> `""` (C07).

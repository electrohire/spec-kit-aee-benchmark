# CSV normalizer

Build `csvnorm.py` with function `normalize_csv(text: str) -> str`, which
takes CSV text and returns normalized CSV text.

## C01: first non-blank header
The first row containing any non-whitespace field is the header. Column order
is preserved exactly as in the header row.

## C02: skip blank lines
Lines where every field is empty or whitespace-only are dropped entirely. A
blank line before the header does not become the header, and blank lines
between data rows are not emitted.

## C03: strip BOM
A leading UTF-8 BOM (U+FEFF) is stripped before parsing. If the text starts
with a byte-order mark, it is removed before parsing, so it never appears
in the first header name. This is stated here once.

## C04: quoted verbatim
Quoted fields keep their exact inner content, unstripped. A field wrapped in
double quotes keeps its exact inner content: no whitespace stripping inside
the quotes. Any other field has leading and trailing whitespace stripped. A
field counts as quoted only if the opening quote is the first character of
the field: `  "x"` is not a quoted field (it strips to `"x"`). This
distinction is stated here once.

## C05: order preserved
Data rows keep their input order and columns keep the header's order. The
normalizer must not sort or otherwise reorder anything. (Negative constraint.)

## C06: quoted specials round-trip
Quoted commas, `""` escapes, and embedded newlines round-trip. Fields may
contain commas, double quotes (escaped as `""`), or embedded newlines inside
double quotes. All three must parse and re-emit correctly. The naive approach
of splitting lines on commas breaks all three.

## C07: output format
Rows join with `\n`; no trailing newline. Rows are joined with `\n` (never
`\r\n`); there is no trailing newline at the end of the output. Fields are
quoted minimally: a field is wrapped in double quotes only if it contains a
comma, a double quote, or a newline, with inner quotes escaped as `""`.
Empty or all-blank input yields `""`.

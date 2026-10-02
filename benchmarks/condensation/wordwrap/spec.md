# Greedy word wrapper

Build `wordwrap.py` with function
`wrap_text(text: str, width: int, indent: str = "") -> list[str]`, which
wraps text into a list of lines.

## C01: greedy packing
Words pack greedily: each line holds as many whole words as fit. Words are
joined with single spaces; a word starts a new line only when it does not
fit on the current one.

## C02: width validated
`width < 1` raises `ValueError`.

## C03: break long words
Overlong words are broken into pieces of at most `width`. A word longer
than `width` is broken across lines; the pieces never exceed `width`
characters. For example, `"abcdefghij"` at width 4 becomes `"abcd"`,
`"efgh"`, `"ij"`. A long word after a partial line starts on a fresh line
(the partial line is flushed first). This breaking rule is stated here once.

## C04: collapse whitespace
Words split on any whitespace; runs collapse to single spaces. Input words
are split on any whitespace (spaces, tabs, newlines); runs of whitespace
collapse to the single spaces between output words. Newlines in the input do
not force line breaks in the output.

## C05: no trailing space
No output line has trailing spaces. (Negative constraint.)

## C06: indent excluded
`indent` prefixes every output line. The `width` limit applies to the content
after the indent, not to the line including the indent. This is stated here
once.

## C07: empty input
Empty or whitespace-only input returns `[]`.

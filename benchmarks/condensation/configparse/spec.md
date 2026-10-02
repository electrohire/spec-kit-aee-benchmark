# INI-ish config parser with interpolation

Build `configparse.py` with `parse(text: str) -> dict` and
`get(config, section, key, default=None)`.

`parse` returns `{section: {key: value}}` with all values as strings.
Malformed input raises `ConfigError` (a subclass of `Exception` defined in
the module).

## C01: sections and keys
`[section]` opens a section; later `key = value` lines belong to it. Blank
lines and lines starting with `#` or `;` are ignored. A key before any
section header raises `ConfigError`, as does a line without `=` or an empty
section name.

## C02: interpolation syntax
`${key}` refers to the same section; `${section.key}` to any section.
Values may reference other values with `${key}` (same section) or
`${section.key}` (any section). References resolve against the raw parsed
values. Referencing a missing section or key raises `ConfigError`.

## C03: one-level interpolation
Substituted values are NOT re-scanned for further references. If `[b]` sets
`y = ${c.z}`, then `[a]`'s `x = start-${b.y}-end` resolves to the literal
string `start-${c.z}-end`, not `start-deep-end`. Self-references terminate:
`x = v-${a.x}` in `[a]` resolves to the literal `v-v-${a.x}`. This one-level
rule is stated here once.

## C04: strings, never code
The parser never evals or interprets values as code. The parser must not
eval, exec, or otherwise interpret values as code. A value like
`__import__('os').system('x')` is just a string. (Negative constraint.)

## C05: last key wins
A repeated key keeps the last value; repeated sections merge. A repeated key
in one section keeps the last value. A repeated `[section]` header merges
into the existing section (keys accumulate; last wins per key).

## C06: get with default
`get` returns the value or `default` when section/key is missing. `get(config,
section, key, default=None)` returns the value, or `default` when the section
or key is missing. It never raises for missing entries.

## C07: inline hash kept
Inline `#` after a value is kept; it is not a comment. Whitespace around
section names, keys, the `=`, and values is stripped. Whitespace inside a
value is preserved. Inline comments are NOT stripped: a `#` after a value is
part of the value. This inline-`#` rule is stated here once.

# Plan: INI-ish config parser

1. `ConfigError(Exception)`.
2. `parse(text)`: iterate lines. Strip each line; skip blank and `#`/`;`
   comments. `[name]` -> set current section (strip name; empty -> ConfigError;
   `setdefault` so repeats merge, C05). `key = value` -> partition on first
   `=`; strip key and value (C07); empty key or no `=` or no current section ->
   ConfigError (C01). Store raw strings; last wins (C05). Values are never
   evaluated (C04).
3. Interpolation over the RAW table, exactly one pass (C03): for each value,
   `re.sub(r"\$\{([^}]+)\}", repl, value)` where repl looks up `${key}` in the
   same section's raw dict or `${sec.key}` in the raw table; missing ->
   ConfigError (C02). The replacement text is inserted literally and never
   re-scanned, so nesting and self-reference terminate with literals left in
   place.
4. `get(config, section, key, default=None)`: nested `.get` with defaults;
   never raises for missing entries (C06).
5. Inline `#` after a value is kept (only full-line comments are comments).

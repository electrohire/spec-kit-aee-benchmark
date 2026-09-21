# Pure path normalizer

Build `pathresolve.py` with function `resolve_path(path: str) -> str`.

It normalizes a POSIX-style path purely lexically: no filesystem access, no
symlink resolution, no `os.path` calls.

## C01: drop dot segments
`.` segments are removed. `a/./b` becomes `a/b`, and a trailing `/.` is
removed as well: `a/.` becomes `a`.

## C02: dot-dot pops
`..` removes the previous normal segment. `a/b/../c` becomes `a/c`, and a
trailing `/..` pops too: `a/b/..` becomes `a`.

## C03: collapse slashes
Runs of `/` collapse to one. `a//b` becomes `a/b`; a trailing `/` is
dropped: `a/b/` becomes `a/b`. The root path `/` stays `/`.

## C04: keep leading dot-dot
A `..` with nothing to pop is kept on relative paths. `../a` stays `../a`,
and `a/../../b` becomes `../b`. For absolute paths a leading `..` has
nothing to pop and is dropped: `/../a` becomes `/a`. This matches POSIX
semantics, where `..` past the start of a relative path stays meaningful.
This leading-dot-dot rule is stated here once.

## C05: lexical only
No filesystem access and no `os.path`/`pathlib`; hand-roll the segment
stack. The function must not touch the filesystem and must not call
`os.path` (or `pathlib`). (Negative constraint.)

## C06: no empty segments
Edge slashes never produce empty segments in the output. Leading, trailing,
and doubled slashes are absorbed: `/a/b` stays `/a/b`, never `//a/b`;
`a/b/` becomes `a/b`, never `a/b/`. This is stated here once.

## C07: degenerate inputs
`""` becomes `"."`, `"."` stays `"."`, and `".."` stays `".."` (a relative
leading dot-dot, per C04).

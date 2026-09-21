# Plan: pure path normalizer

1. `absolute = path.startswith("/")`. Split on `/`; drop empty segments and
   `.` segments (C01, C03, C06).
2. Walk the segments with a stack. For `..`: if the stack is non-empty and
   its top is not `..`, pop (C02). Else if the path is relative, push `..`
   (C04: leading dot-dot kept); if absolute, drop it (C04).
3. Rebuild: `"/" + "/".join(stack)` for absolute (root -> `/`, C03), or
   `"/".join(stack)` for relative; empty relative result -> `"."` (C07).
4. No `os.path`/`pathlib`/filesystem calls anywhere (C05).

"""Attractive trap for pathresolve: drops leading ".." on relative paths.

Popping ".." unconditionally looks like the natural stack rule, but it turns
`../a` into `a` and `a/../../b` into `b`, violating C04. Public tests never
use a leading "..", so they pass.
"""


def resolve_path(path):
    absolute = path.startswith("/")
    stack = []
    for seg in path.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            # TRAP: a ".." with nothing to pop is dropped even when the path
            # is relative (C04 requires keeping it).
            continue
        stack.append(seg)
    if absolute:
        return "/" + "/".join(stack) if stack else "/"
    return "/".join(stack) if stack else "."

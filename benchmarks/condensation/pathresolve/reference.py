"""Pure POSIX path normalizer (reference implementation)."""


def resolve_path(path):
    absolute = path.startswith("/")
    stack = []
    for seg in path.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            # absolute with nothing to pop: drop the ".."
            continue
        stack.append(seg)
    if absolute:
        return "/" + "/".join(stack) if stack else "/"
    return "/".join(stack) if stack else "."

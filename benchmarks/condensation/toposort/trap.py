"""Attractive trap for toposort: Kahn's algorithm with a LIFO worklist.

"Any worklist gives a valid topological order" is true -- and that is exactly
why this passes every public test. But C04 requires smallest-first
tie-breaking, which the stack violates: independent nodes come out in
reverse-sorted order.
"""


class CycleError(Exception):
    pass


def topo_sort(deps):
    nodes = set(deps)
    for ds in deps.values():
        nodes.update(ds)
    indegree = {n: 0 for n in nodes}
    dependents = {n: [] for n in nodes}
    for node, ds in deps.items():
        seen = set()
        for d in ds:
            if d in seen:
                continue
            seen.add(d)
            indegree[node] += 1
            dependents[d].append(node)
    # TRAP: LIFO stack instead of smallest-first selection.
    stack = sorted(n for n in nodes if indegree[n] == 0)
    order = []
    while stack:
        n = stack.pop()
        order.append(n)
        for m in dependents[n]:
            indegree[m] -= 1
            if indegree[m] == 0:
                stack.append(m)
    if len(order) != len(nodes):
        raise CycleError("dependency cycle detected")
    return order

"""Deterministic topological sort (reference implementation)."""
import heapq


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
    heap = [n for n in nodes if indegree[n] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        n = heapq.heappop(heap)
        order.append(n)
        for m in dependents[n]:
            indegree[m] -= 1
            if indegree[m] == 0:
                heapq.heappush(heap, m)
    if len(order) != len(nodes):
        raise CycleError("dependency cycle detected")
    return order

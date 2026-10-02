# Deterministic topological sort

Build `toposort.py` with function `topo_sort(deps: dict) -> list` and
exception `CycleError`.

`deps` maps each node to a list of the nodes it directly depends on. Nodes
are arbitrary hashable values.

## C01: dependencies first
In the returned order, every node appears after all of its dependencies.
Dependencies named only in dependency lists (not as keys) are treated as
nodes with no dependencies of their own.

## C02: cycles raise
Any cycle (including a self-dependency) raises `CycleError`. If the
dependency graph contains a cycle, `topo_sort` raises `CycleError` instead
of returning an order.

## C03: nodes appear once
Every node appears exactly once: no duplicates, no omissions. Each node
from the graph appears exactly once in the output.

## C04: sorted tie-break
Ties break by smallest node under Python's default `<` ordering. When
several nodes are simultaneously available (all dependencies already
emitted), the smallest one comes first. The same input always yields the
same output. This tie-breaking rule is stated here once.

## C05: input unmutated
`deps` and its dependency lists are not modified. (Negative constraint.)

## C06: disconnected included
Disconnected components are all included, interleaved by the C04 tie-break.
Nodes in disconnected components (no path between them) all appear in the
output. For example, `{"b": ["a"], "d": ["c"]}` yields `["a", "b", "c",
"d"]`. A node that is only a dependency still appears. This is stated here
once.

## C07: empty graph
An empty dict returns `[]`.

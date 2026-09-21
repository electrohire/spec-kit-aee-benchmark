# Plan: deterministic topological sort

1. Collect all nodes: keys of `deps` plus every node named in a dependency
   list (C01, C06). Never mutate `deps` (C05).
2. Kahn's algorithm: indegree counts unique dependency edges (duplicate edges
   listed twice count once); `dependents` maps each node to the nodes that
   depend on it.
3. Worklist is a min-heap of zero-indegree nodes: always emit the smallest
   available node first (C04 deterministic tie-break). Emit, decrement
   dependents, push newly-free nodes.
4. If fewer nodes are emitted than exist, a cycle exists -> CycleError (C02,
   including self-dependencies). Empty input -> `[]` (C07).

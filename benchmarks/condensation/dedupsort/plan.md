# Plan: deduplicated stable sort

1. Single pass over `items` (works for generators; input never mutated, C05).
   For each element `x`: compute `k = key(x)` (or `x`) exactly once (C06),
   then dedup by element equality via a `seen` set: skip if `x in seen`
   (C01, C04: dedup key is the ELEMENT, never `k`).
2. Keep parallel `uniq` and `keys` lists for first occurrences.
3. `order = sorted(range(len(uniq)), key=lambda i: keys[i],
   reverse=reverse)`: `sorted` is stable, so equal keys keep first-occurrence
   order even with `reverse=True` (C02, C03).
4. Return `[uniq[i] for i in order]`; empty input -> `[]` (C07).

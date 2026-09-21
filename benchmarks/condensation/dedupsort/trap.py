"""Attractive trap for dedupsort: dedup by KEY instead of by element.

Fusing dedup and sort around the key looks like a clean optimization, but it
drops unequal elements whose keys collide (violates C04). Passes public
tests, where the key is injective.
"""


def dedup_sort(items, key=None, reverse=False):
    seen_keys = set()
    uniq = []
    for x in items:
        k = key(x) if key is not None else x
        if k in seen_keys:  # TRAP: dedups by key, not by element equality
            continue
        seen_keys.add(k)
        uniq.append((k, x))
    uniq.sort(key=lambda p: p[0], reverse=reverse)
    return [x for _, x in uniq]

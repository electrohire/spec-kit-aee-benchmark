"""Deduplicated stable sort (reference implementation)."""


def dedup_sort(items, key=None, reverse=False):
    seen = set()
    uniq = []
    keys = []
    for x in items:
        k = key(x) if key is not None else x
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
        keys.append(k)
    order = sorted(range(len(uniq)), key=lambda i: keys[i], reverse=reverse)
    return [uniq[i] for i in order]

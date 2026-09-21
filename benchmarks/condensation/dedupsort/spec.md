# Deduplicated stable sort

Build `dedupsort.py` with function
`dedup_sort(items, key=None, reverse=False) -> list`, which removes duplicate
elements and returns them sorted.

`items` is any iterable of hashable elements; `key` is an optional function
applied for comparison (like the `key` argument of `sorted`); `reverse`
reverses the final order.

## C01: equality dedup
Two elements are duplicates when they are equal (`==`). Only the first
occurrence of each equal value is kept. Unhashable elements are not required
to work.

## C02: sort by key
Results sort ascending by `key`, or by the elements themselves. When a key
is given the comparison uses `key(element)`; `reverse=True` reverses the
final order after sorting.

## C03: stable equal keys
Elements whose keys compare equal keep their original relative order
(first occurrence first). Python's `sorted` is stable; use that property.
Stability matters because callers may rely on first-occurrence order when
keys collide.

## C04: equality not key
Duplicates are decided by element equality, never by key equality. Whether
two elements are duplicates is decided by element equality (`==`); two
unequal elements with equal keys are both kept. This distinction is stated
here once.

## C05: input unmutated
The input is consumed at most once and never mutated. `items` may be any
iterable (including a generator); if a list is passed, it must be unchanged
afterwards. The function returns a new list. (Negative constraint.)

## C06: key called once
The key function runs exactly once per input element. Even when the same
value appears many times, a key function with side effects (for example a
counter) must observe one call per element. This is stated here once.

## C07: empty input
Empty input returns `[]`, with any key and any reverse value.

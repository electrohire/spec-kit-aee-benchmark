# Tiny event emitter

Build `eventbus.py` with class `EventBus` and exception `EmitError`.

API: `on(event, handler)`, `once(event, handler)`, `off(event, handler)`,
`emit(event, *args, **kwargs)`. `on` and `once` return the handler passed in.
Events are arbitrary hashable values; handlers are callables.

## C01: registration order
Handlers run in registration order, receiving all emit arguments. `emit`
invokes handlers for the event first-in, first-invoked, passing through all
positional and keyword arguments.

## C02: once fires once
`once` handlers fire on the first emit, then are removed. A handler
registered with `once` is invoked on the first `emit` of its event and then
removed; later emits do not invoke it. Other handlers are unaffected.

## C03: off by reference
`off` removes every registration of the handler, matched by original
reference. This covers registrations via `on` and via `once` (for `once`,
the original handler reference passed to `once` is what `off` accepts).
Removing a handler that is not registered is a no-op, never an error.

## C04: raise does not stop
If a handler raises, the remaining handlers still run. After all handlers
have run, `emit` raises `EmitError`, whose `.errors` attribute is the list of
the raised exception instances in handler invocation order. If no handler
raises, `emit` does not raise. This error-isolation rule is stated here once.

## C05: no silent swallowing
Handler exceptions are never swallowed; they propagate via `EmitError`.
`emit` must not return normally while hiding a handler exception. (Negative
constraint.)

## C06: snapshot iteration
`emit` iterates a snapshot taken when the emit starts. A handler registered
from inside another handler during an emit does not fire in the current emit
(it fires on the next one). Symmetrically, a handler removed during an emit
still fires in the current emit if its turn has not come yet. This snapshot
rule is stated here once.

## C07: return count
`emit` returns the number of handlers actually invoked. Emitting an event
with no handlers returns 0.

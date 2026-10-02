# Plan: tiny event emitter

1. `self._handlers`: dict event -> list of entries. Each entry is
   `(original, invokable)`: for `on` both are the handler; for `once`,
   invokable is a wrapper that removes itself (by identity) before calling
   the original (C02, C03).
2. `on(event, handler)`: append `(handler, handler)`; return handler.
3. `once(event, handler)`: define `wrapper(*a, **k)` that first removes the
   wrapper entry from the live list, then calls `handler`. Append
   `(handler, wrapper)`; return handler (C02, C03: off by original ref).
4. `off(event, handler)`: drop every entry whose original is `handler`;
   missing event/handler is a no-op (C03).
5. `emit(event, *args, **kwargs)`: snapshot = list of current entries (C06).
   For each `(original, invokable)` in the snapshot: try invokable(*args,
   **kwargs); except Exception as e: errors.append(e). Count invocations.
   After the loop, if errors: raise EmitError(errors). Return count (C01,
   C04, C05, C07).
6. `EmitError(Exception)` with `.errors` list, in invocation order (C04).

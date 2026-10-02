"""Attractive trap for eventbus: the naive emit.

1. Iterates the LIVE handler list: a handler registered mid-emit fires in
   the same emit.
2. Lets the first handler exception propagate immediately: later handlers
   never run and no EmitError is raised.
Public tests (no mid-emit registration, no raising handlers) never notice.
"""


class EmitError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(f"{len(self.errors)} handler(s) raised")


class EventBus:
    def __init__(self):
        self._handlers = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append((handler, handler))
        return handler

    def once(self, event, handler):
        def wrapper(*args, **kwargs):
            entries = self._handlers.get(event, [])
            for i, (orig, inv) in enumerate(entries):
                if inv is wrapper:
                    del entries[i]
                    break
            return handler(*args, **kwargs)

        self._handlers.setdefault(event, []).append((handler, wrapper))
        return handler

    def off(self, event, handler):
        entries = self._handlers.get(event)
        if not entries:
            return
        self._handlers[event] = [(o, v) for (o, v) in entries if o is not handler]

    def emit(self, event, *args, **kwargs):
        # TRAP 1: iterate the live list, not a snapshot.
        # TRAP 2: no try/except -- the first exception aborts the emit.
        count = 0
        for _original, invokable in self._handlers.get(event, []):
            count += 1
            invokable(*args, **kwargs)
        return count

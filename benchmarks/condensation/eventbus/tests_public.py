"""Public tests for eventbus: basic happy path only.

No raising handlers, no mid-emit registration: must pass on both reference
and trap.
"""
from eventbus import EventBus


def test_public_on_emit():
    bus = EventBus()
    seen = []
    bus.on("e", lambda x: seen.append(x))
    bus.on("e", lambda x: seen.append(x * 2))
    assert bus.emit("e", 21) == 2
    assert seen == [21, 42]


def test_public_once():
    bus = EventBus()
    seen = []
    bus.once("e", lambda: seen.append(1))
    bus.emit("e")
    bus.emit("e")
    assert seen == [1]


def test_public_off():
    bus = EventBus()
    seen = []
    h = lambda: seen.append(1)  # noqa: E731
    bus.on("e", h)
    bus.off("e", h)
    assert bus.emit("e") == 0
    assert seen == []

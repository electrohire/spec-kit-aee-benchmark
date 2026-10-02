"""Hidden acceptance tests for eventbus. Every test pinned via PINS."""
import pytest
from eventbus import EventBus, EmitError

PINS = {
    "test_c01_registration_order": ["C01"],
    "test_c01_args_passthrough": ["C01"],
    "test_c02_once_fires_once": ["C02"],
    "test_c03_off_removes_on": ["C03"],
    "test_c03_off_removes_once_by_original": ["C03"],
    "test_c03_off_missing_is_noop": ["C03"],
    "test_c04_emit_continues_after_raise": ["C04"],
    "test_c04_emit_error_carries_errors_in_order": ["C04"],
    "test_c04_no_raise_when_clean": ["C04"],
    "test_c05_no_silent_swallow": ["C05"],
    "test_c06_register_during_emit_waits": ["C06"],
    "test_c06_removed_during_emit_still_fires": ["C06"],
    "test_c07_emit_returns_count": ["C07"],
    "test_c07_no_handlers_returns_zero": ["C07"],
}


def test_c01_registration_order():
    bus = EventBus()
    seen = []
    bus.on("e", lambda: seen.append(1))
    bus.on("e", lambda: seen.append(2))
    bus.on("e", lambda: seen.append(3))
    bus.emit("e")
    assert seen == [1, 2, 3]


def test_c01_args_passthrough():
    bus = EventBus()
    seen = []
    bus.on("e", lambda *a, **k: seen.append((a, k)))
    bus.emit("e", 1, 2, x=3)
    assert seen == [((1, 2), {"x": 3})]


def test_c02_once_fires_once():
    bus = EventBus()
    seen = []
    bus.once("e", lambda: seen.append(1))
    bus.on("e", lambda: seen.append(2))
    bus.emit("e")
    bus.emit("e")
    assert seen == [1, 2, 2]


def test_c03_off_removes_on():
    bus = EventBus()
    seen = []
    h = lambda: seen.append(1)  # noqa: E731
    bus.on("e", h)
    bus.off("e", h)
    assert bus.emit("e") == 0
    assert seen == []


def test_c03_off_removes_once_by_original():
    bus = EventBus()
    seen = []
    h = lambda: seen.append(1)  # noqa: E731
    bus.once("e", h)
    bus.off("e", h)  # original reference, not the wrapper
    assert bus.emit("e") == 0
    assert seen == []


def test_c03_off_missing_is_noop():
    bus = EventBus()
    bus.off("nope", lambda: None)
    bus.on("e", lambda: None)
    bus.off("e", lambda: None)  # different function object
    assert bus.emit("e") == 1


def test_c04_emit_continues_after_raise():
    bus = EventBus()
    seen = []

    def bad():
        seen.append("bad")
        raise RuntimeError("boom")

    bus.on("e", bad)
    bus.on("e", lambda: seen.append("good"))
    with pytest.raises(EmitError):
        bus.emit("e")
    assert seen == ["bad", "good"]


def test_c04_emit_error_carries_errors_in_order():
    bus = EventBus()
    e1, e2 = RuntimeError("one"), ValueError("two")
    bus.on("e", lambda: (_ for _ in ()).throw(e1))
    bus.on("e", lambda: (_ for _ in ()).throw(e2))
    with pytest.raises(EmitError) as ei:
        bus.emit("e")
    assert ei.value.errors == [e1, e2]


def test_c04_no_raise_when_clean():
    bus = EventBus()
    bus.on("e", lambda: None)
    assert bus.emit("e") == 1  # no raise


def test_c05_no_silent_swallow():
    bus = EventBus()

    def bad():
        raise RuntimeError("boom")

    bus.on("e", bad)
    with pytest.raises(EmitError) as ei:
        bus.emit("e")
    assert isinstance(ei.value.errors[0], RuntimeError)


def test_c06_register_during_emit_waits():
    bus = EventBus()
    seen = []
    fired = []

    def registrar():
        seen.append("registrar")
        bus.on("e", lambda: fired.append("late"))

    bus.on("e", registrar)
    assert bus.emit("e") == 1  # late handler not fired in this emit
    assert fired == []
    assert bus.emit("e") == 2  # fires on the next emit
    assert fired == ["late"]


def test_c06_removed_during_emit_still_fires():
    bus = EventBus()
    seen = []
    second = lambda: seen.append("second")  # noqa: E731

    def remover():
        seen.append("remover")
        bus.off("e", second)

    bus.on("e", remover)
    bus.on("e", second)
    bus.emit("e")
    # Snapshot semantics: `second` was registered at emit start, so it fires
    # even though `remover` unregistered it mid-emit.
    assert seen == ["remover", "second"]


def test_c07_emit_returns_count():
    bus = EventBus()
    bus.on("e", lambda: None)
    bus.on("e", lambda: None)
    assert bus.emit("e") == 2


def test_c07_no_handlers_returns_zero():
    bus = EventBus()
    assert bus.emit("never") == 0

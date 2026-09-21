import pytest

from minisched import JobStore, Scheduler, SchedulerConfig


@pytest.fixture
def sched():
    return Scheduler()


def flaky(failures, result="ok"):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= failures:
            raise RuntimeError("boom")
        return result

    fn.calls = calls
    return fn


def test_public_basic(sched):
    jid = sched.enqueue({"fn": lambda: 42})
    assert jid == 1
    out = sched.run_next()
    assert out["status"] == "done" and out["result"] == 42 and out["id"] == jid
    assert sched.run_next() is None


def test_R01_empty_next(sched):
    assert sched.run_next() is None


def test_R02_fifo_order(sched):
    sched.enqueue({"fn": lambda: "first"})
    sched.enqueue({"fn": lambda: "second"})
    assert sched.run_next()["result"] == "first"
    assert sched.run_next()["result"] == "second"


def test_R02_update_unknown():
    store = JobStore()
    with pytest.raises(KeyError):
        store.update(999, status="done")


def test_R03_bad_payload():
    sched = Scheduler(config=SchedulerConfig(max_retries=2))
    sched.enqueue({"nope": 1})
    out = sched.run_next()
    assert out["status"] == "retried" and out["attempts"] == 1

# STAGE2

def test_public_retry():
    sched = Scheduler(config=SchedulerConfig(max_retries=2))
    sched.enqueue({"fn": flaky(1)})
    out = sched.run_next()
    assert out["status"] == "retried" and out["attempts"] == 1
    out = sched.run_next()
    assert out["status"] == "done" and out["result"] == "ok"


def test_public_store():
    store = JobStore()
    jid = store.add({"a": 1})
    assert jid == 1
    assert store.get(jid)["payload"] == {"a": 1}
    assert len(store.list_pending()) == 1
    assert store.get(999) is None


def test_R04_default_retries(sched):
    fn = flaky(10**9)
    sched.enqueue({"fn": fn})
    statuses = [sched.run_next()["status"] for _ in range(4)]
    assert statuses == ["retried", "retried", "retried", "failed"]
    assert fn.calls["n"] == 4
    assert sched.run_next() is None


def test_R04_explicit_retries():
    sched = Scheduler(config=SchedulerConfig(max_retries=1))
    fn = flaky(10**9)
    sched.enqueue({"fn": fn})
    assert sched.run_next()["status"] == "retried"
    assert sched.run_next()["status"] == "failed"
    assert fn.calls["n"] == 2


def test_R05_add_detached():
    store = JobStore()
    payload = {"x": 1, "nested": [1]}
    jid = store.add(payload)
    payload["x"] = 999
    payload["nested"].append(2)
    assert store.get(jid)["payload"] == {"x": 1, "nested": [1]}


def test_R05_enqueue_detached(sched):
    seen = []
    payload = {"fn": lambda: seen.append("original") or "ran"}
    sched.enqueue(payload)
    payload["fn"] = lambda: seen.append("evil") or "ran"
    out = sched.run_next()
    assert out["status"] == "done" and seen == ["original"]


def test_R05_get_detached():
    store = JobStore()
    jid = store.add({"x": 1})
    record = store.get(jid)
    record["payload"]["x"] = 999
    record["status"] = "done"
    fresh = store.get(jid)
    assert fresh["payload"] == {"x": 1} and fresh["status"] == "pending"


def test_R06_validation():
    with pytest.raises(ValueError):
        SchedulerConfig(max_retries=True)
    with pytest.raises(ValueError):
        SchedulerConfig(max_retries=-1)
    with pytest.raises(ValueError):
        SchedulerConfig(retry_base_seconds=0)
    with pytest.raises(ValueError):
        SchedulerConfig(retry_base_seconds=3601)
    cfg = SchedulerConfig(max_retries=0, retry_base_seconds=3600)
    assert cfg.max_retries == 0 and cfg.retry_base_seconds == 3600

# STAGE3

def test_public_config():
    cfg = SchedulerConfig(max_retries=5, retry_base_seconds=10)
    assert cfg.max_retries == 5 and cfg.retry_base_seconds == 10
    with pytest.raises(ValueError):
        SchedulerConfig(max_retries=-1)
    with pytest.raises(ValueError):
        SchedulerConfig(retry_base_seconds=0)


def test_R07_default_value():
    cfg = SchedulerConfig()
    assert cfg.max_retries == 3
    assert cfg.retry_base_seconds == 1


def test_R07_explicit_zero():
    sched = Scheduler(config=SchedulerConfig(max_retries=0))
    fn = flaky(10**9)
    sched.enqueue({"fn": fn})
    out = sched.run_next()
    assert out["status"] == "failed" and out["attempts"] == 1
    assert fn.calls["n"] == 1


def test_R08_failed_terminal(sched):
    sched.enqueue({"fn": flaky(10**9)})
    for _ in range(4):
        sched.run_next()
    assert sched.store.list_pending() == []
    assert sched.run_next() is None


def test_R08_failed_then_next():
    sched = Scheduler(config=SchedulerConfig(max_retries=1))
    sched.enqueue({"fn": flaky(10**9)})
    sched.enqueue({"fn": lambda: "second"})
    assert sched.run_next()["status"] == "retried"
    assert sched.run_next()["status"] == "failed"
    out = sched.run_next()
    assert out["status"] == "done" and out["result"] == "second"

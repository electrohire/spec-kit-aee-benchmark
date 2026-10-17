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


# CLAIM-A CANDIDATES (feat/claim-a-candidates): hidden tests for new calibration variants.
# New hidden tests for Claim A minisched candidate variants.
# Concatenated after the existing tests.py; may use `sched`, `flaky`, pytest,
# JobStore, Scheduler, SchedulerConfig.


def test_R07_zero_with_bad_payload():
    # max_retries=0 + uncallable payload: immediate 'failed', never raises (R01 x R07).
    s = Scheduler(config=SchedulerConfig(max_retries=0))
    s.enqueue({"nope": 1})
    out = s.run_next()
    assert out["status"] == "failed" and out["attempts"] == 1


def test_R04_attempts_boundary():
    # Spec-literal boundary: 'failed' exactly when attempts > max_retries (R04).
    s = Scheduler(config=SchedulerConfig(max_retries=2))
    fn = flaky(10**9)
    s.enqueue({"fn": fn})
    statuses = [s.run_next()["status"] for _ in range(3)]
    assert statuses == ["retried", "retried", "failed"]
    assert fn.calls["n"] == 3
    assert s.run_next() is None


def test_R08_failed_never_rerun(sched):
    # A terminally failed job must never execute again (R08 x R04).
    fn = flaky(10**9)
    sched.enqueue({"fn": fn})
    for _ in range(4):
        sched.run_next()
    for _ in range(3):
        assert sched.run_next() is None
    assert fn.calls["n"] == 4


def test_R02_fifo_three_jobs(sched):
    sched.enqueue({"fn": lambda: "a"})
    sched.enqueue({"fn": lambda: "b"})
    sched.enqueue({"fn": lambda: "c"})
    assert [sched.run_next()["result"] for _ in range(3)] == ["a", "b", "c"]


def test_R04_retry_budget_boundary(sched):
    # Default config: exactly 4 total executions; the 4th must still be allowed.
    fn = flaky(3)
    sched.enqueue({"fn": fn})
    outs = [sched.run_next() for _ in range(4)]
    assert [o["status"] for o in outs] == ["retried", "retried", "retried", "done"]
    assert outs[-1]["result"] == "ok"
    assert fn.calls["n"] == 4


def test_R05_get_nested_detached():
    # Detachment is deep: nested mutation of a get() result must not leak (R05).
    store = JobStore()
    jid = store.add({"n": {"m": [1]}})
    rec = store.get(jid)
    rec["payload"]["n"]["m"].append(2)
    rec["attempts"] = 99
    fresh = store.get(jid)
    assert fresh["payload"]["n"] == {"m": [1]} and fresh["attempts"] == 0


def test_R04_stored_attempts_persist(sched):
    # The job's stored attempts must actually be persisted across runs (R04).
    sched.enqueue({"fn": flaky(10**9)})
    sched.run_next()
    sched.run_next()
    assert sched.store.get(1)["attempts"] == 2


def test_R04_reported_attempts_monotonic(sched):
    # Reported attempts must track the persisted count, not reset (R04).
    sched.enqueue({"fn": flaky(10**9)})
    outs = [sched.run_next()["attempts"] for _ in range(2)]
    assert outs == [1, 2]


def test_R04_high_retries_respected():
    # Config is honored upward too: max_retries=5 means 6 total executions (R04).
    s = Scheduler(config=SchedulerConfig(max_retries=5))
    fn = flaky(10**9)
    s.enqueue({"fn": fn})
    statuses = [s.run_next()["status"] for _ in range(6)]
    assert statuses == ["retried"] * 5 + ["failed"]
    assert fn.calls["n"] == 6


def test_R02_fifo_retry_keeps_order():
    # A retried job keeps its FIFO position; it must not jump the queue (R02 x R04).
    s = Scheduler(config=SchedulerConfig(max_retries=2))
    s.enqueue({"fn": flaky(1, result="first-ok")})
    s.enqueue({"fn": lambda: "second"})
    assert s.run_next()["status"] == "retried"
    out = s.run_next()
    assert out["status"] == "done" and out["result"] == "first-ok"


def test_R02_store_update_preserves_order():
    # JobStore.update must not disturb relative job order (R02; direct store use, R03).
    store = JobStore()
    a = store.add({"fn": lambda: "a"})
    b = store.add({"fn": lambda: "b"})
    c = store.add({"fn": lambda: "c"})
    store.update(b, attempts=1)
    assert [r["id"] for r in store.list_pending()] == [a, b, c]


def test_R08_failed_status_stored(sched):
    # The stored record of a terminally failed job carries status 'failed' (R04/R08).
    sched.enqueue({"fn": flaky(10**9)})
    for _ in range(4):
        sched.run_next()
    rec = sched.store.get(1)
    assert rec["status"] == "failed" and rec["attempts"] == 4


def test_R08_terminal_statuses_exact(sched):
    ok_id = sched.enqueue({"fn": lambda: "done-ok"})
    fail_id = sched.enqueue({"fn": flaky(10**9)})
    sched.run_next()
    for _ in range(4):
        sched.run_next()
    statuses = {sched.store.get(ok_id)["status"], sched.store.get(fail_id)["status"]}
    assert statuses == {"done", "failed"}


def test_R05_add_deep_nested_detached():
    # add() detachment is deep: nested caller-side mutation must not leak (R05).
    store = JobStore()
    payload = {"a": {"b": [1]}}
    jid = store.add(payload)
    payload["a"]["b"].append(2)
    assert store.get(jid)["payload"] == {"a": {"b": [1]}}


def test_R05_enqueue_nested_detached(sched):
    # Same via the scheduler path: nested meta must be detached at enqueue (R05).
    payload = {"fn": lambda: "ok", "meta": {"tags": ["x"]}}
    sched.enqueue(payload)
    payload["meta"]["tags"].append("evil")
    out = sched.run_next()
    assert out["status"] == "done" and out["result"] == "ok"
    assert sched.store.get(1)["payload"]["meta"] == {"tags": ["x"]}


def test_R01_bad_payload_enqueue_no_raise(sched):
    # enqueue must never raise for a bad payload; it becomes a job failure (R01).
    jid = sched.enqueue({"nope": 1})
    assert isinstance(jid, int) and jid > 0
    out = sched.run_next()
    assert out["status"] in ("retried", "failed")


def test_R01_nondict_payload_is_job_failure(sched):
    # A non-dict payload is a job failure under the retry rule, not a caller error.
    sched.enqueue("not-a-dict")
    out = sched.run_next()
    assert out["status"] == "retried" and out["attempts"] == 1


# CLAIM-A CANDIDATES, round 2 (2026-09-22): hidden tests for harder variants.

def test_R04_config_change_honored():
    # R04 clarification: the retry decision reads the LIVE config object on
    # each run_next -- a Scheduler must not snapshot max_retries at
    # construction. Post-construction config changes are honored.
    s = Scheduler()
    s.config.max_retries = 0
    s.enqueue({"fn": flaky(10**9)})
    out = s.run_next()
    assert out["status"] == "failed" and out["attempts"] == 1
    assert s.store.get(1)["status"] == "failed"


def test_R04_config_replaced():
    # Same via wholesale config replacement (R04 clarification).
    s = Scheduler()
    s.config = SchedulerConfig(max_retries=1)
    s.enqueue({"fn": flaky(10**9)})
    assert s.run_next()["status"] == "retried"
    assert s.run_next()["status"] == "failed"


def test_R08_done_token_stored_exact(sched):
    # R08 clarification: the status string stored on the job record when it
    # completes is exactly "done" -- the same token R08 keys terminality off.
    sched.enqueue({"fn": lambda: "ok"})
    sched.run_next()
    assert sched.store.get(1)["status"] == "done"


def test_R05_list_pending_detached():
    # R05 extension: records returned by list_pending are detached copies;
    # mutating a listed record (including nested payload) must not corrupt
    # the store.
    store = JobStore()
    jid = store.add({"n": [1]})
    recs = store.list_pending()
    recs[0]["status"] = "done"
    recs[0]["payload"]["n"].append(2)
    assert len(store.list_pending()) == 1
    assert store.get(jid)["payload"] == {"n": [1]}
    assert store.get(jid)["status"] == "pending"

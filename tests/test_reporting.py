from benchmark_runner.reporting import aggregate, article_table
from benchmark_runner.store import Store


def fixture(store, arm, task, repeat, resolved, cost="1", outcome=None):
    id = f"{task}-{arm}-{repeat}"
    store.append("attempts", dict(attempt_id=id, task_id=task, repeat=repeat, arm=arm,
                                 status="completed", duration_seconds=2, assessment_outcome=outcome))
    store.append("calls", dict(attempt_id=id, call_id=id, request_id=id, cost=cost,
                               input_tokens=100, cached_input_tokens=20, output_tokens=30, reasoning_tokens=10))
    store.append("grades", dict(attempt_id=id, resolved=resolved))


def test_all_attempt_cost_zero_success_and_disagreement(tmp_path):
    store = Store(tmp_path)
    for repeat in range(1, 4):
        fixture(store, "baseline", "task", repeat, False)
        fixture(store, "spec_kit", "task", repeat, True)
        fixture(store, "spec_kit_aee", "task", repeat, repeat == 1, outcome="pass")
    report = aggregate(store, synthetic=True)
    assert report["status"] == "synthetic_fixture"
    baseline = report["arms"]["baseline"]
    assert baseline["total_cost"] == 3 and baseline["cost_per_resolved"] is None
    aee = report["arms"]["spec_kit_aee"]
    assert aee["cost_per_resolved"] == 3 and aee["false_acceptances"] == 2
    uncertainty = report["comparisons"]["spec_kit_aee_vs_baseline"]["task_cluster_bootstrap"]
    assert uncertainty["paired_tasks"] == 1  # repetitions are not three independent tasks
    assert "synthetic_fixture" in article_table(report)


def test_unknown_cost_and_not_run(tmp_path):
    store = Store(tmp_path)
    assert aggregate(store)["status"] == "not_run"
    fixture(store, "baseline", "task", 1, True, cost=None)
    report = aggregate(store, synthetic=True)
    assert report["arms"]["baseline"]["total_cost"] is None
    assert report["arms"]["baseline"]["cost_per_resolved"] is None


def test_crash_after_reservation_is_not_free(tmp_path):
    store = Store(tmp_path)
    store.append("attempts", dict(attempt_id="a", task_id="t", repeat=1, arm="baseline", status="infrastructure_failure"))
    store.append("budget", dict(call_id="c", attempt_id="a", status="reserved", amount="1"))
    report = aggregate(store, synthetic=True)
    assert report["arms"]["baseline"]["total_cost"] is None
    assert report["arms"]["baseline"]["tokens"]["input_tokens"] is None

"""Amendment 1 R-A2: campaign setup as a measured reporting line.

Synthetic stores only: events are appended through Store.append so the
hash chains are real, and freeze.json is a minimal manifest carrying
the reservation config (max_input_tokens + max_output_tokens) and an
empty schedule.
"""
import json

from benchmark_runner.reporting import aggregate, arm_token_totals, campaign_setup_line
from benchmark_runner.store import Store

RESERVATION = 1000 + 500  # freeze config below: max_input + max_output


def make_store(tmp_path, *, freeze=True):
    store = Store(tmp_path)
    if freeze:
        (tmp_path / "freeze.json").write_text(json.dumps(
            {"config": {"max_input_tokens": 1000, "max_output_tokens": 500},
             "schedule": []}))
    return store


def call(store, call_id, *, task_id="task-1", arm="spec_kit", phase="constitution",
         purpose="campaign_setup", input_tokens=100, output_tokens=10,
         attempt_id=None):
    store.append("calls", dict(
        call_id=call_id, request_id=call_id, attempt_id=attempt_id or f"setup-{call_id}",
        task_id=task_id, arm=arm, phase=phase, purpose=purpose,
        input_tokens=input_tokens, cached_input_tokens=0,
        output_tokens=output_tokens, reasoning_tokens=0,
        unknown_reason=None if input_tokens is not None and output_tokens is not None
        else "provider omitted usage"))


def scored_attempt(store, attempt_id, *, task_id="task-1", arm="baseline",
                   phase="solve", input_tokens=100, output_tokens=30):
    store.append("attempts", dict(attempt_id=attempt_id, task_id=task_id, repeat=1,
                                  arm=arm, status="completed", duration_seconds=2,
                                  assessment_outcome=None))
    store.append("calls", dict(
        call_id=attempt_id, request_id=attempt_id, attempt_id=attempt_id,
        task_id=task_id, arm=arm, phase=phase, purpose="scored_comparison",
        cost="1", input_tokens=input_tokens, cached_input_tokens=0,
        output_tokens=output_tokens, reasoning_tokens=0, unknown_reason=None))
    log = store.artifact(f"SYNTHETIC GRADER LOG {attempt_id}".encode())
    store.append("grades", dict(attempt_id=attempt_id, task_id=task_id,
                                run_id=f"bench-{attempt_id}", resolved=True,
                                reason=None, grader_exit_code=0, log=log, reports=[]))


def test_setup_line_on_empty_store_is_zeros_not_an_error(tmp_path):
    store = make_store(tmp_path, freeze=False)
    assert campaign_setup_line(store) == {
        "tokens": 0, "calls": 0, "per_task": {}, "construction_records": 0}


def test_setup_line_sums_known_usage_construction_calls_per_task(tmp_path):
    store = make_store(tmp_path)
    call(store, "c1", task_id="task-1", input_tokens=100, output_tokens=10)
    call(store, "c2", task_id="task-1", input_tokens=200, output_tokens=20)
    call(store, "c3", task_id="task-2", input_tokens=50, output_tokens=5)
    # A scored call is never part of the setup line.
    call(store, "c4", task_id="task-1", purpose="scored_comparison",
         input_tokens=999, output_tokens=999)
    store.append("campaign_setups", dict(setup_key="task-1", attempt_id="setup-c1"))
    store.append("campaign_setups", dict(setup_key="task-2", attempt_id="setup-c3"))

    line = campaign_setup_line(store)
    assert line["tokens"] == 330 + 55
    assert line["calls"] == 3
    assert line["per_task"] == {"task-1": 330, "task-2": 55}
    assert line["construction_records"] == 2


def test_setup_line_unknown_usage_charged_at_reservation(tmp_path):
    store = make_store(tmp_path)
    call(store, "c1", task_id="task-1", input_tokens=None, output_tokens=None)
    call(store, "c2", task_id="task-1", input_tokens=100, output_tokens=10)

    line = campaign_setup_line(store)
    assert line["tokens"] == RESERVATION + 110
    assert line["per_task"] == {"task-1": RESERVATION + 110}
    assert line["calls"] == 2


def test_setup_line_unknown_usage_without_freeze_config_is_none(tmp_path):
    store = make_store(tmp_path, freeze=False)
    call(store, "c1", task_id="task-1", input_tokens=None, output_tokens=None)

    line = campaign_setup_line(store)
    assert line["tokens"] is None
    assert line["per_task"] == {"task-1": None}
    assert line["calls"] == 1


def test_setup_share_adds_same_per_task_amount_to_both_spec_kit_arms(tmp_path):
    store = make_store(tmp_path)
    # Scored calls, one per arm.
    call(store, "s1", task_id="task-1", arm="baseline", phase="solve",
         purpose="scored_comparison", input_tokens=100, output_tokens=50)
    call(store, "s2", task_id="task-1", arm="spec_kit", phase="implement",
         purpose="scored_comparison", input_tokens=200, output_tokens=50)
    call(store, "s3", task_id="task-1", arm="spec_kit_aee", phase="implement",
         purpose="scored_comparison", input_tokens=300, output_tokens=50)
    # Construction: 500 for task-1 and 700 for task-2, charged once per task.
    call(store, "c1", task_id="task-1", input_tokens=400, output_tokens=100)
    call(store, "c2", task_id="task-2", input_tokens=600, output_tokens=100)

    plain = arm_token_totals(store)
    assert plain == {"arms": {"baseline": 150, "spec_kit": 250, "spec_kit_aee": 350},
                     "setup_applied": False, "setup_tokens": 1200}

    shared = arm_token_totals(store, setup_share=True)
    assert shared["setup_applied"] is True
    assert shared["setup_tokens"] == 1200
    assert shared["arms"]["baseline"] == 150  # baseline untouched
    assert shared["arms"]["spec_kit"] == 250 + 1200
    assert shared["arms"]["spec_kit_aee"] == 350 + 1200


def test_aggregate_without_construction_keeps_setup_cost_none(tmp_path):
    store = make_store(tmp_path)
    scored_attempt(store, "task-1--baseline--r1")

    report = aggregate(store, synthetic=True)
    assert report["setup_cost"] is None
    assert report["setup_cost_reason"] == (
        "controller session usage and human time not attributable")
    assert report["campaign_setup"] == {
        "tokens": 0, "calls": 0, "per_task": {}, "construction_records": 0}
    assert report["amortized_cost"] is None


def test_aggregate_with_construction_emits_measured_setup_line(tmp_path):
    store = make_store(tmp_path)
    scored_attempt(store, "task-1--baseline--r1", input_tokens=100, output_tokens=30)
    # Construction calls: 500 on the constitution phase, plus 250 whose
    # phase says specification -- purpose wins, so it counts to setup
    # exactly once and never to specification (no double count).
    call(store, "c1", task_id="task-1", phase="constitution",
         input_tokens=400, output_tokens=100)
    call(store, "c2", task_id="task-1", phase="specify",
         input_tokens=200, output_tokens=50)
    store.append("campaign_setups", dict(setup_key="task-1", attempt_id="setup-c1"))

    report = aggregate(store, synthetic=True)
    assert report["setup_cost"] == 750
    assert report["setup_cost_reason"] == (
        "campaign construction tokens charged to the setup line "
        "(calls with purpose campaign_setup); controller session usage "
        "and human time excluded")
    assert report["campaign_setup"]["tokens"] == 750
    assert report["campaign_setup"]["calls"] == 2
    assert report["campaign_setup"]["per_task"] == {"task-1": 750}
    assert report["campaign_setup"]["construction_records"] == 1

    categories = report["category_tokens"]
    assert categories["setup"] == 750  # == the construction total
    assert categories["implementation"] == 130  # the scored solve call
    assert categories["specification"] == 0
    # Every call counted exactly once across the categories.
    assert sum(v for v in categories.values() if v is not None) == 750 + 130


def test_scored_constitution_phase_call_categorizes_to_setup(tmp_path):
    store = make_store(tmp_path)
    scored_attempt(store, "task-1--spec_kit--r1", arm="spec_kit",
                   phase="constitution", input_tokens=80, output_tokens=20)

    report = aggregate(store, synthetic=True)
    assert report["category_tokens"]["setup"] == 100
    # It is scored work, not construction: the setup line stays empty.
    assert report["setup_cost"] is None
    assert report["campaign_setup"]["calls"] == 0

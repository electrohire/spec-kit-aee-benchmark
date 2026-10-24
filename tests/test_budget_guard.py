"""Budget guard: cumulative caps across run stores (Amendment 1).

Stores are synthetic directories in tmp_path with hand-written
calls.jsonl + freeze.json. Charging must match
benchmark_runner.accounting.attempt_token_usage exactly: known usage
charges input + output; a call with either side unknown charges that
store's full reservation, cfg max_input_tokens + max_output_tokens.
"""
import json

from benchmark_runner.budget_guard import BudgetGuard, charged_tokens, load_store, main


def _call(input_tokens, output_tokens):
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _write_store(root, calls, cfg):
    root.mkdir(parents=True, exist_ok=True)
    (root / "calls.jsonl").write_text(
        "".join(json.dumps(call) + "\n" for call in calls), encoding="utf-8")
    (root / "freeze.json").write_text(
        json.dumps({"config": cfg}), encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# charged_tokens / load_store


def test_known_usage_sums_input_plus_output():
    cfg = {"max_input_tokens": 1000, "max_output_tokens": 100}
    calls = [_call(100, 30), _call(50, 0), _call(7, 3)]
    assert charged_tokens(calls, cfg) == 130 + 50 + 10


def test_unknown_usage_charged_at_full_reservation():
    cfg = {"max_input_tokens": 1000, "max_output_tokens": 100}
    # Either side unknown (a failed physical request) -> full reservation.
    calls = [_call(100, 30), _call(None, None), _call(None, 5), _call(5, None)]
    assert charged_tokens(calls, cfg) == 130 + 1100 + 1100 + 1100


def test_load_store_reads_calls_and_freeze_config(tmp_path):
    cfg = {"max_input_tokens": 10, "max_output_tokens": 2, "purpose": "x"}
    store = _write_store(tmp_path / "s", [_call(1, 2)], cfg)
    calls, loaded_cfg = load_store(store)
    assert calls == [_call(1, 2)]
    assert loaded_cfg == cfg


def test_load_store_missing_files(tmp_path):
    calls, cfg = load_store(tmp_path / "does-not-exist")
    assert calls == []
    assert cfg == {}


# ---------------------------------------------------------------------------
# Per-store reservations and the cumulative program total


def test_each_store_charged_at_its_own_reservation(tmp_path):
    # Same unknown-usage call in both stores, different freezes: the
    # stage store's reservation is 32768 + 4096, the prior store's 1100.
    stage = _write_store(tmp_path / "stage", [_call(None, None), _call(100, 30)],
                         {"max_input_tokens": 32768, "max_output_tokens": 4096})
    prior = _write_store(tmp_path / "prior", [_call(None, None), _call(100, 30)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    guard = BudgetGuard(stage, prior_stores=[prior])
    assert guard.stage_tokens() == 36864 + 130
    assert guard.prior_tokens() == 1100 + 130


def test_program_total_is_prior_plus_stage(tmp_path):
    stage = _write_store(tmp_path / "stage", [_call(100, 30)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    prior_a = _write_store(tmp_path / "prior-a", [_call(50, 10)],
                           {"max_input_tokens": 1000, "max_output_tokens": 100})
    prior_b = _write_store(tmp_path / "prior-b", [_call(1, 2)],
                           {"max_input_tokens": 1000, "max_output_tokens": 100})
    guard = BudgetGuard(stage, prior_stores=[prior_a, prior_b])
    verdict = guard.verdict()
    assert verdict["stage_tokens"] == 130
    assert verdict["prior_tokens"] == 60 + 3
    assert verdict["program_tokens"] == 130 + 63
    assert verdict["program_tokens"] == verdict["prior_tokens"] + verdict["stage_tokens"]


# ---------------------------------------------------------------------------
# Verdict cap edges


def _guard_at(tmp_path, stage_total, stage_cap=None, program_cap=None):
    store = _write_store(tmp_path / "stage", [_call(stage_total, 0)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    return BudgetGuard(store, stage_cap=stage_cap, program_cap=program_cap)


def test_verdict_exactly_at_cap_is_reached(tmp_path):
    verdict = _guard_at(tmp_path, 1000, stage_cap=1000, program_cap=1000).verdict()
    assert verdict["stage_cap_reached"] is True
    assert verdict["program_cap_reached"] is True


def test_verdict_one_below_cap_is_not_reached(tmp_path):
    verdict = _guard_at(tmp_path, 999, stage_cap=1000, program_cap=1000).verdict()
    assert verdict["stage_cap_reached"] is False
    assert verdict["program_cap_reached"] is False


def test_verdict_no_cap_is_never_reached(tmp_path):
    verdict = _guard_at(tmp_path, 10**9).verdict()
    assert verdict["stage_cap"] is None and verdict["program_cap"] is None
    assert verdict["stage_cap_reached"] is False
    assert verdict["program_cap_reached"] is False


def test_verdict_program_cap_counts_prior_stores(tmp_path):
    # Stage alone is under the program cap; prior + stage reaches it.
    stage = _write_store(tmp_path / "stage", [_call(400, 0)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    prior = _write_store(tmp_path / "prior", [_call(600, 0)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    verdict = BudgetGuard(stage, prior_stores=[prior], program_cap=1000).verdict()
    assert verdict["stage_cap_reached"] is False  # no stage cap set
    assert verdict["program_cap_reached"] is True


def test_verdict_reads_stores_fresh_on_every_call(tmp_path):
    store = _write_store(tmp_path / "stage", [_call(100, 0)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    guard = BudgetGuard(store, stage_cap=150)
    assert guard.verdict()["stage_cap_reached"] is False
    # The watcher polls a live store: a call appended after construction
    # must show up in the next verdict without rebuilding the guard.
    with (store / "calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(_call(50, 0)) + "\n")
    verdict = guard.verdict()
    assert verdict["stage_tokens"] == 150
    assert verdict["stage_cap_reached"] is True


# ---------------------------------------------------------------------------
# Empty / missing stores


def test_empty_and_missing_stores_are_zero(tmp_path):
    empty = _write_store(tmp_path / "empty", [],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    guard = BudgetGuard(empty, prior_stores=[tmp_path / "missing"],
                        stage_cap=1, program_cap=1)
    assert guard.stage_tokens() == 0
    assert guard.prior_tokens() == 0
    assert guard.program_tokens() == 0
    verdict = guard.verdict()
    assert verdict["stage_cap_reached"] is False
    assert verdict["program_cap_reached"] is False


# ---------------------------------------------------------------------------
# Stage 1 figure pin


def test_stage1_style_store_hand_computed_total(tmp_path):
    # Hand-computed pin, in the shape of the closed Stage 1 store:
    # the freeze reservation is max_input_tokens + max_output_tokens
    # = 28672 + 4096 = 32768, charged in full for the one call whose
    # usage is unknown.
    #
    #   known call 1:  1,200,000 input + 300,000 output = 1,500,000
    #   known call 2:    450,000 input +  50,000 output =   500,000
    #   unknown call:  reservation                       =    32,768
    #   known call 3:      9,000 input +   1,232 output =    10,232
    #   total                                            = 2,043,000
    cfg = {"max_input_tokens": 28672, "max_output_tokens": 4096}
    assert cfg["max_input_tokens"] + cfg["max_output_tokens"] == 32768
    calls = [
        _call(1_200_000, 300_000),
        _call(450_000, 50_000),
        _call(None, None),
        _call(9_000, 1_232),
    ]
    store = _write_store(tmp_path / "stage1", calls, cfg)
    loaded_calls, loaded_cfg = load_store(store)
    assert charged_tokens(loaded_calls, loaded_cfg) == 2_043_000
    assert BudgetGuard(store).stage_tokens() == 2_043_000


# ---------------------------------------------------------------------------
# CLI


def test_cli_prints_verdict_json_and_exits_zero_at_cap(tmp_path, capsys):
    stage = _write_store(tmp_path / "stage", [_call(100, 30)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    prior = _write_store(tmp_path / "prior", [_call(50, 10)],
                         {"max_input_tokens": 1000, "max_output_tokens": 100})
    rc = main([str(stage), str(prior), "--stage-cap", "130", "--program-cap", "1000"])
    assert rc == 0  # a reached stage cap does not change the exit code
    verdict = json.loads(capsys.readouterr().out)
    assert verdict == {
        "prior_tokens": 60,
        "program_cap": 1000,
        "program_cap_reached": False,
        "program_tokens": 190,
        "stage_cap": 130,
        "stage_cap_reached": True,
        "stage_tokens": 130,
    }

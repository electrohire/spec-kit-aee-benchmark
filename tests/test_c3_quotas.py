"""Claim C-3 as amended 2026-10-26: the quota policy splits the
construction cap by completion mode.

The original claim's single 720,000 construction cap failed its
Phase 2 test as written: the recorded pydantic construction
completed through installments of 890,588 + 663,076, and the
successful 890,588 installment exceeds the single-draw cap. The
amended policy (AMENDMENT-C3-RECORD, 2026-10-26) caps single-draw
construction totals at 720,000, caps each installment at 910,000
with no cap on the summed total, keeps the drafting quotas the
Phase 2 derivation produced, and leaves the tasks class UNPRICED —
zero observed successes, no number invented.

This test pins the policy itself. The full-record layer of the
amended claim's frozen test — the complete phase-draw record
rebuilt from every campaign store — runs offline on the recorded
stores and is reported in the amendment record.
"""
import pytest

from benchmark_runner.quotas import (
    CAPS,
    INSTALLMENT,
    SINGLE_DRAW,
    Draw,
    evaluate_draws,
    mechanical_quota,
    quota_for,
)

# The recorded maxima of the frozen phase-draw record (Phase 2
# record) and the cap each derives by the mechanical rule.
RECORDED_MAXIMA = [
    (705_441, 720_000),    # construction, single-draw success
    (890_588, 910_000),    # construction, largest successful installment
    (968_355, 990_000),    # specify
    (1_181_872, 1_210_000),  # plan
    (365_025, 380_000),    # implement
    (977_092, 1_000_000),  # solve
]


@pytest.mark.parametrize("largest,expected", RECORDED_MAXIMA)
def test_mechanical_rule_reproduces_every_cap(largest, expected):
    assert mechanical_quota(largest) == expected


def test_cap_table_is_exactly_the_amended_claim():
    assert CAPS == {
        ("construction", SINGLE_DRAW): 720_000,
        ("construction", INSTALLMENT): 910_000,
        ("constitution", SINGLE_DRAW): 720_000,
        ("specify", SINGLE_DRAW): 990_000,
        ("plan", SINGLE_DRAW): 1_210_000,
        ("implement", SINGLE_DRAW): 380_000,
        ("solve", SINGLE_DRAW): 1_000_000,
    }
    for (phase_class, mode), cap in CAPS.items():
        assert quota_for(phase_class, mode) == cap


def test_tasks_class_is_unpriced_and_policy_abstains():
    assert quota_for("tasks") is None
    assert quota_for("tasks", INSTALLMENT) is None
    # Any class or mode the table does not name is likewise unpriced.
    assert quota_for("converge") is None
    assert quota_for("specify", INSTALLMENT) is None


def test_the_original_claims_falsifier_passes_under_the_split():
    # The pydantic banked construction: installments 890,588 +
    # 663,076 = 1,553,664, a success. The single-draw cap would
    # have cut its first installment; the installment cap does not,
    # and the summed total is never capped.
    draw = Draw("construction", 1_553_664, True, (890_588, 663_076))
    assert draw.mode == INSTALLMENT
    result = evaluate_draws([draw])
    assert result.truncated_successes == 0
    assert result.freed_tokens == 0


def test_single_draw_construction_successes_and_freeing():
    draws = [
        # Observed single-draw completions, all under the cap.
        Draw("construction", 507_754, True),
        Draw("construction", 695_742, True),
        Draw("construction", 705_441, True),
        # Censored failures: each frees (draw - 720,000).
        Draw("construction", 867_939, False),
        Draw("construction", 887_733, False),
    ]
    result = evaluate_draws(draws)
    assert result.truncated_successes == 0
    assert result.freed_tokens == (867_939 - 720_000) + (887_733 - 720_000)


def test_installment_above_its_cap_would_truncate_a_success():
    # The falsifier still has teeth in installment mode: an
    # installment beyond 910,000 cuts the success it belongs to.
    draw = Draw("construction", 1_600_000, True, (950_000, 650_000))
    result = evaluate_draws([draw])
    assert result.truncated_successes == 1


def test_miniature_record_evaluates_clean_with_tasks_abstaining():
    draws = [
        Draw("construction", 705_441, True),
        Draw("construction", 1_553_664, True, (890_588, 663_076)),
        Draw("constitution", 695_742, True),
        Draw("specify", 968_355, True),
        Draw("plan", 1_181_872, True),
        Draw("implement", 365_025, True),
        Draw("solve", 977_092, True),
        Draw("solve", 1_100_000, False),  # frees 100,000
        # Tasks draws exist (all failures in the record) but the
        # class is unpriced: never capped, never freed, abstained.
        Draw("tasks", 2_500_000, False),
    ]
    result = evaluate_draws(draws)
    assert result.truncated_successes == 0
    assert result.freed_tokens == 100_000
    assert result.abstained_draws == 1
    assert result.capped_draws == len(draws) - 1

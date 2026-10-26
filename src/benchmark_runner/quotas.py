"""Per-phase token quota policy (claim C-3, as amended 2026-10-26).

Quotas are budget machinery: caps derived mechanically from the
frozen phase-draw record, evaluated offline and at registration.
The original claim priced constitution construction with a single
720,000 cap; its Phase 2 test failed as written because one
recorded construction completed through installments of 890,588 +
663,076, and the successful 890,588 installment draw exceeds the
single-draw cap. The amended policy (amendment record
AMENDMENT-C3-RECORD, 2026-10-26) splits the construction cap by
completion mode — a recorded fact: each campaign setup record
carries its installments list, one entry for a single-draw
completion, two or more for an installment completion.

Every value below comes from the mechanical rule in the Phase 2
record — largest observed successful draw x 1.02, rounded up to
the next 10,000 — applied to the frozen record:

* construction, single-draw total: 705,441 -> 720,000 (the same cap
  governs the constitution phase class, the same work priced
  inside a workflow attempt; largest observed success 695,742)
* construction, per installment: 890,588 -> 910,000 (no cap on the
  summed installment total; the sum is what banking exists to pay)
* specify: 968,355 -> 990,000
* plan: 1,181,872 -> 1,210,000
* implement: 365,025 -> 380,000
* solve: 977,092 -> 1,000,000

The tasks class has zero observed successes in the frozen record,
so it is UNPRICED: this module returns no cap for it, and no cap
may be quoted or enforced for it. The same abstention applies to
any class or mode the table does not name — a cap is never
invented. This mirrors the abstain-by-default rule for unmeasured
classes established under claim C-4.
"""
import math
from dataclasses import dataclass

#: Mode of a construction draw, from its setup record's
#: installments list: exactly one installment (or none recorded)
#: is a single-draw completion; two or more is installment mode.
SINGLE_DRAW = "single_draw"
INSTALLMENT = "installment"

#: Caps keyed by (phase class, mode). A missing key means UNPRICED:
#: the class/mode has no observed successful draw to derive from,
#: and the policy abstains.
CAPS = {
    ("construction", SINGLE_DRAW): 720_000,
    ("construction", INSTALLMENT): 910_000,
    ("constitution", SINGLE_DRAW): 720_000,
    ("specify", SINGLE_DRAW): 990_000,
    ("plan", SINGLE_DRAW): 1_210_000,
    ("implement", SINGLE_DRAW): 380_000,
    ("solve", SINGLE_DRAW): 1_000_000,
}

#: Classes whose work is priced per attempt total in the frozen
#: record regardless of how many calls the total accumulated over;
#: their draws carry the SINGLE_DRAW key above (the drafting quotas
#: the original claim derived). Construction is the one class whose
#: mode split is recorded per draw.
DRAFTING_CLASSES = frozenset({"specify", "plan", "implement", "solve"})


def mechanical_quota(largest_successful_draw):
    """The Phase 2 derivation rule: largest observed successful
    draw x 1.02, rounded up to the next 10,000. Reproduces every
    cap in CAPS from its recorded maximum."""
    return math.ceil(largest_successful_draw * 1.02 / 10_000) * 10_000


def quota_for(phase_class, mode=SINGLE_DRAW):
    """The cap for one draw of `phase_class` in `mode`, or None
    when the class/mode is UNPRICED (the policy abstains). For
    construction in INSTALLMENT mode the returned cap applies to
    each installment individually, never to the summed total."""
    return CAPS.get((phase_class, mode))


@dataclass(frozen=True)
class Draw:
    """One phase-class draw from the frozen record: the tokens
    charged to one attempt in one class. `installments` carries a
    construction draw's recorded installment split when the setup
    record has one; empty means the draw stands as recorded."""
    phase_class: str
    tokens: int
    success: bool
    installments: tuple = ()

    @property
    def mode(self):
        if self.phase_class == "construction" and len(self.installments) >= 2:
            return INSTALLMENT
        return SINGLE_DRAW


@dataclass(frozen=True)
class QuotaEvaluation:
    truncated_successes: int
    freed_tokens: int
    capped_draws: int
    abstained_draws: int


def evaluate_draws(draws):
    """Apply the amended caps to a draw record. A successful draw
    is truncated when its cap would have cut it — for an
    installment-mode construction, when any single installment
    exceeds the per-installment cap (the summed total is never
    capped). A failed draw above its cap frees (draw - cap); a
    failed installment-mode construction frees the sum over its
    installments of (installment - cap) for installments above the
    cap. UNPRICED classes are neither truncated nor freed: the
    policy abstains."""
    truncated = 0
    freed = 0
    capped = 0
    abstained = 0
    for draw in draws:
        cap = quota_for(draw.phase_class, draw.mode)
        if cap is None:
            abstained += 1
            continue
        capped += 1
        if draw.mode == INSTALLMENT:
            over = [part - cap for part in draw.installments
                    if part > cap]
            if draw.success:
                if over:
                    truncated += 1
            else:
                freed += sum(over)
        elif draw.tokens > cap:
            if draw.success:
                truncated += 1
            else:
                freed += draw.tokens - cap
    return QuotaEvaluation(truncated, freed, capped, abstained)

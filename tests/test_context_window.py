import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from context_window import select_context


def test_selector_matches_first_fitting_window_across_lengths_and_budgets():
    rng = random.Random(123)
    for size in range(2, 202):
        messages = [{'role':'user', 'content':'x' * rng.randrange(1, 150)} for _ in range(size)]
        total = lambda chosen: 3 + sum(len(m['content']) + 7 for m in chosen)
        candidates = [messages[:2] + messages[2+2*cut:] for cut in range((size-2)//2+1)]
        limit = rng.randrange(total(candidates[-1]), total(messages)+1)
        expected = next(c for c in candidates if total(c) <= limit)
        probes = []
        chosen, count, removed = select_context(messages, lambda c: probes.append(c) or total(c), limit+20, 20)
        assert chosen == expected and count == total(expected)
        assert removed == len(messages)-len(expected)
        assert len(probes) <= 2 + math.ceil(math.log2(max(1, len(candidates))))
        assert len(messages) == size


def test_selector_rejects_fixed_instructions_that_cannot_fit():
    messages = [{'role':'system','content':'too large'}, {'role':'user','content':'requirements'}, {'role':'user','content':'latest'}]
    with pytest.raises(RuntimeError, match='fixed_instructions_exceed_context'):
        select_context(messages, lambda c: 100, 20, 5)

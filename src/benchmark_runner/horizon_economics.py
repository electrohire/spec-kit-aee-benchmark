"""Quality-gated, observed token amortization; no prices or invented payback.

Inputs are measured per-checkpoint calls and independent requirement grades.
Cached input is a subset of prompt tokens. Unknown costs remain lower bounds.
"""
from collections import Counter


def trajectory(checkpoints):
    result, seen, previous_required = [], set(), set()
    totals = Counter()
    phases = Counter()
    for position, checkpoint in enumerate(checkpoints):
        for key in ('required_ids', 'passed_ids'):
            values = checkpoint[key]
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
                raise ValueError('requirement identifiers must be unique nonempty strings')
        required = set(checkpoint['required_ids'])
        passed = set(checkpoint['passed_ids'])
        if checkpoint['index'] != position + 1 or not previous_required <= required or not passed <= required:
            raise ValueError('checkpoint order, retained requirement inventory or independent grades invalid')
        previous_required = required
        for call in checkpoint['new_calls']:
            identity = call['receipt_id']
            if not isinstance(identity, str) or not identity.strip() or not isinstance(call.get('category'), str) or not call['category'].strip():
                raise ValueError('each physical receipt needs an identity and category')
            if identity in seen:
                raise ValueError('physical call duplicated across checkpoints')
            seen.add(identity)
            usage = call.get('usage')
            if usage is None:
                if not call.get('unknown_reason'):
                    raise ValueError('missing usage requires explicit reason')
                totals['unknown_usage_calls'] += 1
                continue
            prompt, completion = usage['prompt_tokens'], usage['completion_tokens']
            cached = usage.get('prompt_tokens_details', {}).get('cached_tokens')
            if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
                raise ValueError('invalid native token counters')
            if cached is not None and (type(cached) is not int or not 0 <= cached <= prompt):
                raise ValueError('cached input is a subset of native prompt tokens')
            if 'total_tokens' in usage and usage['total_tokens'] != prompt + completion:
                raise ValueError('native total contradicts prompt plus completion')
            totals['prompt_tokens'] += prompt
            totals['completion_tokens'] += completion
            totals['cached_tokens'] += cached or 0
            totals['unknown_cached_fields'] += cached is None
            totals['known_tokens'] += prompt + completion
            phases[call['category']] += prompt + completion
        known = not totals['unknown_usage_calls']
        quality_known = checkpoint.get('grade_complete') is True
        unsafe = checkpoint.get('unsafe_claim_count')
        if unsafe is not None and (type(unsafe) is not int or unsafe < 0):
            raise ValueError('invalid independently adjudicated unsafe claim count')
        measured = dict(totals)
        measured.update(known_tokens=totals['known_tokens'], unknown_usage_calls=totals['unknown_usage_calls'])
        result.append(dict(index=checkpoint['index'], required_ids=sorted(required), passed_ids=sorted(passed),
            grade_complete=quality_known, unsafe_claim_count=unsafe, calls=len(seen),
            **measured, usage_complete=known,
            category_tokens=dict(phases),
            tokens_per_verified_requirement=totals['known_tokens'] / len(passed) if passed and known and quality_known else None))
    return result


def compare(control, treatment, sustained_points=2):
    if sustained_points < 2:
        raise ValueError('sustained payoff needs at least two observed checkpoints')
    left, right = trajectory(control), trajectory(treatment)
    if len(left) != len(right):
        raise ValueError('matched checkpoint prefixes required; no extrapolation')
    rows = []
    for a, b in zip(left, right, strict=True):
        if a['required_ids'] != b['required_ids']:
            raise ValueError('arms must face the same active and retained requirements')
        cost_known = a['usage_complete'] and b['usage_complete']
        quality_known = a['grade_complete'] and b['grade_complete'] and a['unsafe_claim_count'] is not None and b['unsafe_claim_count'] is not None
        quality_noninferior = (set(a['passed_ids']) <= set(b['passed_ids']) and b['unsafe_claim_count'] <= a['unsafe_claim_count']) if quality_known else None
        delta = b['known_tokens'] - a['known_tokens'] if cost_known else None
        rows.append(dict(index=a['index'], control=a, treatment=b, extra_tokens=delta,
            quality_noninferior=quality_noninferior,
            verified_work_present=bool(b['passed_ids']),
            pays_back=(delta <= 0 and quality_noninferior and bool(b['passed_ids'])) if cost_known and quality_known else None))
    first = next((r['index'] for r in rows if r['pays_back'] is True), None)
    sustained = next((rows[i]['index'] for i in range(len(rows))
        if len(rows) - i >= sustained_points and all(r['pays_back'] is True for r in rows[i:])), None)
    return dict(checkpoints=rows, first_observed_break_even=first,
        sustained_observed_break_even=sustained, extrapolated_break_even=None,
        boundary='Native tokens only, cached input not added twice. Missing usage/grades/claim adjudication prevents payoff assertions. No API bill, monetary value or human labor saving is inferred.')

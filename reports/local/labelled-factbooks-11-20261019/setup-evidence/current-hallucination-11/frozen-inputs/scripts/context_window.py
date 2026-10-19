"""Select the first fitting legacy two-message cutoff with logarithmic probes.

The pinned Qwen template uses delimited, nonempty message units. Removing an
old unit monotonically reduces its tokenized length; native calibration checks
this premise and equivalence to the previous linear selector before scoring.
"""


def select_context(messages, measure, context, max_output):
    original = [dict(message) for message in messages]
    cache = {}

    def candidate(cut):
        return original[:2] + original[2 + 2 * cut:]

    def count(cut):
        if cut not in cache:
            cache[cut] = measure(candidate(cut))
        return cache[cut]

    limit = context - max_output
    if count(0) <= limit:
        return original, count(0), 0
    high = max(0, (len(original) - 2) // 2)
    if count(high) > limit:
        raise RuntimeError('fixed_instructions_exceed_context')
    low = 0  # Known not to fit; high is known to fit.
    while high - low > 1:
        middle = (low + high) // 2
        if count(middle) <= limit:
            high = middle
        else:
            low = middle
    return candidate(high), count(high), 2 * high

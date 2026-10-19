"""Two fresh synthetic native schema checks, not a retry of a stopped case.

Registered separately as setup: two calls, output caps unchanged, no retries.
This test verifies bounded delivery, never requires a correct factual judgment.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import matched_hallucinations as m


def probe(out, original, binding):
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=m.ROOT).strip():
        raise RuntimeError('native probe requires committed clean source')
    m.current.configure_worker_binding(binding)
    if any(s.get('is_processing') for s in m.current.http('/slots')):
        raise RuntimeError('worker busy; no overlap')
    plan = m.prepare(out, original)
    hashes = m.source_hashes()
    m.write_json(out / 'probe-started.json', dict(at=m.utc(), source_hashes=hashes,
        maximum_calls=2, reserved_tokens=65536, role='separate setup, not scored',
        source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=m.ROOT).decode().strip(),
        binding_sha256=hashlib.sha256(binding.read_bytes()).hexdigest()), exclusive=True)
    provider = m.Provider(out, {**plan, 'maximum_calls': 2})
    tests = [('constitution', m.DOC_SCHEMA, plan['policy_output'],
              'Return a draft source-grounding policy document. Aim for4000characters, but the native schema bound is authoritative.'),
             ('review', m.DECISION_SCHEMA, plan['case_output'],
              'Source: Only the synthetic key cobalt is registered. Candidate: Amber is registered. Return a verdict with rationale, exact source_quotes, uncertainties. Aim for a4000character rationale and200character quotes/uncertainties, but the native schema bounds are authoritative. No human acceptance or external verification.')]
    values = []
    for phase, schema, cap, instruction in tests:
        value, path = provider.call([dict(role='system', content='Return only a JSON object matching the native schema.'),
            dict(role='user', content=instruction)], schema, cap,
            dict(cohort='setup', dataset='native_bounds_probe', arm='baseline', phase=phase))
        values.append(dict(phase=phase, call=path.name,
            document_characters=len(value['document']) if 'document' in value else None,
            rationale_characters=len(value['rationale']) if 'rationale' in value else None))
    if m.source_hashes() != hashes:
        raise RuntimeError('source changed during native probe')
    calls = [m.load(p) for p in sorted((out / 'calls').glob('*.json'))]
    result = dict(passed=True, physical_calls=len(calls), known_native_tokens=sum((c.get('usage') or {}).get('total_tokens', 0) for c in calls),
        usage_unknown=sum(c.get('usage') is None for c in calls), values=values,
        limitation='Synthetic native delivery checks only; not classification accuracy, AEE benefit, hidden grader success or a repeat of failed scored input.')
    m.write_json(out / 'probe-result.json', result, exclusive=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--worker-binding', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.output, args.original, args.worker_binding), indent=2))

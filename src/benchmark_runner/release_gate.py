"""Paired, preregistered release comparison; consumes independently audited data.

This module does not authenticate a report or run a model/grader. A protected
release workflow must resolve evidence from the trusted benchmark repository,
verify its hashes/approval and bind the tested build before using this decision.
"""
import hashlib
import json
import math
import random
import re
from statistics import mean

SCHEMA = 'release-benchmark-evidence-v1'
REQUIRED = {'halueval_accuracy', 'halueval_false_acceptance', 'ragtruth_accuracy',
            'ragtruth_false_acceptance', 'featurebench_correctness', 'swe_evo_retained_correctness',
            'all_call_tokens'}
SHA = re.compile(r'^[0-9a-f]{64}$')


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate(report, policy):
    if type(policy.get('bootstrap_resamples')) is not int or not 200 <= policy['bootstrap_resamples'] <= 50000:
        raise ValueError('invalid registered resampling budget')
    for rule in policy['metrics'].values():
        if rule['direction'] not in ('higher','lower') or rule['scale'] not in ('absolute','relative') or not 0 <= rule['tolerance'] <= rule['gross_loss'] or not math.isfinite(rule['gross_loss']):
            raise ValueError('invalid preregistered margin')
    if report.get('schema') != SCHEMA:
        raise ValueError('unsupported or historical evidence schema')
    if report.get('status') != 'complete' or not report.get('audits') or any(
            report['audits'].get(k) is not True for k in ('inputs', 'source', 'grades', 'ledgers', 'calls', 'upstream_labels')):
        raise ValueError('complete independent audit required')
    if report.get('usage_unknown') != 0 or report.get('ungraded') != 0:
        raise ValueError('unknown usage or ungraded scheduled work blocks release comparison')
    if not SHA.fullmatch(report.get('matched_environment_sha256', '')):
        raise ValueError('missing matched model/task/seed/tool/cap/grader/protocol fingerprint')
    component = report['component']
    if component['repository'] not in policy['repositories'] or not re.fullmatch(r'[0-9a-f]{40}', component['commit']):
        raise ValueError('unsupported repository or unbound commit')
    if not SHA.fullmatch(component['artifact_sha256']):
        raise ValueError('unbound build artifact')
    if set(report['metrics']) != REQUIRED or set(policy['metrics']) != REQUIRED:
        raise ValueError('all registered detector, coding and cost metrics required')
    for name, rows in report['metrics'].items():
        if len(rows) < policy['metrics'][name]['minimum_clusters'] or len({r['cluster'] for r in rows}) != len(rows):
            raise ValueError('insufficient or duplicate independent clusters')
        for row in rows:
            if not isinstance(row['cluster'], str) or not row['cluster'] or not row['values']:
                raise ValueError('missing paired observations')
            if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in row['values']):
                raise ValueError('invalid observation')
            if name != 'all_call_tokens' and any(v > 1 for v in row['values']):
                raise ValueError('quality observations must lie in [0,1]')
    for name in ('featurebench_correctness', 'swe_evo_retained_correctness'):
        if not any(v > 0 for row in report['metrics'][name] for v in row['values']):
            raise ValueError('zero verified coding work cannot establish a passing release baseline/candidate')
    calls = report.get('calls', [])
    if not calls or len({r['id'] for r in calls}) != len(calls):
        raise ValueError('missing/duplicate all-call inventory')
    for call in calls:
        if call['cohort'] not in ('setup', 'failed', 'scored') or not SHA.fullmatch(call['receipt_sha256']):
            raise ValueError('missing physical receipt/cohort')
        if any(type(call.get(k)) is not int or call[k] < 0 for k in ('prompt', 'completion', 'cached')) or call['cached'] > call['prompt']:
            raise ValueError('unknown/invalid native token usage')
    cost = sum(c['prompt'] + c['completion'] for c in calls)
    if cost != sum(sum(r['values']) for r in report['metrics']['all_call_tokens']):
        raise ValueError('all setup/failed/scored tokens must reconcile exactly; cache is a subset')
    return cost


def compare(baseline, candidate, policy):
    base_cost, candidate_cost = validate(baseline, policy), validate(candidate, policy)
    if baseline['component']['repository'] != candidate['component']['repository'] or baseline['matched_environment_sha256'] != candidate['matched_environment_sha256']:
        raise ValueError('unmatched repository/model/tasks/seeds/caps/graders/protocol')
    if base_cost == 0:
        raise ValueError('zero-cost baseline cannot establish token economics')
    rng = random.Random(policy['bootstrap_seed'])
    results = {}
    for name in sorted(REQUIRED):
        rule = policy['metrics'][name]
        a = {r['cluster']: r['values'] for r in baseline['metrics'][name]}
        b = {r['cluster']: r['values'] for r in candidate['metrics'][name]}
        if a.keys() != b.keys() or any(len(a[k]) != len(b[k]) for k in a):
            raise ValueError('paired task/question/policy clusters differ')
        keys = sorted(a)
        def effect(sample):
            x = mean(v for k in sample for v in a[k]); y = mean(v for k in sample for v in b[k])
            if rule['scale'] == 'relative':
                if x <= 0:
                    raise ValueError('zero baseline in sampled token cluster')
                difference = (y - x) / x
            else:
                difference = y - x
            return difference if rule['direction'] == 'higher' else -difference
        observed = effect(keys)
        draws = sorted(effect(rng.choices(keys, k=len(keys))) for _ in range(policy['bootstrap_resamples']))
        lo, hi = draws[int(.025 * len(draws))], draws[min(len(draws)-1, int(.975 * len(draws)))]
        tolerance = rule['tolerance']
        state = ('regression' if observed < -rule['gross_loss'] or hi < -tolerance else
                 'inconclusive' if lo < -tolerance else
                 'improvement' if lo > tolerance else 'within_tolerance')
        results[name] = dict(change_in_favorable_direction=observed, paired_95_interval=[lo, hi], state=state,
            tolerance=tolerance, clusters=len(keys), boundary='Conditional paired cluster bootstrap; not a universal guarantee or a substitute for independent repeats.')
    states = {v['state'] for v in results.values()}
    # No cheap failed arm earns release savings: every quality metric must clear.
    passed = not states.intersection({'regression', 'inconclusive'})
    return dict(schema='release-benchmark-decision-v1', release_allowed=passed,
        status='blocked_regression' if 'regression' in states else 'blocked_inconclusive' if not passed else 'pass',
        baseline_sha256=canonical_sha(baseline), candidate_sha256=canonical_sha(candidate), policy_sha256=canonical_sha(policy),
        metrics=results, improvements=[k for k,v in results.items() if v['state']=='improvement'] if passed else [],
        warnings=[k for k,v in results.items() if v['state'] in ('regression','inconclusive')],
        baseline_all_call_tokens=base_cost, candidate_all_call_tokens=candidate_cost,
        limitation='An audited experiment decision, not authenticated human approval, semantic truth, product safety or authority. Local API0 excludes hardware/energy/labor.')

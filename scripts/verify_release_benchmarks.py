"""Resolve a release approval from protected benchmark main; no model/network execution beyond public GitHub reads.

No caller-supplied pass flag or local evidence file can authorize publication.
The trusted benchmark approval index selects the approval for the exact build;
each approval declares the standard that granted it. A policy-v1 approval is
resolved by recomputing its matched-baseline comparison. A policy-v2 governance
approval (owner decision, 2026-10-24) is resolved by re-checking its recorded
evidence: build provenance from the component repository's public Actions
records, the frozen detector battery's records and their recorded exact
reproduction, the governance decision record's hash, and suite health. This
does not authenticate physical measurements beyond the protected
publication/audit process.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from benchmark_runner.release_gate import compare, canonical_sha

REPO = 'electrohire/spec-kit-aee-benchmark'
GOVERNANCE_STANDARD = 'policy-v2-governance'
GOVERNANCE_POLICY = 'benchmarks/releases/policy-v2.json'


def decode(raw):
    def members(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate evidence member')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=members, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'aee-benchmark-release-gate', 'Accept':'application/vnd.github+json'}), timeout=60) as r:
        raw = r.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('oversized release evidence')
    return raw


def resolve(repository, commit, artifact_sha256, get=fetch):
    if repository not in ('electrohire/applied-epistemic-engineering', 'electrohire/spec-kit-aee') or not re.fullmatch('[0-9a-f]{40}', commit) or not re.fullmatch('[0-9a-f]{64}', artifact_sha256):
        raise ValueError('unsupported/unbound candidate identity')
    revision = decode(get(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('invalid protected benchmark revision')
    base = f'https://raw.githubusercontent.com/{REPO}/{revision}/'
    def read(name): return decode(get(base + name))
    matches = [x for x in read('benchmarks/releases/approvals.json')['approvals'] if x['repository']==repository and x['commit']==commit and x['artifact_sha256']==artifact_sha256]
    if len(matches) != 1:
        raise ValueError('no unique audited approval for this exact build; release blocked, queue benchmarks')
    entry = matches[0]
    if entry.get('standard') == GOVERNANCE_STANDARD:
        return resolve_governance(entry, repository, commit, artifact_sha256, revision, get, base, read)
    if entry.get('standard') not in (None, 'policy-v1'):
        raise ValueError('approval declares an unknown release standard')
    runs = decode(get(f'https://api.github.com/repos/{REPO}/actions/runs?head_sha={revision}&per_page=100'))['workflow_runs']
    if not any(r['head_sha'] == revision and r['event'] == 'push' and r['path'] == '.github/workflows/ci.yml' and r['status'] == 'completed' and r['conclusion'] == 'success' for r in runs):
        raise ValueError('protected benchmark publication lacks exact-head green CI')
    accepted = [x for x in read('benchmarks/releases/accepted-baselines.json')['baselines'] if x['id']==entry['baseline_id'] and x['repository']==repository]
    if len(accepted) != 1:
        raise ValueError('accepted matched baseline missing/ambiguous')
    def report(ref):
        name = ref['path']
        if not re.fullmatch(r'reports/releases/[A-Za-z0-9_./-]+\.json', name) or '..' in name.split('/'):
            raise ValueError('release report escaped protected report tree')
        raw = get(base + name)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('bound release report changed')
        return decode(raw)
    baseline, candidate = report(accepted[0]['evidence']), report(entry['evidence'])
    if candidate['component'] != dict(repository=repository, commit=commit, artifact_sha256=artifact_sha256):
        raise ValueError('benchmark used another product commit/build artifact')
    if baseline['component'] == candidate['component']:
        raise ValueError('candidate cannot approve itself as baseline')
    policy=read('benchmarks/releases/policy-v1.json')
    if entry['policy_sha256']!=canonical_sha(policy):
        raise ValueError('approval policy changed; no retroactive margin substitution')
    decision = compare(baseline, candidate, policy)
    if not decision['release_allowed']:
        raise ValueError('release comparison blocked: ' + decision['status'])
    return dict(benchmark_revision=revision, repository=repository, commit=commit, artifact_sha256=artifact_sha256, decision=decision)


def resolve_governance(entry, repository, commit, artifact_sha256, revision, get, base, read):
    """Resolve an approval granted under policy-v2 (owner governance decision,
    2026-10-24). Every element is re-checked from protected benchmark main or
    from the component repository's public Actions records at verification
    time; nothing is taken from the caller beyond the build identity."""
    policy = read(GOVERNANCE_POLICY)
    if policy.get('schema') != 'release-governance-policy-v2':
        raise ValueError('governance policy missing or not the registered schema')
    if entry.get('policy_sha256') != canonical_sha(policy):
        raise ValueError('approval governance policy changed; no retroactive standard substitution')
    def checked(ref, prefixes):
        name = ref['path']
        if not name.endswith('.json') or '..' in name.split('/') or not any(name.startswith(p) for p in prefixes):
            raise ValueError('governance evidence escaped protected tree')
        raw = get(base + name)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('bound governance evidence changed')
        return decode(raw)
    evidence = checked(entry['evidence'], ('reports/releases/',))
    if evidence.get('schema') != 'release-governance-evidence-v2' or evidence.get('standard') != GOVERNANCE_STANDARD:
        raise ValueError('governance evidence is not the registered schema/standard')
    if evidence.get('component') != dict(repository=repository, commit=commit, artifact_sha256=artifact_sha256):
        raise ValueError('governance evidence used another product commit/build artifact')
    governance = evidence['governance']
    if governance.get('policy') != GOVERNANCE_POLICY or governance.get('decision_record') != policy.get('decision_record'):
        raise ValueError('governance evidence is not anchored to the registered policy and decision record')
    raw = get(base + governance['decision_record'])
    if hashlib.sha256(raw).hexdigest() != governance.get('decision_record_sha256'):
        raise ValueError('governance decision record changed')
    build = evidence['build']
    run = decode(get(f'https://api.github.com/repos/{repository}/actions/runs/{build["build_run_id"]}'))
    if (run.get('repository', {}).get('full_name') != repository or run.get('head_sha') != commit
            or run.get('head_branch') != 'main' or run.get('path') != '.github/workflows/benchmark-candidate.yml'
            or run.get('event') not in ('push', 'workflow_dispatch')
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'):
        raise ValueError('candidate build provenance does not verify')
    artifacts = decode(get(f'https://api.github.com/repos/{repository}/actions/runs/{build["build_run_id"]}/artifacts'))['artifacts']
    named = [a for a in artifacts if a['name'] == build['artifact_name'] and not a['expired']]
    if build['artifact_name'] != f'benchmark-candidate-{commit}' or len(named) != 1:
        raise ValueError('candidate build artifact missing/expired/ambiguous')
    bundles = evidence['detector_battery']['bundles']
    if len(bundles) != 5:
        raise ValueError('governance battery must record exactly the five frozen bundles')
    for bundle in bundles:
        composed = checked(bundle['frozen_records']['composed'], ('reports/aee-validation/',))
        summary = checked(bundle['frozen_records']['summary'], ('reports/aee-validation/',))
        try:
            score = composed['state']['aee']['aee']['scores'][bundle['claim_id']]
            lane = composed['metadata']['lane_states'][0]['lane_1']
            actual = dict(
                outcome=composed['outcome'],
                lane_1={k: lane[k] for k in ('outcome', 'threshold', 'claims_at_or_above_threshold', 'claims_below_threshold')},
                direct_score=score['direct_score'], propagated_score=score['propagated_score'],
                band=score['band'], components=score['components'], notes=score['notes'],
                evidence_verification=summary['evidence_verification'],
                aee_exit=summary['aee_exit'], composition_exit=summary['composition_exit'])
        except (KeyError, IndexError, TypeError):
            raise ValueError('frozen battery record shape changed')
        if actual != bundle['frozen_fields']:
            raise ValueError('frozen battery record does not match the recorded evidence')
        if bundle.get('rescore_exact_match') is not True or bundle.get('rescore_fields') != bundle['frozen_fields']:
            raise ValueError('recorded battery re-score is not an exact reproduction')
    suites = evidence['suites']
    engine_runs = decode(get(f'https://api.github.com/repos/{repository}/actions/runs?head_sha={commit}&per_page=100'))['workflow_runs']
    if not any(r['head_sha'] == commit and r['path'] == '.github/workflows/ci.yml' and r['status'] == 'completed' and r['conclusion'] == 'success' for r in engine_runs):
        raise ValueError('component CI not successful at the candidate commit')
    harness = suites['harness_suite']
    if type(harness.get('passed')) is not int or harness['passed'] <= 0 or harness.get('failed') != 0:
        raise ValueError('harness suite totals do not verify')
    lineage = decode(get(f'https://api.github.com/repos/{REPO}/compare/{harness["lineage_commit"]}...{revision}'))
    if lineage.get('behind_by') != 0 or lineage.get('status') not in ('ahead', 'identical'):
        raise ValueError('harness suite lineage is not contained in protected benchmark main')
    benchmark_runs = decode(get(f'https://api.github.com/repos/{REPO}/actions/runs?head_sha={revision}&per_page=100'))['workflow_runs']
    completed = [r for r in benchmark_runs if r['head_sha'] == revision and r['event'] == 'push' and r['path'] == '.github/workflows/ci.yml' and r['status'] == 'completed']
    benchmark_ci = completed[0]['conclusion'] if completed else 'no completed run at revision'
    decision = dict(schema='release-governance-decision-v2', standard=GOVERNANCE_STANDARD,
        release_allowed=True, status='pass_governance',
        policy_sha256=canonical_sha(policy), evidence_sha256=entry['evidence']['sha256'],
        checks=dict(build_run_id=build['build_run_id'], detector_bundles=len(bundles),
                    engine_ci='success', harness_suite=f"{harness['passed']} passed, {harness['failed']} failed"),
        benchmark_ci_at_revision=benchmark_ci,
        limitation=policy['limitations'])
    return dict(benchmark_revision=revision, repository=repository, commit=commit, artifact_sha256=artifact_sha256, decision=decision)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--artifact-sha256', required=True)
    args=parser.parse_args()
    try:
        value=resolve(args.repository,args.commit,args.artifact_sha256)
    except Exception as exc:
        print('Benchmark release gate blocked: ' + str(exc),file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(value,indent=2))
    if value['decision'].get('improvements'):
        print('Verified improvements: '+', '.join(value['decision']['improvements']),file=sys.stderr)


if __name__=='__main__':main()

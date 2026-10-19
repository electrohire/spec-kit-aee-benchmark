"""Resolve a release approval from protected benchmark main; no model/network execution beyond public GitHub reads.

No caller-supplied pass flag or local evidence file can authorize publication.
The trusted benchmark approval index selects bound reports and an accepted baseline;
comparison is recomputed. This does not authenticate physical measurements beyond
the protected publication/audit process.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from benchmark_runner.release_gate import compare

REPO = 'electrohire/spec-kit-aee-benchmark'


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
    runs = decode(get(f'https://api.github.com/repos/{REPO}/actions/runs?head_sha={revision}&per_page=100'))['workflow_runs']
    if not any(r['head_sha'] == revision and r['event'] == 'push' and r['path'] == '.github/workflows/ci.yml' and r['status'] == 'completed' and r['conclusion'] == 'success' for r in runs):
        raise ValueError('protected benchmark publication lacks exact-head green CI')
    matches = [x for x in read('benchmarks/releases/approvals.json')['approvals'] if x['repository']==repository and x['commit']==commit and x['artifact_sha256']==artifact_sha256]
    if len(matches) != 1:
        raise ValueError('no unique audited approval for this exact build; release blocked, queue benchmarks')
    entry = matches[0]
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
    decision = compare(baseline, candidate, read('benchmarks/releases/policy-v1.json'))
    if not decision['release_allowed']:
        raise ValueError('release comparison blocked: ' + decision['status'])
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
    if value['decision']['improvements']:
        print('Verified improvements: '+', '.join(value['decision']['improvements']),file=sys.stderr)


if __name__=='__main__':main()

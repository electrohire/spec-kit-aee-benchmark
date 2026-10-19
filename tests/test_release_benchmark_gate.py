"""Synthetic release-policy and authenticated-publication boundary fixtures only."""
import copy
import json
import sys
from pathlib import Path

import pytest
from benchmark_runner.release_gate import compare, canonical_sha
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_release_benchmarks as verifier
ROOT=Path(__file__).resolve().parents[1]


def fixtures():
    policy=json.loads((ROOT/'benchmarks/releases/policy-v1.json').read_text())
    policy['bootstrap_resamples']=200
    report=dict(schema='release-benchmark-evidence-v1',status='complete',audits={k:True for k in ('inputs','source','grades','ledgers','calls','upstream_labels')},usage_unknown=0,ungraded=0,matched_environment_sha256='a'*64,component=dict(repository='electrohire/applied-epistemic-engineering',commit='a'*40,artifact_sha256='a'*64),metrics={},calls=[])
    for key,rule in policy['metrics'].items():
        report['metrics'][key]=[dict(cluster=str(i),values=[10 if key=='all_call_tokens' else 0 if key.endswith('false_acceptance') else 1]) for i in range(rule['minimum_clusters'])]
    report['calls']=[dict(id=str(i),cohort='setup' if i==0 else 'scored',receipt_sha256='b'*64,prompt=8,completion=2,cached=0) for i in range(60)]
    other=copy.deepcopy(report);other['component'].update(commit='c'*40,artifact_sha256='c'*64)
    return report,other,policy


def test_equal_and_small_cost_noise_pass_without_manufactured_improvement():
    a,b,p=fixtures()
    for index,row in enumerate(b['metrics']['all_call_tokens']):row['values']=[11 if index%2 else 10]
    for index,call in enumerate(b['calls']):call['prompt']=9 if index%2 else 8
    result=compare(a,b,p)
    assert result['release_allowed'] and result['improvements']==[]
    assert all(m['state']=='within_tolerance' for m in result['metrics'].values())


@pytest.mark.parametrize('change',['unknown','missing_grade','unmatched','zero_work','duplicate_call','unreconciled_cost','duplicate_cluster'])
def test_incomplete_unmatched_or_cheap_failed_candidate_cannot_pass(change):
    a,b,p=fixtures()
    if change=='unknown':b['usage_unknown']=1
    elif change=='missing_grade':b['audits']['grades']=False
    elif change=='unmatched':b['matched_environment_sha256']='d'*64
    elif change=='zero_work':
        for row in b['metrics']['swe_evo_retained_correctness']:row['values']=[0]
    elif change=='duplicate_call':b['calls'][1]=b['calls'][0]
    elif change=='unreconciled_cost':b['calls'][0]['prompt']+=1
    else:b['metrics']['halueval_accuracy'][1]['cluster']='0'
    with pytest.raises(ValueError):compare(a,b,p)


def test_gross_cost_loss_blocks_even_when_quality_is_unchanged():
    a,b,p=fixtures()
    for r in b['metrics']['all_call_tokens']:r['values']=[15]
    for c in b['calls']:c['prompt']=13
    result=compare(a,b,p)
    assert not result['release_allowed'] and result['status']=='blocked_regression'
    assert 'all_call_tokens' in result['warnings']


def test_real_uniform_cost_improvement_is_good_news_only_after_quality_clears():
    a,b,p=fixtures()
    for r in b['metrics']['all_call_tokens']:r['values']=[8]
    for c in b['calls']:c['prompt']=6
    result=compare(a,b,p)
    assert result['release_allowed'] and result['improvements']==['all_call_tokens']
    b['metrics']['featurebench_correctness'][0]['values']=[0]
    result=compare(a,b,p)
    assert not result['release_allowed'] and result['improvements']==[]


def test_uncertainty_crossing_noninferiority_margin_is_not_called_noise_equivalence():
    a,b,p=fixtures()
    for i,r in enumerate(a['metrics']['halueval_accuracy']):r['values']=[int(i%2==0)]
    for i,r in enumerate(b['metrics']['halueval_accuracy']):r['values']=[int(i%2!=0)]
    result=compare(a,b,p)
    assert result['metrics']['halueval_accuracy']['state']=='inconclusive'
    assert not result['release_allowed']


def test_missing_protected_approval_blocks_without_trusting_caller_pass_flags():
    a,b,p=fixtures(); revision='e'*40
    def get(url):
        if url.endswith('/commits/main'):data={'sha':revision}
        elif '/actions/runs?' in url:data={'workflow_runs':[dict(head_sha=revision,event='push',path='.github/workflows/ci.yml',status='completed',conclusion='success')]}
        else:data={'approvals':[]}
        return json.dumps(data).encode()
    with pytest.raises(ValueError,match='no unique audited approval'):
        verifier.resolve(b['component']['repository'],b['component']['commit'],b['component']['artifact_sha256'],get)


def test_duplicate_or_nonfinite_published_json_is_refused():
    with pytest.raises(ValueError):verifier.decode('{"a":1,"a":2}')
    with pytest.raises(ValueError):verifier.decode('{"a":NaN}')


def test_build_requests_are_deterministic_content_bound_and_do_not_mean_success(tmp_path):
    import build_benchmark_request as request
    inputs=tmp_path/'dist';inputs.mkdir();(inputs/'candidate.whl').write_bytes(b'synthetic candidate, not an installable wheel')
    one=request.prepare('electrohire/applied-epistemic-engineering','a'*40,123,inputs,tmp_path/'one')
    two=request.prepare('electrohire/applied-epistemic-engineering','a'*40,124,inputs,tmp_path/'two')
    assert one['artifact_sha256']==two['artifact_sha256']
    assert one['status']=='queued_not_executed' and one['build_run_id']!=two['build_run_id']
    with pytest.raises(ValueError):request.prepare('outsider/repo','a'*40,125,inputs,tmp_path/'bad')

@pytest.mark.parametrize('fault',[None,'wrong_build','bad_hash','unapproved_baseline','ci_not_green'])
def test_protected_index_exact_build_and_hashes_are_recomputed(fault):
    import hashlib
    a,b,p=fixtures();revision='e'*40
    baseline_ref=dict(path='reports/releases/test/baseline.json',sha256=hashlib.sha256(json.dumps(a).encode()).hexdigest())
    candidate_ref=dict(path='reports/releases/test/candidate.json',sha256=hashlib.sha256(json.dumps(b).encode()).hexdigest())
    entry=dict(repository=b['component']['repository'],commit=b['component']['commit'],artifact_sha256=b['component']['artifact_sha256'],baseline_id='accepted-01',evidence=candidate_ref,policy_sha256=canonical_sha(p))
    accepted=dict(id='accepted-01',repository=a['component']['repository'],evidence=baseline_ref)
    if fault=='wrong_build':b['component']['artifact_sha256']='f'*64
    if fault=='bad_hash':candidate_ref['sha256']='f'*64
    if fault=='unapproved_baseline':accepted['id']='other'
    blobs={'benchmarks/releases/approvals.json':dict(approvals=[entry]),'benchmarks/releases/accepted-baselines.json':dict(baselines=[accepted]),'benchmarks/releases/policy-v1.json':p,baseline_ref['path']:a,candidate_ref['path']:b}
    def get(url):
        if url.endswith('/commits/main'):value=dict(sha=revision)
        elif '/actions/runs?' in url:value=dict(workflow_runs=[dict(head_sha=revision,event='push',path='.github/workflows/ci.yml',status='completed',conclusion='failure' if fault=='ci_not_green' else 'success')])
        else:value=blobs[url.split('/'+revision+'/')[1]]
        return json.dumps(value).encode()
    if fault:
        with pytest.raises(ValueError):verifier.resolve(entry['repository'],entry['commit'],entry['artifact_sha256'],get)
    else:
        result=verifier.resolve(entry['repository'],entry['commit'],entry['artifact_sha256'],get)
        assert result['decision']['release_allowed'] and result['benchmark_revision']==revision


def test_candidate_build_verification_rejects_untrusted_run_or_changed_bundle(tmp_path):
    import build_benchmark_request as request
    import verify_candidate_build as build
    dist=tmp_path/'dist';dist.mkdir();(dist/'candidate.whl').write_bytes(b'fixture')
    repo='electrohire/applied-epistemic-engineering';commit='a'*40
    request.prepare(repo,commit,123,dist,tmp_path/'out')
    run=dict(id=123,repository=dict(full_name=repo),head_repository=dict(full_name=repo),event='push',head_branch='main',path='.github/workflows/benchmark-candidate.yml',conclusion='success',head_sha=commit)
    artifacts={'artifacts':[dict(name='benchmark-candidate-'+commit,expired=False)]}
    assert build.verify(repo,run,artifacts,tmp_path/'out')['commit']==commit
    with pytest.raises(ValueError):build.verify(repo,{**run,'event':'pull_request'},artifacts,tmp_path/'out')
    (tmp_path/'out/candidate-bundle.zip').write_bytes(b'changed')
    with pytest.raises(ValueError):build.verify(repo,run,artifacts,tmp_path/'out')


def test_release_version_is_literal_and_does_not_import_candidate(tmp_path):
    import verify_release_version as v
    (tmp_path/'pyproject.toml').write_text('[project]\nversion="1.6.0"\n')
    assert v.version(tmp_path,'engine')=='1.6.0'
    (tmp_path/'extension.yml').write_text('extension:\n  id: aee\n  version: "1.6.0"\n')
    assert v.version(tmp_path,'extension')=='1.6.0'
    (tmp_path/'extension.yml').write_text('extension:\n  version: "1.6.0"\n  version: "9.9.9"\n')
    with pytest.raises(ValueError):v.version(tmp_path,'extension')

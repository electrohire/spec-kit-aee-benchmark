"""Offline-only join of stopped03 and authorized completion04; no raw writes."""
from pathlib import Path
import collections
import hashlib
import json
import random
import sys
import datetime

R = Path(__file__).resolve().parent.parent
P = R / 'work/benchmark-results-publication'
G = R / 'work/benchmark-release-gates'
STOP = R / 'validation/matched03-stop-20261020'
REC = R / 'validation/matched-completion-recovery-04'
OLD = P / 'artifacts/matched-hallucinations-03'
NEW = REC / 'scored'
OUTPUT = REC / 'independent-combined-grade.json'
sys.path[:0] = [str(P / 'scripts'), str(P / 'src'), str(G / 'scripts')]


def guard(event, args):
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system'):
        raise RuntimeError('offline audit forbids network/process execution')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(args[0]).resolve()
        if path.name == '.env': raise RuntimeError('credential reads forbidden')
        mode = args[1]
        if isinstance(mode, str) and any(c in mode for c in 'wax+') and path != OUTPUT:
            raise RuntimeError('offline auditor may write only its derived grade')


sys.dont_write_bytecode = True
sys.addaudithook(guard)
import matched_hallucinations as m
import matched_hallucinations_audit as a
import matched_completion_recovery as recovery
import jsonschema


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def load(p): return json.loads(Path(p).read_text())


def pair_metrics(rows, cases, seed, excluded=()):
    observed = {(x['index'], x['arm']): x for x in rows if x['index'] not in excluded}
    result = {}
    for dataset in ('halueval_qa', 'ragtruth_test'):
        comparisons = {}
        for left, right in (('baseline', 'spec_kit'), ('spec_kit', 'spec_kit_aee'), ('baseline', 'spec_kit_aee')):
            groups = {}; left_only = right_only = 0
            for index, case in enumerate(cases):
                if case['dataset'] != dataset or index in excluded: continue
                x, y = observed[index, left], observed[index, right]
                lc, rc = x['prediction'] == case['gold'], y['prediction'] == case['gold']
                groups.setdefault(case['cluster'], []).append(int(rc)-int(lc))
                left_only += lc and not rc; right_only += rc and not lc
            values = list(groups.values()); rng = random.Random(seed); boot = []
            for _ in range(2000):
                chosen = [rng.choice(values) for _ in values]
                boot.append(sum(map(sum, chosen))/sum(map(len, chosen)))
            boot.sort()
            comparisons[left+'_vs_'+right] = dict(paired_responses=sum(map(len, values)), clusters=len(values),
                accuracy_difference_right_minus_left=sum(map(sum, values))/sum(map(len, values)),
                cluster_bootstrap_95=[boot[49], boot[1949]], left_only_correct=int(left_only), right_only_correct=int(right_only))
        result[dataset] = comparisons
    return result


def main():
    if OUTPUT.exists(): raise RuntimeError('derived grade already exists; never overwrite')
    state = load(NEW / 'result.json')
    if not state.get('complete') or state.get('error') or len(state['rows']) != 9 or state['physical_calls'] != 18:
        raise RuntimeError('completion-only auditor refuses incomplete recovery')
    freeze = load(NEW / 'recovery-freeze.json')
    if freeze['controller_head'] != '286f3d8348c9c07d7f9a8c0227e790528698ad9b': raise ValueError('controller head changed')
    if sha(G / 'scripts/matched_completion_recovery.py') != freeze['controller_sha256']: raise ValueError('controller changed')
    recovery.verify_inventory(OLD, STOP / 'retained-files-sha256.json')
    plan, cases = m.verify(OLD)
    started = load(OLD / 'run-started.json')
    if m.source_hashes() != started['source_hashes']: raise ValueError('original declared source changed')
    partial_path = STOP / 'independent-partial-grade.json'
    if sha(partial_path) != 'd45992541ff01453ae0967e10a846b0305acc8e73015a93b3c076dcd6710c06d':
        raise ValueError('original independently retained grade changed')
    partial = load(partial_path)
    # Recompute the complete original receipt/policy/helper/AEE audit, including
    # its retained orphan draft and failed request. It stays incomplete.
    original_integrity = a.audit(OLD, plan, cases)
    if original_integrity != partial['integrity']: raise ValueError('original integrity audit differs')
    recovery.validate_readiness(REC / 'native', STOP / 'restored-worker-binding-04.json', G / 'scripts/matched_completion_recovery.py')
    files = sorted((NEW / 'calls').glob('call-*.json'))
    if [x.name for x in files] != [f'call-{i:04}.json' for i in range(18)]: raise ValueError('recovery call inventory differs')
    calls = {x.relative_to(NEW).as_posix(): load(x) for x in files}
    rows = [x for x in partial['rows'] if x['status'] == 'graded']; used = set(); totals = collections.Counter(); by_arm = {}
    outcomes = collections.Counter()
    if [(x['index'],x['arm']) for x in state['rows']] != recovery.MISSING: raise ValueError('recovery schedule changed')
    for entry in state['rows']:
        index, arm = entry['index'], entry['arm']; case = cases[index]
        policy = load(OLD / 'policies' / case['dataset'] / arm / 'policy.json')['documents']
        project = NEW / 'judgments' / f'case-{index:04}-{arm}'
        saved = load(project / 'judgment.json')
        if saved != {k:v for k,v in entry.items() if k not in ('index','schedule_order','worker_epoch')}: raise ValueError('saved judgment differs')
        before, after = None, None
        if arm == 'spec_kit_aee':
            actual = a.audit_aee(project, ['implement','implement']); outcomes.update(actual)
            before, after = actual
            if actual != [entry['actual_AEE_before'],entry['actual_AEE_after']]: raise ValueError('AEE outcomes differ')
        draft = None
        for phase, key in (('draft','first_call'),('review','final_call')):
            name = entry[key]
            if name in used or name not in calls: raise ValueError('receipt reused/missing')
            used.add(name); c = calls[name]; path = NEW / name
            if sha(path) != entry[key+'_sha256'] or c.get('error') or not c.get('ended_at'): raise ValueError('receipt failed/changed')
            if c['metadata'] != dict(cohort='scored',dataset=case['dataset'],arm=arm,case_index=index,phase=phase): raise ValueError('receipt identity differs')
            native = a.usage(c)
            if native['usage_unknown']: raise ValueError('recovery usage unknown')
            totals.update(native); totals['calls'] += 1
            by_arm.setdefault(arm,collections.Counter()).update({**native,'calls':1})
            req = c['request']; expected = dict(model=plan['model'],seed=plan['seed'],max_tokens=plan['case_output'],temperature=.6,top_p=.95,top_k=20,min_p=0.,presence_penalty=0.,repeat_penalty=1.,cache_prompt=False,chat_template_kwargs=dict(enable_thinking=False))
            if any(req.get(k) != v for k,v in expected.items()): raise ValueError('model settings differ')
            if req['grammar'] != m.schema_grammar(m.DECISION_SCHEMA) or c['validation_schema'] != m.DECISION_SCHEMA: raise ValueError('schema/grammar differs')
            if c['preflight_input_tokens']+plan['case_output'] > plan['context']: raise ValueError('context exceeded')
            if req['messages'][0] != dict(role='system',content=m.TASK) or len(req['messages']) != 2: raise ValueError('system prompt differs')
            user = json.loads(req['messages'][1]['content']); allowed = {'task','policy','input','response_contract'} if phase=='draft' else {'task','policy','input','draft','literal_quote_check','instruction'}
            if arm!='baseline' and phase=='draft': allowed.update(('implementation_command','adapter'))
            if arm=='spec_kit_aee' and phase=='review': allowed.add('actual_AEE_feedback')
            if set(user)!=allowed or user['task']!=m.TASK or user['input']!=case['payload'] or user['policy']!=policy: raise ValueError('input/policy/treatment leaked or changed')
            response=c['response']; choice=response['choices'][0]
            if response['model']!=plan['model'] or choice['finish_reason']!='stop': raise ValueError('bad native completion')
            value=json.loads(choice['message']['content']);jsonschema.validate(value,m.DECISION_SCHEMA)
            if phase=='draft': draft=value
            else:
                if user['draft']!=draft or value['verdict']!=entry['prediction']: raise ValueError('draft/review/verdict join failed')
                quote_check=dict(exact_source_quotes=sum(bool(q.strip()) and q in str(case['payload'].get('source')) for q in draft['source_quotes']),quote_count=len(draft['source_quotes']),limitation='Literal quote membership is not semantic entailment.')
                if user['literal_quote_check']!=quote_check: raise ValueError('quote check changed')
                if arm=='spec_kit_aee' and user['actual_AEE_feedback']!=a.actual_feedback(project,0): raise ValueError('AEE feedback join failed')
        if entry['human_acceptance']!='unrecorded': raise ValueError('human approval invented')
        gate=entry['prediction'] if after is None or after in ('pass','warn') else 'abstain'
        if gate!=entry['gate_prediction']: raise ValueError('gate promotion invented')
        rows.append(dict(**{k:case[k] for k in ('dataset','id','cluster','gold','task')},index=index,arm=arm,
            prediction=entry['prediction'],gate_prediction=gate,status='graded',new_calls=2,
            actual_AEE_before=before,actual_AEE_after=after,worker_epoch='authorized-recovery-04'))
    if len(used)!=18 or len(rows)!=720 or len({(x['index'],x['arm']) for x in rows})!=720: raise ValueError('full denominator mismatch')
    excluded={x[0] for x in recovery.MISSING}
    metrics=lambda selected,key: {ds:{arm:m.external.metrics([{**r,'prediction':r[key]} for r in selected if r['dataset']==ds and r['arm']==arm]) for arm in m.ARMS} for ds in plan['datasets']}
    sensitivity=[x for x in rows if x['index'] not in excluded]
    value=dict(complete_amended_schedule=True,original03_complete=False,scheduled=720,graded=720,ungraded=0,rows=rows,
        metrics=metrics(rows,'prediction'),gate_metrics=metrics(rows,'gate_prediction'),paired=pair_metrics(rows,cases,plan['seed']),
        original_worker_complete_case_sensitivity=dict(excluded_case_indices=sorted(excluded),graded=len(sensitivity),metrics=metrics(sensitivity,'prediction'),paired=pair_metrics(rows,cases,plan['seed'],excluded)),
        original_integrity=original_integrity,recovery_accounting=dict(totals),recovery_accounting_by_arm={k:dict(v) for k,v in by_arm.items()},recovery_scored_AEE_outcomes=dict(outcomes),
        original_accounting=load(STOP/'stop-summary.json')['accounting'],
        separate_native_setup=[dict(episode='original03',path=str(P/'artifacts/matched-native-bounds-03/probe-result.json'),result=load(P/'artifacts/matched-native-bounds-03/probe-result.json')),
            dict(episode='recovery04',calls=[a.usage(load(p)) for p in sorted((REC/'native/calls').glob('*.json'))])],
        provenance=dict(original_inventory_sha256=sha(STOP/'retained-files-sha256.json'),partial_grade_sha256=sha(partial_path),recovery_freeze_sha256=sha(NEW/'recovery-freeze.json'),auditor_sha256=sha(__file__),audited_at=datetime.datetime.now(datetime.timezone.utc).isoformat()),
        limitations='Original03 halted; nine cells completed in an explicitly approved second worker epoch. Full comparison is amended/descriptive, not uninterrupted or independent replication. One seed/policy, public exposure, no protected identity/human acceptance/semantic oracle. Unknown original failed-request usage retained; all-call tokens are a lower bound. No coding payback conclusion.')
    with OUTPUT.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps({k:value[k] for k in ('graded','ungraded','metrics','paired','recovery_accounting')},indent=2))


if __name__=='__main__': main()

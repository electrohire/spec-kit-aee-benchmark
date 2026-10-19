"""Offline receipt, treatment and cost joins, independent of proposed verdicts.

Hash chains establish retained local integrity, not external identity or truth.
This auditor never calls a model and never supplies labels to a treatment.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

import jsonschema

from benchmark_runner.store import Store


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('evidence path escaped its study')
    return path


def usage(call):
    value = call.get('usage')
    if value is None:
        if not call.get('unknown_reason'):
            raise ValueError('missing usage has no reason')
        return dict(usage_unknown=1, known_native_tokens=0)
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError('invalid native usage')
    if value['total_tokens'] != value['prompt_tokens'] + value['completion_tokens']:
        raise ValueError('contradictory native total')
    if call.get('response', {}).get('usage') != value:
        raise ValueError('receipt usage differs from native response')
    cached = value.get('prompt_tokens_details', {}).get('cached_tokens')
    if cached is not None and (type(cached) is not int or not 0 <= cached <= value['prompt_tokens']):
        raise ValueError('invalid cached subset')
    return dict(prompt_tokens=value['prompt_tokens'], completion_tokens=value['completion_tokens'],
                known_native_tokens=value['total_tokens'], cached_tokens=cached or 0,
                unknown_cache_fields=int(cached is None), usage_unknown=0)


def audit_aee(project, phases):
    from aee.ledger import HashChainLedger
    store = Store(project / 'store')
    events = store.events('assessments')
    if [e['phase'] for e in events] != phases or not store.verify_stream('assessments')['chain_verified']:
        raise ValueError('missing/extra/unverified actual AEE execution')
    outcomes = []
    for position, event in enumerate(events):
        artifacts = []
        for ref in event['artifacts']:
            data = contained(store.root, ref['path']).read_bytes()
            if digest(data) != ref['sha256']:
                raise ValueError('AEE artifact hash mismatch')
            artifacts.append(data)
        if len(artifacts) != 5 or event['ledger_entries'] != position + 1:
            raise ValueError('AEE snapshot inventory/count mismatch')
        claims, envelope, composition, ledger, returned = artifacts
        claim = json.loads(claims)['claims'][0]
        if claim['status'] != 'draft' or claim['stage'] != 'created':
            raise ValueError('invented lifecycle promotion')
        if json.loads(envelope)['phase'] != 'after_' + event['phase']:
            raise ValueError('AEE phase mismatch')
        composed = json.loads(composition)
        if composed['outcome'] != event['outcome'] or json.loads(returned)['outcome'] != event['outcome'] or composed['metadata']['evaluator_count'] != 1:
            raise ValueError('AEE composition/outcome mismatch')
        if len(ledger.splitlines()) != event['ledger_entries']:
            raise ValueError('AEE retained ledger snapshot mismatch')
        outcomes.append(event['outcome'])
    verification = HashChainLedger(project / 'aee-project/.specify/extensions/aee/ledger/epistemic-ledger.jsonl').verify(require_anchor=True)
    if not verification.valid or verification.entries != len(events):
        raise ValueError('AEE current anchored ledger mismatch')
    return outcomes


def actual_feedback(project, index):
    store = Store(project / 'store')
    event = store.events('assessments')[index]
    value = read(contained(store.root, event['artifacts'][-1]['path']))
    return {key: value.get(key) for key in ('outcome', 'summary', 'findings', 'next_action')}


def audit(out, plan, cases):
    state = read(out / 'result.json')
    started = read(out / 'run-started.json')
    # Archive can be audited after the controller checkout advances; no demand
    # that historical source becomes fresh code, and no changed archive allowed.
    for name, expected in started['source_hashes'].items():
        if digest(contained(out / 'source-archive', name).read_bytes()) != expected:
            raise ValueError('frozen source archive changed')
    if started['input_hashes_sha256'] != digest((out / 'input-hashes.json').read_bytes()):
        raise ValueError('input freeze changed since launch')
    files = sorted((out / 'calls').glob('call-*.json'))
    if [p.name for p in files] != [f'call-{i:04}.json' for i in range(len(files))] or len(files) != state['physical_calls'] or len(files) > plan['maximum_calls']:
        raise ValueError('physical call inventory/cap mismatch')
    calls, accounting = {}, {}
    for path in files:
        call = read(path)
        metadata = call['metadata']
        if metadata['cohort'] not in ('setup', 'scored') or metadata['arm'] not in plan['arms']:
            raise ValueError('unexpected call cohort/arm')
        native = usage(call)
        for key in (metadata['cohort'], metadata['cohort'] + '/' + metadata['arm']):
            counter = accounting.setdefault(key, Counter())
            counter['calls'] += 1
            counter.update(native)
        request = call['request']
        bounds = plan.get('schema_bounds')
        if bounds:
            props = request['response_format']['json_schema']['schema']['properties']
            if metadata['phase'] in ('draft', 'review'):
                actual = (props['rationale'].get('maxLength'), props['source_quotes']['items'].get('maxLength'), props['uncertainties']['items'].get('maxLength'))
                expected = (bounds['rationale_characters'], bounds['source_quote_characters'], bounds['uncertainty_characters'])
                if actual != expected:
                    raise ValueError('registered native decision string bounds missing/changed')
            elif props['document'].get('maxLength') != bounds['document_characters']:
                raise ValueError('registered native policy string bound missing/changed')
        cap = plan['case_output'] if metadata['phase'] in ('draft', 'review') else plan['policy_output']
        if (request['model'] != plan['model'] or request['seed'] != plan['seed'] or request['max_tokens'] != cap
                or request['chat_template_kwargs'] != {'enable_thinking': False}
                or request['cache_prompt'] is not False or call['preflight_input_tokens'] + cap > plan['context']):
            raise ValueError('matched model/seed/context/output settings changed')
        if any(request.get(key) != expected for key, expected in dict(temperature=.6, top_p=.95, top_k=20, min_p=0., presence_penalty=0., repeat_penalty=1.).items()):
            raise ValueError('matched sampling settings changed')
        if not call.get('error'):
            response = call['response']
            choice = response['choices'][0]
            if response['model'] != plan['model'] or choice['finish_reason'] != 'stop':
                raise ValueError('invalid native completion')
            parsed = json.loads(choice['message']['content'])
            jsonschema.validate(parsed, request['response_format']['json_schema']['schema'])
        elif state['complete']:
            raise ValueError('completed study contains a failed call')
        calls[path.relative_to(out).as_posix()] = call
    policies = {}
    policy_receipts = set()
    for folder in [out / 'calibration' / arm / 'policy' for arm in plan['arms']] + [out / 'policies' / dataset / arm for dataset in plan['datasets'] for arm in plan['arms']]:
        path = folder / 'policy.json'
        if not path.exists():
            if state['complete']:
                raise ValueError('completed study missing a generated policy')
            continue
        policy = read(path)
        arm, dataset = policy['arm'], policy['dataset']
        phases = ['constitution'] if arm == 'baseline' else ['constitution', 'specify', 'plan', 'tasks']
        if [r['phase'] for r in policy['receipts']] != phases or policy['human_acceptance'] != 'unrecorded' or policy['artifacts_are_drafts'] is not True:
            raise ValueError('policy phase/acceptance mismatch')
        documents = {}
        if arm == 'spec_kit_aee':
            audit_aee(folder, ['specify', 'plan', 'tasks'])
        for receipt in policy['receipts']:
            name, phase = receipt['call'], receipt['phase']
            if name in policy_receipts or name not in calls:
                raise ValueError('policy receipt missing/reused')
            policy_receipts.add(name)
            call = calls[name]
            if digest(contained(out, name).read_bytes()) != receipt['call_sha256'] or call['metadata'] != dict(cohort='setup', dataset=dataset, arm=arm, phase=phase):
                raise ValueError('policy identity/hash mismatch')
            user = json.loads(call['request']['messages'][1]['content'])
            allowed = {'task', 'phase', 'deliverable', 'prior_documents', 'adapter'}
            if arm != 'baseline':
                allowed.update(('speckit_command', 'speckit_template'))
            if arm == 'spec_kit_aee' and phase in ('plan', 'tasks'):
                allowed.add('actual_AEE_feedback')
            if set(user) != allowed:
                raise ValueError('unexpected policy input fields')
            if user['prior_documents'] != documents or 'input' in user:
                raise ValueError('policy received cases or changed earlier documents')
            if ('actual_AEE_feedback' in user) != (arm == 'spec_kit_aee' and phase in ('plan', 'tasks')):
                raise ValueError('policy feedback treatment mismatch')
            if 'actual_AEE_feedback' in user and user['actual_AEE_feedback'] != actual_feedback(folder, 0 if phase == 'plan' else 1):
                raise ValueError('policy feedback differs from actual composition')
            document = json.loads(call['response']['choices'][0]['message']['content'])['document']
            data = contained(folder, receipt['artifact']).read_bytes()
            if digest(data) != receipt['artifact_sha256'] or data.decode('utf-8') != document:
                raise ValueError('generated policy artifact changed')
            documents[phase] = document
        if documents != policy['documents']:
            raise ValueError('policy documents differ from physical model outputs')
        if arm != 'baseline':
            for tag in ('git-init', 'create-feature', 'setup-plan', 'check-prerequisites'):
                if read(folder / 'host-commands' / (tag + '.json'))['exit_code'] != 0:
                    raise ValueError('Spec Kit helper failed')
        policies[dataset, arm] = documents
    schedule = read(out / 'schedule.json')
    if [(r['index'], r['arm']) for r in state['rows']] != [(r['index'], r['arm']) for r in schedule[:len(state['rows'])]]:
        raise ValueError('judgments are not a schedule prefix')
    used = set()
    aee_outcomes = Counter()
    for row in state['rows']:
        index, arm = row['index'], row['arm']
        case = cases[index]
        draft = None
        for phase, key in (('draft', 'first_call'), ('review', 'final_call')):
            name = row[key]
            if name in used or name not in calls:
                raise ValueError('duplicate or missing scored receipt')
            used.add(name)
            call = calls[name]
            if call.get('error') or digest(contained(out, name).read_bytes()) != row[key + '_sha256']:
                raise ValueError('scored receipt changed or failed')
            expected = dict(cohort='scored', arm=arm, dataset=case['dataset'], case_index=index, phase=phase)
            if call['metadata'] != expected:
                raise ValueError('scored receipt identity mismatch')
            user = json.loads(call['request']['messages'][1]['content'])
            allowed = ({'task', 'policy', 'input', 'response_contract'} if phase == 'draft' else
                       {'task', 'policy', 'input', 'draft', 'literal_quote_check', 'instruction'})
            if arm != 'baseline' and phase == 'draft':
                allowed.update(('implementation_command', 'adapter'))
            if arm == 'spec_kit_aee' and phase == 'review':
                allowed.add('actual_AEE_feedback')
            if set(user) != allowed:
                raise ValueError('unexpected classification input fields')
            if user['input'] != case['payload']:
                raise ValueError('source/candidate payload changed')
            if user['policy'] != policies.get((case['dataset'], arm)):
                raise ValueError('classification did not use its actual generated policy')
            if ('actual_AEE_feedback' in user) != (arm == 'spec_kit_aee' and phase == 'review'):
                raise ValueError('AEE feedback missing or leaked to control')
            value = json.loads(call['response']['choices'][0]['message']['content'])
            if phase == 'draft':
                draft = value
            elif user['draft'] != draft or row['prediction'] != value['verdict']:
                raise ValueError('draft/review/verdict join mismatch')
        folder = out / 'judgments' / f'case-{index:04}-{arm}'
        after = None
        if arm == 'spec_kit_aee':
            outcomes = audit_aee(folder, ['implement', 'implement'])
            if outcomes != [row['actual_AEE_before'], row['actual_AEE_after']]:
                raise ValueError('reported AEE outcome not actual composed outcome')
            user = json.loads(calls[row['final_call']]['request']['messages'][1]['content'])
            if user['actual_AEE_feedback'] != actual_feedback(folder, 0):
                raise ValueError('case feedback differs from actual composition')
            aee_outcomes.update(outcomes)
            after = outcomes[-1]
        elif row['actual_AEE_before'] is not None or row['actual_AEE_after'] is not None:
            raise ValueError('AEE execution invented on control arm')
        gate = row['prediction'] if after is None or after in ('pass', 'warn') else 'abstain'
        if row['gate_prediction'] != gate or row['human_acceptance'] != 'unrecorded':
            raise ValueError('gate/acceptance incorrectly promoted')
    if state['complete'] and (len(used) != plan['scored_calls'] or len(files) != plan['expected_total_calls']):
        raise ValueError('completed run has missing/extra receipts')
    return dict(accounting={key: dict(value) for key, value in accounting.items()},
        scored_receipts_joined=len(used), scored_AEE_outcomes=dict(aee_outcomes),
        source_archive_verified=len(started['source_hashes']),
        authority_boundary='Local retained hash/anchor integrity only, not externally authenticated identity, human acceptance or semantic truth.')

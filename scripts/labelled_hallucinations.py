"""Real local model judgments against frozen, synthetic closed-world factbooks.

This diagnostic measures bounded factual judgments, not spontaneous software
hallucination prevalence, AEE detector efficacy, or a three-arm treatment effect.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import current_local as current
from benchmark_runner.store import utc, write_json

CORPUS = current.ROOT / 'benchmarks/current_local/hallucination-cases-v1.json'
VERDICTS = ('supported', 'contradicted', 'unknown')
SCHEMA = dict(type='object', properties=dict(verdict=dict(type='string', enum=list(VERDICTS)),
    reason=dict(type='string')), required=['verdict', 'reason'], additionalProperties=False)


def oracle(case):
    facts = case['facts']
    family = case['family']
    if family == 'completion':
        if not facts.get('finished') or not facts.get('tests'):
            return 'unknown'
        truth = all(facts['tests'].values())
    elif family == 'test_execution':
        truth = facts.get('tests', {}).get(case['target'])
    elif family == 'citation_integrity':
        if not facts.get('complete_inventory'):
            return 'unknown'
        truth = facts['references'].get(case['target']) == case['claimed_digest']
    elif family == 'api_inventory':
        if not facts.get('complete_inventory'):
            return 'unknown'
        truth = case['target'] in facts['symbols']
    else:
        raise ValueError('unknown diagnostic family')
    return 'unknown' if truth is None else ('supported' if truth else 'contradicted')


def metrics(rows):
    labelled = [r for r in rows if r['gold'] != 'unknown' and r['prediction'] in VERDICTS]
    tp = sum(r['gold'] == 'contradicted' and r['prediction'] == 'contradicted' for r in labelled)
    fp = sum(r['gold'] == 'supported' and r['prediction'] == 'contradicted' for r in labelled)
    fn = sum(r['gold'] == 'contradicted' and r['prediction'] != 'contradicted' for r in labelled)
    tn = sum(r['gold'] == 'supported' and r['prediction'] != 'contradicted' for r in labelled)
    return dict(scheduled=len(rows), gold={v: sum(r['gold'] == v for r in rows) for v in VERDICTS},
        correct=sum(r['gold'] == r['prediction'] for r in rows),
        invalid_decisions=sum(r['prediction'] not in VERDICTS for r in rows),
        predictions={v: sum(r['prediction'] == v for r in rows) for v in VERDICTS},
        binary_known_truth=dict(tp=tp, fp=fp, fn=fn, tn=tn,
            precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None,
            rule='contradicted flags an error; supported/unknown do not; invalid responses excluded and reported'),
        contradicted_claims_accepted=sum(r['gold'] == 'contradicted' and r['prediction'] == 'supported' for r in rows),
        unknown_claims_accepted=sum(r['gold'] == 'unknown' and r['prediction'] == 'supported' for r in rows),
        limitations='Synthetic closed-world inputs, real model calls. Unknown truth excluded from binary denominators. Not AEE detector precision/recall, workflow hallucination prevalence or treatment efficacy.')


def run(out, corpus_version=1):
    if type(corpus_version) is not int or corpus_version not in (1, 2):
        raise ValueError('shipped corpus version1 or2 required')
    selected = CORPUS if corpus_version == 1 else current.ROOT / 'benchmarks/current_local/hallucination-cases-v2.json'
    corpus = json.loads(selected.read_text(encoding='utf-8'))
    cases = corpus['cases']
    if len(cases) != 12 or len({c['id'] for c in cases}) != 12:
        raise ValueError('preregistered twelve distinct cases required')
    current.setup()
    current.freeze(out, 'separate twelve-call labelled factbook diagnostic; max output256; no retry; real local model')
    write_json(out / 'diagnostic-plan.json', dict(corpus_version=corpus_version, corpus_sha256=hashlib.sha256(selected.read_bytes()).hexdigest(),
        cases=cases, model=current.MODEL, context=32768, max_output=256, seed=current.SEEDS[0],
        timeout=600, max_calls=12, reserved_tokens=400000, synthetic_inputs=True,
        gold={c['id']: oracle(c) for c in cases}), exclusive=True)
    (out / 'calls').mkdir()
    rows = []
    state = dict(passed=False, complete=False, physical_calls=0, rows=rows)
    try:
        for index, case in enumerate(cases):
            if any(slot.get('is_processing') for slot in current.http('/slots')):
                raise RuntimeError('shared inference busy; no overlapping inference permitted')
            messages = [dict(role='system', content='Judge the claim using ONLY the supplied factbook. Missing or incomplete evidence means unknown. Return verdict supported, contradicted, or unknown and a short reason. Do not assume tests ran or invent evidence.'),
                        dict(role='user', content=json.dumps(case, sort_keys=True))]
            template = current.http('/apply-template', dict(messages=messages, chat_template_kwargs=dict(enable_thinking=False)))['prompt']
            tokens = current.http('/tokenize', dict(content=template, add_special=False))['tokens']
            if len(tokens) + 256 > 32768:
                raise ValueError('diagnostic context budget exceeded')
            request = dict(model=current.MODEL, messages=messages, temperature=.6, top_p=.95, top_k=20,
                min_p=0., presence_penalty=0., repeat_penalty=1., seed=current.SEEDS[0], max_tokens=256,
                cache_prompt=False, response_format=dict(type='json_schema', json_schema=dict(name='fact_verdict', strict=True, schema=SCHEMA)),
                chat_template_kwargs=dict(enable_thinking=False))
            record = dict(stage=0, phase='labelled_hallucination', started_at=utc(), request=request,
                          usage=None, unknown_reason='request_pending', preflight_input_tokens=len(tokens), max_output=256)
            call_path = out / 'calls' / f'call-{index:04}.json'
            write_json(call_path, record, exclusive=True)
            started = time.monotonic()
            try:
                response = current.http('/v1/chat/completions', request, timeout=600)
                record.update(response=response, usage=response.get('usage'), ended_at=utc(), unknown_reason=None)
                if not record['usage']:
                    record['unknown_reason'] = 'native_usage_not_returned'
                if response.get('model') != current.MODEL:
                    raise RuntimeError('model identity mismatch')
            except BaseException as exc:
                record.update(error=repr(exc), ended_at=utc(), unknown_reason='failed_request_usage_unknown' if not record.get('usage') else None,
                              infrastructure_evidence=getattr(exc, 'evidence', None))
                raise
            finally:
                record['request_seconds'] = time.monotonic() - started
                write_json(call_path, record)
                state['physical_calls'] += 1
            prediction = None
            try:
                choice = response['choices'][0]
                value = json.loads(choice['message']['content'])
                if choice['finish_reason'] == 'stop' and value.get('verdict') in VERDICTS and isinstance(value.get('reason'), str):
                    prediction = value['verdict']
            except (ValueError, KeyError, TypeError, IndexError):
                pass
            rows.append(dict(id=case['id'], family=case['family'], gold=oracle(case), prediction=prediction,
                call=call_path.relative_to(out).as_posix(), call_sha256=hashlib.sha256(call_path.read_bytes()).hexdigest()))
            write_json(out / 'result.json', state)
        state.update(complete=True, passed=True, metrics=metrics(rows), ended_at=utc())
    except BaseException as exc:
        state.update(error=repr(exc), ended_at=utc(), infrastructure_evidence=getattr(exc, 'evidence', None))
        raise
    finally:
        write_json(out / 'result.json', state)
    (out / 'README.md').write_text('# Labelled factual-judgment diagnostic\n\nTwelve synthetic factbooks, twelve real local-model calls. Gold labels were frozen before generation and withheld from model prompts. This is separate from scored workflow outcomes and is not AEE detector efficacy.\n\n```json\n' + json.dumps(state['metrics'], indent=2) + '\n```\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--corpus-version', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    run(args.output, args.corpus_version)

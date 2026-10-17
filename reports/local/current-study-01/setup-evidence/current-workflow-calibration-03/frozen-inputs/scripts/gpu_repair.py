"""Separately frozen, user-authorized test-feedback repairs of primary failures."""
import argparse
import ast
import json
import time
from pathlib import Path

from benchmark_runner.store import utc, write_json
from gpu_experiment import ROOT, ARMS, digest, extract, grade, local_json, query, source_hashes

INSTRUCTION = ('Repair the submitted Python implementation using the exercise facts and failure feedback. '
               'If no implementation was submitted, implement the exercise now. '
               'Return only the complete replacement Python module in a python code block. '
               'No tools or repository access are available. Do not claim tests passed.')


def run(primary, output, upstream):
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((primary/'freeze.json').read_text())
    original = json.loads((primary/'results.json').read_text())
    assert source_hashes() == frozen['source_hashes']
    assert local_json('/props') == frozen['server_props']
    for task, expected in frozen['test_hashes'].items():
        assert digest(upstream/'exercises/practice'/task/(task.replace('-', '_')+'_test.py')) == expected
    write_json(output/'freeze.json', dict(timestamp=utc(), primary_freeze_sha256=digest(primary/'freeze.json'),
        primary_results_sha256=digest(primary/'results.json'), max_rounds=2, maximum_output_per_call=1024,
        input_ceiling_per_case=32768, output_ceiling_per_case=2048, case_seconds=300,
        request_seconds=120, instruction=INSTRUCTION, same_test_feedback=True,
        hashes={str(p):digest(p) for p in [Path(__file__), ROOT/'docs/gpu-repair-protocol.md', ROOT/'scripts/gpu_experiment.py',ROOT/'scripts/local_experiment.py']},
        server_props=local_json('/props'), schedule=[(r['task'],r['arm']) for r in original]), exclusive=True)
    rows = []
    for index, previous in enumerate(original):
        folder = output/previous['path']
        folder.mkdir()
        code = (primary/previous['path']/'solution.py').read_text(encoding='utf-8')
        current_grade = previous['grade']
        feedback = previous['error'] or current_grade.get('output') or current_grade.get('error')
        row = dict(task=previous['task'], arm=previous['arm'], path=previous['path'],
                   original_passed=current_grade['passed'], rounds=[], final_passed=current_grade['passed'])
        rows.append(row)
        write_json(output/'results.json', rows)
        begin = time.monotonic()
        for round_number in range(1, 3):
            if row['final_passed']:
                break
            if (output/'CANCEL').exists():
                raise KeyboardInterrupt('CANCEL')
            remaining = 300-(time.monotonic()-begin)
            if remaining <= 25:
                row['limit'] = 'insufficient_remaining_case_time'
                break
            phase = f'repair-{round_number}'
            event = dict(round=round_number, error=None, grade=None, usage=None,
                         unknown_reason='not_dispatched', text_changed=None, ast_changed=None)
            row['rounds'].append(event)
            write_json(output/'results.json', rows)
            messages = [dict(role='system',content='You are a Python coding assistant. Use the observed failure feedback; do not invent test results.'),
                dict(role='user',content='EXERCISE\n'+frozen['task_inputs'][row['task']]['text']+
                     '\nCURRENT SUBMITTED CODE\n'+code+'\nFAILURE FEEDBACK\n'+str(feedback)+'\n'+INSTRUCTION)]
            call_path = folder/(phase+'.json')
            round_begin = time.monotonic()
            try:
                try:
                    text, record = query(messages, 1024, min(120, remaining-25), call_path)
                finally:
                    if call_path.exists():
                        record = json.loads(call_path.read_text())
                        event.update(usage=record['usage'], unknown_reason=record['unknown_reason'],
                                     model_seconds=record['seconds'], finish_reason=record.get('response',{}).get('choices',[{}])[0].get('finish_reason'))
                replacement = extract(text)
                event['text_changed'] = replacement.strip() != code.strip()
                try:
                    event['ast_changed'] = ast.dump(ast.parse(replacement)) != ast.dump(ast.parse(code))
                except SyntaxError:
                    pass
                code = replacement
                (folder/(phase+'.py')).write_text(code,encoding='utf-8')
                module = row['task'].replace('-', '_')
                test = upstream/'exercises/practice'/row['task']/(module+'_test.py')
                assert digest(test) == frozen['test_hashes'][row['task']]
                grade_start = time.monotonic()
                event['grade'] = grade(code,test.read_bytes(),module,frozen['image'],expected_count=frozen['test_counts'][row['task']])
                event['grading_seconds'] = time.monotonic()-grade_start
                row['final_passed'] = event['grade']['passed']
                feedback = event['grade'].get('output') or event['grade'].get('error')
            except BaseException as exc:
                event['error'] = type(exc).__name__+': '+str(exc)
                feedback = event['error']
                if isinstance(exc, KeyboardInterrupt):
                    write_json(output/'results.json', rows)
                    raise
            event['seconds'] = time.monotonic()-round_begin
            write_json(output/'results.json', rows)
        row['seconds'] = time.monotonic()-begin
        (folder/'final.py').write_text(code,encoding='utf-8')
        write_json(output/'results.json', rows)
        print(f'{index+1}/18 {row["task"]} {row["arm"]}: {len(row["rounds"])} repairs, pass={row["final_passed"]}',flush=True)
    summary=[]
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        events=[e for r in selected for e in r['rounds']]
        known=[e['usage'] for e in events if e['usage']]
        before=[r for r in original if r['arm']==arm]
        initial_usage=[c['usage'] for r in before for c in r['calls']]
        known_all=all(initial_usage) and len(known)==len(events)
        original_tokens=sum(u['prompt_tokens']+u['completion_tokens'] for u in initial_usage if u)
        repaired=sum(r['final_passed'] and not r['original_passed'] for r in selected)
        final=sum(r['final_passed'] for r in selected)
        repair_tokens=sum(u['prompt_tokens']+u['completion_tokens'] for u in known) if len(known)==len(events) else None
        cumulative=original_tokens+repair_tokens if known_all else None
        summary.append(dict(arm=arm,attempts=6,original_passed=sum(r['original_passed'] for r in selected),
            eligible_cases=sum(not r['original_passed'] for r in selected), repair_calls=len(events),
            cases_repaired=repaired,final_passed=final,remaining_failures=6-final,
            fixed_in_round_1=sum(not r['original_passed'] and r['final_passed'] and len(r['rounds'])==1 for r in selected),
            fixed_in_round_2=sum(not r['original_passed'] and r['final_passed'] and len(r['rounds'])==2 for r in selected),
            repair_input_tokens=sum(u['prompt_tokens'] for u in known) if len(known)==len(events) else None,
            repair_output_tokens=sum(u['completion_tokens'] for u in known) if len(known)==len(events) else None,
            known_repair_input_tokens=sum(u['prompt_tokens'] for u in known),
            known_repair_output_tokens=sum(u['completion_tokens'] for u in known),
            unknown_usage_calls=len(events)-len(known),repair_total_tokens=repair_tokens,
            repair_tokens_per_repaired_case=repair_tokens/repaired if repaired and repair_tokens is not None else None,
            cumulative_total_tokens=cumulative,cumulative_tokens_per_correct_answer=cumulative/final if final and cumulative is not None else None,
            repair_seconds_including_grading=sum(r['seconds'] for r in selected),
            model_seconds=sum(e.get('model_seconds',0) for e in events), grading_seconds=sum(e.get('grading_seconds',0) for e in events),
            changed_code_submissions=sum(e['text_changed'] is True for e in events),api_dollars=0))
    write_json(output/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('primary',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--upstream',type=Path,required=True)
    args=parser.parse_args()
    run(args.primary,args.output,args.upstream)

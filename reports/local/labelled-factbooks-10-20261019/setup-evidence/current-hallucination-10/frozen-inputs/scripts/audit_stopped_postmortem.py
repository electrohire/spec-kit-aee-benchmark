"""Audit the stopped study without executing model or grader code."""
import ast
import csv
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bound_path(folder, name):
    require(isinstance(name,str) and name and not Path(name).is_absolute(), 'confined evidence path')
    path=(folder/name).resolve(strict=True)
    require(path.is_relative_to(folder.resolve()) and path.is_file(), 'confined evidence path')
    return path


def audit(folder):
    folder = Path(folder)
    report = read(folder/'summary.json')
    rows = read(folder/'checkpoint-rows.json')
    freeze = read(folder/'freeze.json')
    require(sha(folder/'freeze.json') == report['freeze_sha256'], 'freeze binding')
    require(rows == report['rows'], 'row exports disagree')
    expected = {(p,s,a,k) for p,s,a in freeze['schedule'] for k in (1,2,3)}
    actual = [(r['project'],r['seed'],r['arm'],r['stage']) for r in rows]
    require(len(expected)==36 and len(actual)==36 and set(actual)==expected, 'scheduled inventory')
    require(len(freeze['hashes'])==348, 'frozen input inventory')
    driver = folder/'grader-sources/grader-driver.py'
    require(sha(driver)==freeze['hashes']['scripts/repeated_local.py'], 'frozen grader driver')
    require(sha(folder/'grader-sources/sandbox-driver.py')==freeze['hashes']['scripts/long_horizon.py'], 'frozen sandbox driver')
    for project in {p for p,_,_ in freeze['schedule']}:
        require(sha(folder/'grader-sources/tasks'/project/'tests.py')==freeze['hashes'][f'benchmarks/repeated_local/{project}/tests.py'], 'frozen task source')
    require(sha(folder/'controller.py')==report['controller_sha256'], 'postmortem controller')
    nodes = {n.name:n for n in ast.parse(driver.read_bytes()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    for name, digest in report['grader_function_ast_hashes'].items():
        require(hashlib.sha256(ast.dump(nodes[name],include_attributes=False).encode()).hexdigest()==digest, 'grader AST binding')
    grade_digest = hashlib.sha256(ast.dump(ast.Module(body=[nodes['grade']],type_ignores=[]),include_attributes=False).encode()).hexdigest()
    eligible = invoked = invocations = failing_hidden = 0
    bins = dict(positive=0,negative=0,unknown_graded=0,ungraded=0)
    for row in rows:
        calls = row['generation_calls']
        require(type(calls) is int and calls>=0, 'call count')
        if row['status'].startswith('not_attempted'):
            require(calls==0 and not row['grade_invocations_available'], 'unattempted cannot be graded or spend calls')
        complete = False
        if row['grade_invocations_available']:
            invoked += 1
            require(set(row['grades'])=={'public','hidden'}, 'public and hidden grades required')
            snapshot = bound_path(folder,row['published_snapshot'])
            require(sha(snapshot)==row['snapshot_sha256'], 'snapshot bytes')
            complete = True
            for mode, binding in row['grades'].items():
                invocations += 1
                path = bound_path(folder,binding['path'])
                require(sha(path)==binding['sha256'], 'grade bytes')
                grade = read(path)
                require(all(binding[k]==grade[k] for k in ('passed','test_count','exit_code')), 'grade result binding')
                require(grade['source_sha256']==row['snapshot_sha256'], 'snapshot binding')
                require(grade['grader_function_sha256']==grade_digest, 'grader function binding')
                require(grade['grader_mode']==mode, 'grader mode')
                require(sha(bound_path(folder,binding['published_grader_source']))==grade['grader_source_sha256'], 'grader test bytes')
                expected_count = freeze['calibration']['projects'][row['project']]['reference'][f"{row['stage']}-{mode}"]['test_count']
                require(binding['expected_test_count']==expected_count, 'expected inventory binding')
                inventory_complete = len(grade['cases'])==grade['test_count']==expected_count and not any(
                    f['kind'] in ('error','skipped') for case in grade['cases'] for f in case['failures'])
                require(binding['complete_test_inventory']==inventory_complete, 'grade inventory classification')
                complete &= inventory_complete
                if mode=='hidden' and inventory_complete:
                    failing_hidden += sum(not c['passed'] for c in grade['cases'])
        require(row['complete_test_inventory']==complete and row['proxy_eligible']==complete, 'proxy inventory eligibility')
        require(row['grade_status']==('complete_test_inventory' if complete else 'incomplete_test_inventory' if row['grade_invocations_available'] else 'ungraded'), 'inventory status')
        if complete:
            eligible += 1
            declaration = row['completion_asserted']
            require(declaration is None or type(declaration) is bool, 'typed completion declaration')
            bins['unknown_graded' if declaration is None else 'positive' if declaration else 'negative'] += 1
        else:
            bins['ungraded'] += 1
    require(bins==report['declaration_denominators'] and sum(bins.values())==36, 'proxy denominators')
    require(invoked==report['source_snapshots_with_grade_invocations']==2 and eligible==report['checkpoints_with_complete_inventory']==1, 'grade eligibility totals')
    require(invocations==len(report['grades'])==4, 'grade invocation inventory')
    require(sum(r['generation_calls'] for r in rows)==report['generation_calls']==192, 'generation accounting')
    require(sum(r['assessments'] for r in rows)==report['scored_actual_AEE_assessments']==0, 'actual scored AEE exposure')
    cohort = read(folder/'bounded-cost-inventory.json')['by_cohort_and_model']['stopped_incomplete_study02']['qwen3.8-27b']
    require(report['known_prompt_tokens']==cohort['prompt_tokens'] and report['known_completion_tokens']==cohort['completion_tokens'], 'native usage binding')
    require(report['known_total_tokens']==report['known_prompt_tokens']+report['known_completion_tokens']==4172224, 'native usage sum')
    require(report['false_completion_rate'] is None and report['detector_precision'] is None and report['detector_recall'] is None, 'unmeasured performance cannot be zero or measured')
    with (folder/'checkpoint-rows.csv').open(encoding='utf-8',newline='') as handle:
        csv_rows=list(csv.DictReader(handle))
    require(len(csv_rows)==len(rows) and all(
        all(cell==('' if row.get(key) is None else str(row[key])) for key,cell in exported.items())
        for row,exported in zip(rows,csv_rows)), 'CSV row export')
    return dict(schedule_rows=36, grade_invocations=invocations, snapshots_with_grades=invoked,
                complete_inventories=eligible, proxy_denominators=bins,
                hidden_test_failures=failing_hidden, actual_scored_AEE_assessments=0)


if __name__ == '__main__':
    print(json.dumps(audit(Path(__file__).resolve().parents[1]/'reports/local/current-study-02-stopped-postmortem'),indent=2))

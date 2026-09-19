"""Repair loops must count failed work and stop at success or the frozen bound."""
import json
import sys
from pathlib import Path

from benchmark_runner.store import write_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import gpu_repair as repair


def test_repair_bounds_and_cumulative_failed_tokens(tmp_path, monkeypatch):
    primary, upstream = tmp_path/'primary', tmp_path/'upstream'
    primary.mkdir()
    test = upstream/'exercises/practice/hello/hello_test.py'
    test.parent.mkdir(parents=True)
    test.write_text('fixture')
    frozen = dict(source_hashes={},server_props={},test_hashes={'hello':repair.digest(test)},
                  test_counts={'hello':1},task_inputs={'hello':{'text':'hello fixture'}},image='fixture')
    write_json(primary/'freeze.json',frozen)
    rows=[]
    for arm in repair.ARMS:
        for i in range(6):
            folder=primary/f'{arm}-{i}'
            folder.mkdir()
            (folder/'solution.py').write_text('def hello(): return 0')
            rows.append(dict(task='hello',arm=arm,path=folder.name,error=None,
                grade=dict(passed=i>1,output='fixture fail'),
                calls=[dict(usage=dict(prompt_tokens=10,completion_tokens=2))]))
    write_json(primary/'results.json',rows)
    monkeypatch.setattr(repair,'source_hashes',lambda:{})
    monkeypatch.setattr(repair,'local_json',lambda *a:{})
    dispatched=[]
    def query(messages, maximum, timeout, path):
        dispatched.append(path)
        content='def hello(): return 1' if path.parent.name.endswith('-0') else 'def hello(): return 0'
        record=dict(usage=dict(prompt_tokens=5,completion_tokens=3),unknown_reason=None,
                    seconds=.1,response=dict(choices=[dict(finish_reason='stop')]))
        write_json(path,record)
        return content,record
    monkeypatch.setattr(repair,'query',query)
    monkeypatch.setattr(repair,'grade',lambda code,*a,**kw:dict(passed='return 1' in code,output='fixture fail',test_count=1))
    output=tmp_path/'repair'
    repair.run(primary,output,upstream)
    result=json.loads((output/'results.json').read_text())
    assert len(dispatched)==9  # Three arms: one success plus two failed calls each.
    assert all(len(r['rounds'])==0 for r in result if r['original_passed'])
    assert all(len(r['rounds'])<=2 for r in result)
    summary=json.loads((output/'summary.json').read_text())
    assert all(r['final_passed']==5 and r['repair_calls']==3 for r in summary)
    assert all(r['cumulative_total_tokens']==6*12+3*8 for r in summary)
    assert all(r['cumulative_tokens_per_correct_answer']==96/5 for r in summary)

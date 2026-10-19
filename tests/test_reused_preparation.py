import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import launch_benchmark_mission as mission


def test_reuse_skips_only_verified_preparation_steps(tmp_path):
    paths=mission.paths(tmp_path,12,5)
    assert [stage for stage,_ in mission.plan(paths,'binding',{'transport','latency','hallucination'})]==['image','grade','context']
    assert [stage for stage,_ in mission.plan(paths,'binding',{'hallucination'})]==['image','grade','context','transport','latency']


@pytest.fixture
def retained(tmp_path,monkeypatch):
    root=tmp_path/'repo';corpus=root/'benchmarks/current_local/hallucination-cases-v2.json'
    corpus.parent.mkdir(parents=True);corpus.write_text('fixture corpus')
    monkeypatch.setattr(mission,'ROOT',root)
    folder=tmp_path/'retained';(folder/'frozen-inputs').mkdir(parents=True);(folder/'calls').mkdir()
    (folder/'frozen-inputs/source.py').write_text('fixture source')
    (folder/'freeze.json').write_text(json.dumps(dict(hashes={'source.py':hashlib.sha256(b'fixture source').hexdigest()})))
    (folder/'diagnostic-plan.json').write_text(json.dumps(dict(corpus_version=2,corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest())))
    rows=[]
    for index in range(12):
        path=folder/f'calls/{index}.json';path.write_text(json.dumps(dict(usage={'total_tokens':1})))
        rows.append(dict(call=f'calls/{index}.json',call_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (folder/'result.json').write_text(json.dumps(dict(complete=True,passed=True,physical_calls=12,rows=rows)))
    return folder


def test_completed_diagnostic_is_read_only_reused(retained):
    before={str(p):p.read_bytes() for p in retained.rglob('*') if p.is_file()}
    assert mission.retained_diagnostic(retained)==retained
    assert before=={str(p):p.read_bytes() for p in retained.rglob('*') if p.is_file()}


@pytest.mark.parametrize('change',['call','source','corpus','incomplete','rows','escape'])
def test_reused_diagnostic_cannot_hide_changed_or_incomplete_evidence(retained,change):
    if change=='call':(retained/'calls/0.json').write_text('{}')
    elif change=='source':(retained/'frozen-inputs/source.py').write_text('changed')
    elif change=='corpus':
        path=retained/'diagnostic-plan.json';value=json.loads(path.read_text());value['corpus_version']=1;path.write_text(json.dumps(value))
    else:
        path=retained/'result.json';value=json.loads(path.read_text())
        if change=='incomplete':value['complete']=False
        elif change=='rows':value['rows'].pop()
        else:value['rows'][0]['call']='../outside'
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):mission.retained_diagnostic(retained)

"""Economic reporting must preserve failed work and unknown native usage."""
import importlib.util
import io
import tarfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('long_report', Path(__file__).parents[1]/'scripts/report_long_horizon.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_failed_known_call_still_counts():
    calls = [dict(usage=dict(prompt_tokens=20,completion_tokens=4,total_tokens=24),seconds=2,error='response_limit')]
    result = module.usage(calls)
    assert result['total_tokens'] == 24
    assert result['calls'] == 1 and result['http_seconds'] == 2

def test_unknown_call_prevents_complete_cost_claim():
    calls = [dict(usage=dict(prompt_tokens=20,completion_tokens=4,total_tokens=24),seconds=2),dict(usage=None,seconds=5)]
    result = module.usage(calls)
    assert result['total_tokens'] is None and result['input_tokens'] is None
    assert result['unknown_calls'] == 1 and result['calls'] == 2
    assert result['http_seconds'] == 7

def test_repair_source_change_ignores_archive_timestamp(tmp_path):
    def make(name,content,mtime):
        path=tmp_path/name
        with tarfile.open(path,'w') as archive:
            member=tarfile.TarInfo('tinydb/feature.py');member.size=len(content);member.mtime=mtime
            archive.addfile(member,io.BytesIO(content))
        return path
    first=make('first.tar',b'x = 1\n',1)
    same=make('same.tar',b'x = 1\n',2)
    changed=make('changed.tar',b'x = 2\n',2)
    assert module.source_digest(first)==module.source_digest(same)
    assert module.source_digest(first)!=module.source_digest(changed)

def test_native_decode_rate_excludes_prefill_first_token():
    calls=[dict(seconds=2,response={'timings':dict(prompt_n=100,prompt_ms=500,predicted_n=11,predicted_ms=1000)})]
    result=module.runtime(calls)
    assert result['weighted_prompt_tokens_per_second']==200
    assert result['weighted_decode_tokens_per_second']==10
    assert result['p95_http_seconds'] is None

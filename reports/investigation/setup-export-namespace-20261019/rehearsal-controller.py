from pathlib import Path
import json,hashlib,sys,datetime
root=Path(__file__).resolve().parent
primary=root/'work/spec-kit-aee-benchmark'; publication=root/'work/benchmark-results-publication'
sys.path.insert(0,str(publication/'scripts'))
import report_current,report_repeated
report_repeated.ROOT=primary
sources=sorted(p for p in primary.glob('artifacts/current-representative-*/tinydb-spec_kit_aee') if (p/'calls').is_dir() and (p/'freeze.json').is_file())
out=primary/'artifacts/setup-export-real-rehearsal-01';out.mkdir(exist_ok=False)
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for f in sources for p in f.rglob('*') if p.is_file()}
result=report_current.setup_inventory(sources,out)
assert len(result['sources'])==len(set(result['sources']))==len(sources)==5
archived=list((out/'setup-evidence').iterdir());assert len(archived)==5
expected={}
for folder in sources:
 for p in folder.rglob('call-*.json'):
  v=json.loads(p.read_bytes());identity=(v.get('response') or {}).get('id') or hashlib.sha256(p.read_bytes()).hexdigest();expected[identity]=v
assert result['physical_calls']==len(expected)
for folder in archived:
 frozen=json.loads((folder/'freeze.json').read_text())
 for name,sha in frozen['hashes'].items():assert hashlib.sha256((folder/'frozen-inputs'/name).read_bytes()).hexdigest()==sha
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in before.items())
summary=dict(passed=True,source_archives=len(sources),unique_archive_names=result['sources'],physical_calls=result['physical_calls'],by_model=result['by_model'],source_files_unchanged=len(before),inference_calls=0,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Real closed readiness04..08 folders exported under fixed report-only namespaces; active study04 source/data not edited. No new model request.')
(out/'rehearsal-proof.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))

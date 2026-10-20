"""Project the four preregistered upstream tasks into a fresh controller bundle.

No inference, resource creation, downloads or credential loading. Author gold
stays in controller-only files; actor-public contains only repo/task facts.
PyArrow is needed only for this explicit preparation command, not normal CI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT=Path(__file__).resolve().parents[1]
PARQUET_SHA='d775855a031b0fb5932ff7fdf4512ce733fbc6716528395bf15cbad22df5d2c3'
ARROW_SHA='74e7c63160ada4ceba71d5d89a9bb7c9794f4574b384458d546eb65cdb730520'
FB_PACKAGE_SHA='9e7b41daf55fd4f7bc564848bbcf80e1d82130a09b20f517e9d7fc68dff9cd15'
SWE_PACKAGE_SHA='52d5b8f6b134d0b9333c0cc95cffceb4aa0c97a4a9570619e4a48f1996d5683f'
MERGE_SHA='518160e466bb749c54697f439249ed21ff9bc22c6df09159c805f867350978b8'
EXPECTED_IDS=(
    'pandas-dev__pandas.82fa2715.test_list_accessor.7ab0b2ea.lv1',
    'astropy__astropy.b0db0daa.test_quantity_erfa_ufuncs.3fc54395.lv1',
    'dask__dask_2023.6.0_2023.6.1',
    'dask__dask_2023.6.1_2023.7.0',
)


def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(value,handle,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        handle.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parquet',type=Path,required=True)
    p.add_argument('--arrow',type=Path,required=True)
    p.add_argument('--featurebench-package-manifest',type=Path,required=True)
    p.add_argument('--swe-package-manifest',type=Path,required=True)
    p.add_argument('--official-merge-helper',type=Path,required=True)
    p.add_argument('--readiness-index',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert digest(a.parquet)==PARQUET_SHA and digest(a.arrow)==ARROW_SHA
    assert digest(a.featurebench_package_manifest)==FB_PACKAGE_SHA
    assert digest(a.swe_package_manifest)==SWE_PACKAGE_SHA
    assert digest(a.official_merge_helper)==MERGE_SHA
    # No implicit installation or import of an inference provider.
    import pyarrow as pa
    import pyarrow.ipc as ipc
    import pyarrow.parquet as pq
    fb=pq.read_table(a.parquet).to_pylist()
    with pa.memory_map(str(a.arrow),'r') as handle:
        swe=ipc.open_stream(handle).read_all().to_pylist()
    registration=json.loads((ROOT/'benchmarks/upstream-coding/registration-draft-v1.json').read_text())
    assert tuple(t['id'] for t in registration['tasks'])==EXPECTED_IDS
    expected_fb=json.loads(a.featurebench_package_manifest.read_text())
    expected_swe=json.loads(a.swe_package_manifest.read_text())
    assert len(expected_fb)==113 and len(expected_swe)==74
    readiness=json.loads(a.readiness_index.read_text())
    if readiness.get('schema')!='upstream-coding-readiness-v1' or not readiness.get('files'):
        raise ValueError('explicit resource/control provenance index required')
    evidence_root=a.readiness_index.parent.resolve()
    for name,expected in readiness['files'].items():
        path=(evidence_root/name).resolve()
        if not path.is_relative_to(evidence_root) or digest(path)!=expected:
            raise ValueError('resource/control provenance input changed')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(evidence_root,out/'resource-readiness')
    controls=out/'grader';controls.mkdir()
    for source,name in [(a.featurebench_package_manifest,'featurebench-package.json'),
                        (a.swe_package_manifest,'swe-package.json'),
                        (a.official_merge_helper,'official_merge_patches.py')]:
        if source.is_symlink():raise ValueError('source ownership input may not be a symlink')
        shutil.copyfile(source,controls/name)
    rows=[]
    for index,spec in enumerate(registration['tasks']):
        selected=[r for r in (fb if index<2 else swe) if r['instance_id']==spec['id']]
        assert len(selected)==1
        raw=selected[0];directory=out/('case-%02d'%index);directory.mkdir()
        public={key:raw[key] for key in ('repo','problem_statement')}
        assert isinstance(public['problem_statement'],str) and public['problem_statement'].strip()
        write(directory/'controller-full-row.json',raw)
        write(directory/'actor-public.json',public)
        (directory/'public-task.txt').write_bytes(public['problem_statement'].encode('utf-8'))
        rows.append(dict(index=index,instance_id=spec['id'],repo=raw['repo'],
            kind='FeatureBench' if index<2 else 'SWE-EVO',image_id=spec['image'],
            controller_row_sha256=digest(directory/'controller-full-row.json'),
            public_sha256=digest(directory/'actor-public.json'),
            public_task_sha256=digest(directory/'public-task.txt'),
            actor_fields=['repo','problem_statement']))
    write(out/'registration-draft.json',registration)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    write(out/'manifest.json',dict(status='PREPARATION ONLY; not model admission',source_head=head,
        source_was_dirty=dirty,
        source_script_sha256=digest(Path(__file__)),model_calls=0,rows=rows,
        source_datasets=dict(FeatureBench=PARQUET_SHA,SWE_EVO=ARROW_SHA),
        grader_inputs={p.name:digest(p) for p in controls.iterdir()},
        exclusion_boundary=registration.get('unadmitted_candidates',[]),
        scope='Exact original public-task bytes; full rows/gold confined to trusted controller bundle. No solver or study admission.'))
    print(json.dumps(dict(prepared=str(out),tasks=len(rows),model_calls=0,manifest_sha256=digest(out/'manifest.json'))))


if __name__=='__main__':main()

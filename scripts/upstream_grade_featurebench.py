"""Independent FeatureBench checkpoint grading via the tested resource-only adapter. No inference."""
from pathlib import Path
import datetime, hashlib, json, sysconfig
import docker, pandas as pd
from featurebench.harness.run_evaluation import run_instance
from featurebench.harness.utils import preprocess_hf_patch,get_docker_image_name,parse_repo_settings,get_docker_runtime_config
from featurebench.harness.constants import KEY_INSTANCE_ID,KEY_PREDICTION

control=Path('/control');out=Path('/results');plan=json.loads((control/'plan.json').read_text())
with (out/'started.json').open('x') as f:json.dump({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan_sha256':hashlib.sha256((control/'plan.json').read_bytes()).hexdigest(),'model_calls':0},f)
expected=json.loads((control/'expected-grader-package.json').read_text())
def package_hashes():
    folder=Path(sysconfig.get_paths()['purelib'])/'featurebench'
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert package_hashes()==expected
assert hashlib.sha256((control/'input.json').read_bytes()).hexdigest()==plan['input_sha256']
assert hashlib.sha256((control/'run.py').read_bytes()).hexdigest()==plan['controller_sha256']
input_row=json.loads((control/'input.json').read_text());assert input_row['instance_id'].endswith('.lv1');input_row['level']=1
row=pd.Series(input_row);assert row['instance_id']==plan['instance_id']
real=docker.from_env();image=real.images.get(plan['image']);assert plan['image']==image.id or plan['image'] in image.attrs['RepoDigests']
requested=get_docker_image_name(row);created=[]
class Images:
    def get(self,name):
        assert name in (requested,plan['image'],image.id),'Unregistered image'
        return real.images.get(image.id)
    def pull(self,*args,**kwargs):raise RuntimeError('No mutable or unknown image pulls allowed')
class Containers:
    def get(self,name):
        try:real.containers.get(name)
        except docker.errors.NotFound:raise
        raise RuntimeError('Container name collision; refusing existing-container mutation')
    def run(self,image_ref,*args,**kwargs):
        assert image_ref==requested and not kwargs.get('device_requests')
        kwargs.update(nano_cpus=2_000_000_000,mem_limit='8g',pids_limit=256,network_mode='none',network_disabled=True,cap_drop=['ALL'],labels={'purpose':plan['control_id'],'model_calls':'0'})
        c=real.containers.run(image.id,*args,**kwargs);c.reload();host=c.attrs['HostConfig']
        assert host['Memory']==8*1024**3 and host['NanoCpus']==2_000_000_000 and host['NetworkMode']=='none'
        if plan.get('resource_sha256'):
            status,output=c.exec_run(['sha256sum',plan['resource_path']])
            assert status==0 and output.decode().split()[0]==plan['resource_sha256']
        created.append({'id':c.id,'image_id':c.image.id,'memory':host['Memory'],'nano_cpus':host['NanoCpus'],'network':'none'})
        return c
class Client:
    images=Images();containers=Containers()
docker.from_env=lambda:Client()
mode='retained_candidate'
raw=(control/'candidate.patch').read_bytes();assert hashlib.sha256(raw).hexdigest()==plan['candidate_sha256']
result={'model_calls':0,'control':'retained candidate checkpoint, independent upstream grade','coding_campaign_admitted':False,'grade_execution_complete':False}
try:
    config=get_docker_runtime_config(parse_repo_settings(row));assert not config.get('need_gpu')
    patch=raw.decode('utf-8')  # Do not reverse/preprocess a solver patch as gold.
    prediction={KEY_INSTANCE_ID:row['instance_id'],KEY_PREDICTION:patch}
    result['run']=run_instance(row,prediction,out,timeout=plan['timeout_seconds'],docker_runtime_config=config)
    assert package_hashes()==expected
    result.update(created=created,grader_package_files_verified=len(expected),candidate_patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),candidate_patch_bytes=len(patch.encode()),mode=mode)
    result['grade_execution_complete']=bool(result['run'].get('completed') and not result['run'].get('error') )
except BaseException as exc:result['error']=repr(exc)
finally:
    result['ended_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if not result.get('grade_execution_complete'):raise SystemExit(1)

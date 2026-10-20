"""Independent retained SWE-EVO checkpoint grade; no inference or candidate changes."""
from pathlib import Path
import json, hashlib, datetime, sys, copy
import docker
import swebench
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS, KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION
from swebench.harness.test_spec.test_spec import TestSpec
from swebench.harness.test_spec.python import make_eval_script_list_py
from swebench.harness.run_evaluation import run_instance
import swebench.harness.run_evaluation as upstream_evaluation
from swebench.harness.grading import get_logs_eval
import sysconfig,sys
from official_merge_patches import merge_patches

out=Path('/results');control=Path('/control');plan=json.loads((control/'plan.json').read_text());row=json.loads((control/'input.json').read_text())
started=out/'started.json'
with started.open('x') as f: json.dump({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan_sha256':hashlib.sha256((control/'plan.json').read_bytes()).hexdigest(),'input_sha256':hashlib.sha256((control/'input.json').read_bytes()).hexdigest(),'model_calls':0},f)
def package_hashes():
 root=Path(sysconfig.get_paths()['purelib'])/'swebench'
 return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
expected=json.loads((control/'expected-grader-package.json').read_text());assert package_hashes()==expected
assert hashlib.sha256((control/'run.py').read_bytes()).hexdigest()==plan['controller_sha256']
assert hashlib.sha256((control/'input.json').read_bytes()).hexdigest()==plan['input_sha256']
result={'model_calls':0,'control':'independent retained candidate grade','grade_execution_complete':False,'coding_campaign_admitted':False}
try:
 assert swebench.__version__=='4.0.5'
 # Strict source-fidelity adaptation: one atomic apply, no reject/fuzz retries.
 upstream_evaluation.GIT_APPLY_CMDS=['git apply --verbose']
 specs=MAP_REPO_VERSION_TO_SPECS[row['repo']][row['version']]
 f2p=json.loads(row['FAIL_TO_PASS']) if isinstance(row['FAIL_TO_PASS'],str) else row['FAIL_TO_PASS'];p2p=json.loads(row['PASS_TO_PASS']) if isinstance(row['PASS_TO_PASS'],str) else row['PASS_TO_PASS'];assert (len(f2p),len(p2p))==tuple(plan['expected_test_counts'])
 script=make_eval_script_list_py(row,specs,'testbed','/testbed',row['base_commit'],row['test_patch'])
 script=[item.replace('pytest ','pytest -x ',1) if item.startswith('pytest ') else item for item in script]
 spec=TestSpec(instance_id=row['instance_id'],repo=row['repo'],version=row['version'],repo_script_list=[],env_script_list=[],eval_script_list=script,arch='x86_64',FAIL_TO_PASS=f2p,PASS_TO_PASS=p2p,language='py',docker_specs=copy.deepcopy(specs.get('docker_specs',{})),namespace=plan['control_id'])
 (out/'official-eval.sh').write_text(spec.eval_script)
 real=docker.from_env();image=real.images.get(plan['image']);assert plan['image']==image.id or plan['image'] in image.attrs['RepoDigests'];alias=spec.instance_image_key
 try: real.images.get(alias)
 except docker.errors.ImageNotFound: pass
 else: raise RuntimeError('Fresh local alias already exists; refusing overwrite/retry')
 image.tag(alias);assert real.images.get(alias).id==image.id
 created=[]
 class Containers:
  def create(self,*args,**kwargs):
   assert kwargs['image']==alias and real.images.get(alias).id==image.id
   assert not kwargs.get('cap_add')
   kwargs.update(cpuset_cpus='0,1',environment={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'},nano_cpus=2_000_000_000,mem_limit='4g',pids_limit=256,network_disabled=False,network_mode='none',cap_drop=['ALL'],labels={'purpose':plan['control_id'],'model_calls':'0'})
   container=real.containers.create(*args,**kwargs);container.reload();h=container.attrs['HostConfig'];assert h['Memory']==4*1024**3 and h['NanoCpus']==2_000_000_000 and h['NetworkMode']=='none' and container.attrs['Config'].get('NetworkDisabled',False) is False
   assert h['CpusetCpus']=='0,1';created.append({'cpuset_cpus':h['CpusetCpus'],'environment':container.attrs['Config']['Env'],'id':container.id,'image_id':container.image.id,'memory':h['Memory'],'nano_cpus':h['NanoCpus'],'network_mode':h['NetworkMode']});return container
 class Client:
  containers=Containers()
  def __getattr__(self,name):return getattr(real,name)
 candidate=(control/'candidate.patch').read_bytes();assert hashlib.sha256(candidate).hexdigest()==plan['candidate_sha256']
 test_part=merge_patches('',row['test_patch'])
 # Preserve literal candidate content, including CR bytes; the upstream merge
 # normalizes both operands. Test bytes retain their original upstream path.
 merged=test_part+('\n' if test_part else '')+candidate.decode('utf-8')
 if not merged.endswith('\n'):merged+='\n'
 pred={KEY_INSTANCE_ID:row['instance_id'],KEY_MODEL:'retained-candidate',KEY_PREDICTION:merged}
 result['literal_merged_patch_sha256']=hashlib.sha256(merged.encode('utf-8')).hexdigest()
 result['patch_application']='single atomic original git apply; no reject/fuzz/retry'
 result['run']=run_instance(spec,pred,False,False,Client(),plan['control_id'],timeout=plan['timeout_seconds'],base_commit=row['base_commit'])
 result.update(created=created,image_id=image.id,local_alias=alias,official_package=swebench.__file__)
 reports=list((out/'logs').rglob('report.json'));result['reports']=[str(p.relative_to(out)) for p in reports]
 log=next((out/'logs').rglob('test_output.txt'),None)
 if log is None:
  result['original_instance_logs']=[str(p.relative_to(out)) for p in (out/'logs').rglob('run_instance.log')]
  raise RuntimeError('Upstream evaluation produced no test output; original instance failure logs retained')
 observed,log_error=get_logs_eval(spec,str(log));missing=sorted((set(f2p)|set(p2p))-set(observed));text=log.read_text(errors='replace');install_errors=[line for line in text.splitlines() if line.lstrip().startswith(('ERROR: Could not','ERROR: No matching distribution','ERROR: Failed building'))];assert package_hashes()==expected
 result.update(expected_tests=len(set(f2p)|set(p2p)),observed_expected_tests=len((set(f2p)|set(p2p))&set(observed)),missing_expected_tests=len(missing),install_errors=install_errors,grader_package_files_verified=len(expected),grader_image_id=plan['grader_image_id'],candidate_patch_bytes=len(candidate),candidate_patch_sha256=hashlib.sha256(candidate).hexdigest(),source_test_patch_bytes=len(row['test_patch'].encode()))
 result['grade_execution_complete']=bool(result['run'].get('completed') and not install_errors)
 result['all_required_IDs_observed']=not missing
 result['observed_required_statuses']={key:observed.get(key) for key in sorted(set(f2p)|set(p2p))}
 result['official_resolved_requires_independent_audit']=bool(result['run'].get('resolved'))
except BaseException as exc:
 result['error']=repr(exc)
finally:
 result['ended_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if not result.get('grade_execution_complete'):raise SystemExit(1)

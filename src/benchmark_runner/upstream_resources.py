"""Owned offline task resources; no model/service loading or source execution on host."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .upstream_agent_adapter import AdmissionError, write_exclusive
from .upstream_docker_transport import PREFIX, StdinDockerBridge, task_environment
from .upstream_snapshot import capture_snapshot


FEATUREBENCH_GRADER = 'sha256:d62c9102f060d774fcb2ab8c25854829c827ecf4049e9c31e351d69e9555fcf8'


def _inspect(name):
    result = subprocess.run(['docker','inspect','--format','{{.Id}}|{{index .Config.Labels "purpose"}}',name],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        error = result.stderr.lower()
        if 'no such object' in error or 'no such container' in error:
            return None
        raise AdmissionError('Docker ownership inspection failed: '+result.stderr)
    fields = result.stdout.strip().split('|')
    if len(fields)!=2 or not re.fullmatch('[0-9a-f]{64}',fields[0]):
        raise AdmissionError('malformed Docker ownership observation')
    return fields


def _remove_owned(name, purpose):
    found = _inspect(name)
    if found is None:
        return
    if found[1] != purpose:
        raise AdmissionError('refusing cleanup of an unowned container')
    subprocess.run(['docker','rm','-f',found[0]],capture_output=True,check=True,timeout=60)
    if _inspect(found[0]) is not None:
        raise AdmissionError('owned container still present after cleanup')


class TaskResource:
    """Create and prepare one fresh actor; use as a context manager.

    Inputs/package ownership and selected image must already be in the study
    freeze. The full upstream row remains on the trusted controller only.
    """
    def __init__(self, *, upstream, source_root, out, row_path, row_sha256,
                 expected_featurebench_package, package_manifest_sha256,
                 image_id, kind, purpose):
        if kind not in ('FeatureBench','SWE-EVO') or not re.fullmatch('sha256:[0-9a-f]{64}',image_id):
            raise AdmissionError('registered upstream kind and immutable image required')
        if not re.fullmatch('[a-z0-9][a-z0-9-]{1,90}',purpose):
            raise AdmissionError('bounded owned resource namespace required')
        self.upstream,self.root,self.out=upstream,Path(source_root),Path(out)
        self.row_path,self.expected=Path(row_path),Path(expected_featurebench_package)
        if self.row_path.is_symlink() or self.expected.is_symlink():
            raise AdmissionError('frozen input files must not be symlinks')
        if hashlib.sha256(self.row_path.read_bytes()).hexdigest()!=row_sha256:
            raise AdmissionError('frozen upstream row changed')
        if hashlib.sha256(self.expected.read_bytes()).hexdigest()!=package_manifest_sha256:
            raise AdmissionError('pinned upstream package manifest changed')
        self.row_sha,self.image,self.kind,self.purpose=row_sha256,image_id,kind,purpose
        self.environment=None
        self.prepared=None
        self.initial=None

    def __enter__(self):
        self.out.mkdir(parents=True,exist_ok=False)
        control=self.out/'preparation'
        control.mkdir();(control/'results').mkdir()
        (control/'input.json').write_bytes(self.row_path.read_bytes())
        (control/'expected-featurebench-package.json').write_bytes(self.expected.read_bytes())
        source=self.root/'scripts/upstream_prepare_task.py'
        (control/'run.py').write_bytes(source.read_bytes())
        memory=8 if self.kind=='FeatureBench' else 4
        try:
            self.environment=self.upstream.DockerEnvironment(image=self.image,cwd='/testbed',
                interpreter=PREFIX+['/bin/bash','-c'],env=task_environment(),
                run_args=['--rm','--pull=never','--network=none','--cpus=2','--cpuset-cpus=0,1',
                    '--memory='+str(memory)+'g','--pids-limit=256','--security-opt=no-new-privileges:true',
                    '--cap-drop=NET_RAW','--label=purpose='+self.purpose],
                container_timeout='5h',timeout=600,pull_timeout=30)
            cid=self.environment.container_id
            if not re.fullmatch('[0-9a-f]{64}',cid or ''):
                raise AdmissionError('owned actor ID missing')
            plan=dict(container_id=cid,image_id=self.image,purpose=self.purpose,kind=self.kind,
                memory_bytes=memory*1024**3,preparer_sha256=hashlib.sha256((control/'run.py').read_bytes()).hexdigest(),
                input_sha256=self.row_sha)
            write_exclusive(control/'plan.json',plan)
            name=self.purpose+'-preparer'
            if _inspect(name) is not None:
                raise AdmissionError('preparer name collision; no retry or overwrite')
            argv=['docker','run','--rm','--name',name,'--label','purpose='+name,'--pull=never',
                '--network=none','--cpus=1','--memory=2g','--pids-limit=256','--entrypoint','python',
                '--mount','type=bind,source='+control.as_posix()+',target=/control,readonly',
                '--mount','type=bind,source='+(control/'results').as_posix()+',target=/results',
                '--mount','type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
                FEATUREBENCH_GRADER,'/control/run.py']
            write_exclusive(control/'argv.json',argv)
            try:
                with (control/'controller.log').open('xb') as handle:
                    result=subprocess.run(argv,stdout=handle,stderr=subprocess.STDOUT,timeout=600)
                if result.returncode:
                    raise AdmissionError('upstream resource preparation failed; retain controller output')
            finally:
                _remove_owned(name,name)
            self.prepared=json.loads((control/'results/prepared.json').read_text())
            row=json.loads((control/'input.json').read_text())
            if not (self.prepared['prepared'] and self.prepared['container_id']==cid
                    and self.prepared['image_id']==self.image and self.prepared['input_sha256']==self.row_sha
                    and self.prepared['instance_id']==row['instance_id']):
                raise AdmissionError('prepared resource input/source mismatch')
            bridge=StdinDockerBridge(self.environment,reader_python='/opt/miniconda3/envs/testbed/bin/python')
            self.initial=capture_snapshot(bridge,self.out/'initial-source',
                baseline_commit=self.prepared['baseline_commit'],reader_python='/opt/miniconda3/envs/testbed/bin/python')
            write_exclusive(self.out/'resource.json',dict(prepared=self.prepared,
                initial_literal_tree=self.initial['candidate_tree'],
                initial_git_normalization_difference_bytes=self.initial['patch_bytes'],
                kind=self.kind,purpose=self.purpose,
                scope='Declared resource preparation/initial literal source only; not a model or grade result.'))
            return self
        except BaseException as original:
            try:
                self.close()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup('Resource preparation and owned cleanup both failed',[original,cleanup_error])
            raise

    def close(self):
        if self.environment is not None and self.environment.container_id:
            cid=self.environment.container_id
            # Disable upstream's Unix-only destructor before any error path.
            self.environment.container_id=None
            _remove_owned(cid,self.purpose)
            write_exclusive(self.out/'owned-cleanup.json',dict(container_id=cid,purpose=self.purpose,observed_absent=True))

    def __exit__(self,kind,value,traceback):
        try:
            self.close()
        except BaseException as cleanup_error:
            if value is not None:
                raise BaseExceptionGroup('Original task event and owned cleanup failure',[value,cleanup_error])
            raise
        return False

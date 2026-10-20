"""Lossless stdin delivery for upstream bash actions on a Windows controller.

Large commands exceed Windows CreateProcess argv limits. Send exact UTF-8 over
stdin to an isolated, unprivileged decoder, then exec the same bash -c command
with /dev/null stdin. No command rewriting, retries, service control or scoring.
"""
import os
import subprocess
import time

from .upstream_agent_adapter import AdmissionError

DECODER="import os,sys;raw=sys.stdin.buffer.read();fd=os.open('/dev/null',os.O_RDONLY);os.dup2(fd,0);os.close(fd);os.execv('/bin/bash',['/bin/bash','-c',raw.decode('utf-8')])"
PREFIX=['/usr/bin/setpriv','--reuid=fbagent','--regid=fbagent','--init-groups','--no-new-privs']


def task_environment():
    """Use the registered task env without sourcing root/actor shell scripts."""
    return dict(PATH='/opt/miniconda3/envs/testbed/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        HOME='/home/fbagent', BASH_ENV='/dev/null', ENV='/dev/null',
        PAGER='cat', MANPAGER='cat', LESS='-R',
        PIP_PROGRESS_BAR='off', TQDM_DISABLE='1',
        OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')


class StdinDockerBridge:
    def __init__(self, upstream_environment, *, reader_python, deadline=None):
        self.env,self.config=upstream_environment,upstream_environment.config
        if self.config.interpreter!=PREFIX+['/bin/bash','-c'] or self.config.forward_env:
            raise AdmissionError('fixed UID interpreter and no host environment forwarding required')
        if reader_python not in ('/usr/bin/python3','/opt/miniconda3/envs/testbed/bin/python'):
            raise AdmissionError('registered immutable container interpreter required')
        self.reader_python,self.deadline=reader_python,deadline

    def get_template_vars(self,**kwargs):return self.env.get_template_vars(**kwargs)

    def serialize(self):
        value=self.env.serialize()
        value['execution_transport']=dict(kind='lossless-utf8-stdin-to-bash-c',decoder=DECODER,
            interpreter=self.reader_python,original_upstream_file_unchanged=True,
            boundary='Execution I/O adaptation, not unmodified upstream execute or protected identity.')
        return value

    def execute(self,action,cwd='',*,timeout=None):
        command=action.get('command','')
        if not isinstance(command,str) or not command.strip():
            raise AdmissionError('nonempty literal native bash command required')
        if self.env.container_id is None:raise AdmissionError('no owned task container')
        actual_timeout=self.config.timeout if timeout is None else min(timeout,self.config.timeout)
        if self.deadline is not None:
            actual_timeout=min(actual_timeout,self.deadline-time.monotonic())
        if actual_timeout<=0:raise AdmissionError('task wall budget exhausted before action')
        argv=[self.config.executable,'exec','-i','-w',cwd or self.config.cwd]
        for key,value in self.config.env.items():argv+=['-e',f'{key}={value}']
        argv += [self.env.container_id,*PREFIX,self.reader_python,'-I','-S','-c',DECODER]
        try:
            result=subprocess.run(argv,input=command.encode('utf-8'),stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,timeout=actual_timeout,check=False)
            output=dict(output=result.stdout.decode('utf-8',errors='replace'),returncode=result.returncode,exception_info='',
                extra=dict(transport='lossless-utf8-stdin-to-bash-c'))
        except Exception as exc:
            raw=getattr(exc,'output',b'') or b''
            output=dict(output=raw.decode('utf-8',errors='replace') if isinstance(raw,bytes) else raw,
                returncode=-1,exception_info=str(exc),extra=dict(exception_type=type(exc).__name__,transport='lossless-utf8-stdin-to-bash-c'))
        self.env._check_finished(output)
        return output

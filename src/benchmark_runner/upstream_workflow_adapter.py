"""Trusted host-managed SpecKit helpers and released AEE phase feedback.

Only bounded proposal bytes cross back from the task container. Agent-modified
scripts are never executed on the host. This is a declared workflow adaptation,
not a protected identity service or independent correctness/acceptance oracle.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import base64
import subprocess
import sys
import re

from .project_assessment import assess_project
from .store import Store, canonical, utc, write_json
from .verified_write import write_bytes_verified

PHASES=('constitution','specify','plan','tasks')
DOCUMENTS={'constitution':'.specify/memory/constitution.md',
    'specify':'specs/001-upstream/spec.md','plan':'specs/001-upstream/plan.md',
    'tasks':'specs/001-upstream/tasks.md','baseline':'notes/work-brief.md'}


class WorkflowFailure(RuntimeError):
    pass


DOCUMENT_READER = r'''
import os,sys,stat,base64,json
root='/testbed'
assert os.geteuid()==999,'fixed unprivileged reader required'
status=open('/proc/self/status').read()
assert 'CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status
relative=sys.argv[1]
assert not relative.startswith('/') and '..' not in relative.split('/')
fd=os.open(root+'/'+relative,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
    before=os.fstat(fd)
    actual=os.path.realpath('/proc/self/fd/'+str(fd))
    assert os.path.commonpath([root,actual])==root and stat.S_ISREG(before.st_mode)
    raw=os.read(fd,65537)
    after=os.fstat(fd)
    print(json.dumps(dict(base64=base64.b64encode(raw).decode(),path=actual,
        size_before=before.st_size,size_after=after.st_size,
        stable_metadata=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns) and after.st_nlink>0,
        partial=len(raw)!=after.st_size,uid=os.geteuid(),isolated_python=True)))
finally:os.close(fd)
'''


def capture_document(environment, phase, out, *, reader_python, relative_path=None):
    """Fixed UID reader, isolated Python, no symlink/host extraction or scripts.

    The interpreter path must be pinned and checked non-writable during trusted
    resource preparation. This captures FD bytes, not transient immutability.
    """
    if phase not in DOCUMENTS:raise WorkflowFailure('unknown document capture phase')
    relative_path = relative_path or DOCUMENTS[phase]
    if phase in ('specify','plan','tasks'):
        filename={'specify':'spec.md','plan':'plan.md','tasks':'tasks.md'}[phase]
        valid=bool(re.fullmatch(r'specs/[0-9]{3}-upstream/'+re.escape(filename),relative_path))
    elif phase=='baseline':
        valid=bool(re.fullmatch(r'notes/work-brief(?:-[0-9]{3})?\.md',relative_path))
    else:valid=relative_path==DOCUMENTS[phase]
    if not valid:raise WorkflowFailure('path outside registered workflow document set')
    if reader_python not in ('/usr/bin/python3','/opt/miniconda3/envs/testbed/bin/python'):
        raise WorkflowFailure('unregistered trusted reader interpreter')
    required=['/usr/bin/setpriv','--reuid=fbagent','--regid=fbagent','--init-groups','--no-new-privs','/bin/bash','-c']
    if environment.config.interpreter!=required:
        raise WorkflowFailure('document reader must use the fixed unprivileged interpreter')
    command=shlex.join([reader_python,'-I','-S','-c',DOCUMENT_READER,relative_path])
    result=environment.execute(dict(command=command),cwd='/testbed',timeout=30)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    record=dict(command=command,result=result,phase=phase,
        boundary='Captured file-descriptor bytes; no semantic truth, human acceptance or transient/full-environment immutability.')
    write_json(out/f'{phase}-read.json',record,exclusive=True)
    if result.get('returncode')!=0 or result.get('exception_info'):
        raise WorkflowFailure('unprivileged document read failed; retain original output')
    value=json.loads(result['output'])
    raw=base64.b64decode(value['base64'],validate=True)
    if not value['stable_metadata']:
        raise WorkflowFailure('document changed during capture')
    return raw,{k:v for k,v in value.items() if k!='base64'}


class Workflow:
    def __init__(self, source_root, out, arm, public_task, *, continuity_root=None, prior_context=None,
                 feature_number=1):
        if arm not in ('baseline','spec_kit','spec_kit_aee'):
            raise ValueError('unknown registered treatment')
        self.source_root,self.out=Path(source_root).resolve(),Path(out).resolve()
        if type(feature_number) is not int or not 1<=feature_number<=999:
            raise WorkflowFailure('registered feature number required')
        self.feature_number=feature_number
        self.feature=f'{feature_number:03d}-upstream'
        self.paths={**DOCUMENTS}
        for phase,filename in [('specify','spec.md'),('plan','plan.md'),('tasks','tasks.md')]:
            self.paths[phase]=f'specs/{self.feature}/{filename}'
        if feature_number>1:self.paths['baseline']=f'notes/work-brief-{feature_number:03d}.md'
        self.arm,self.task=arm,public_task
        self.out.mkdir(parents=True,exist_ok=False)
        self.host=(Path(continuity_root).resolve()/'trusted-framework'
                   if continuity_root is not None and arm!='baseline' else self.out/'trusted-framework')
        existing_host=self.host.exists()
        self.host.mkdir(parents=True,exist_ok=existing_host)
        self.store=Store((Path(continuity_root).resolve() if continuity_root is not None else self.out)/'store')
        self.prior_context=prior_context
        self.identity_prefix=hashlib.sha256(str(self.out).encode()).hexdigest()[:16]
        (self.out/'public-task.txt').write_bytes(public_task.encode('utf-8'))
        self.documents={};self.phase_order=[];self.previous=None
        self.empty_git=self.out/'empty-git-config';self.empty_git.write_bytes(b'')
        self.env={k:v for k,v in os.environ.items() if k.upper() in
                  {'SYSTEMROOT','COMSPEC','PATH','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA'}}
        self.env.update(SPECIFY_INIT_DIR=str(self.host),SPECIFY_FEATURE=self.feature,
            SPECIFY_FEATURE_DIRECTORY='specs/'+self.feature,PYTHONUTF8='1',SPECKIT_AEE_AUTO_INSTALL='0',
            GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(self.empty_git),PYTHON_DOTENV_DISABLED='1')
        if arm!='baseline':
            expected={p.relative_to(self.source_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for part in ('templates','scripts/python')
                for p in (self.source_root/'.specify'/part).rglob('*')
                if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
            marker=self.host/'controller-helper-manifest.json'
            if existing_host:
                if not marker.is_file() or json.loads(marker.read_text())!=expected:
                    raise WorkflowFailure('retained trusted helper manifest differs; no host execution')
                for path,digest in expected.items():
                    target=self.host/path
                    if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
                        raise WorkflowFailure('retained host helper bytes changed; no host execution')
            else:
                for part in ('templates','scripts/python'):
                    shutil.copytree(self.source_root/'.specify'/part,self.host/'.specify'/part,
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                write_json(marker,expected,exclusive=True)
                self.command(['git','init','-q'],'git-init')
            self.command([sys.executable,str(self.host/'.specify/scripts/python/create_new_feature.py'),
                '--json','--short-name','upstream','--number',str(feature_number),'Implement the registered upstream task; complete task bytes are captured separately.'],'create-feature')
            self.command([sys.executable,str(self.host/'.specify/scripts/python/setup_plan.py'),'--json'],'setup-plan')
        self.initial={phase:hashlib.sha256((self.host/path).read_bytes()).hexdigest()
            for phase,path in self.paths.items() if (self.host/path).is_file()}

    def retain_constitution(self,raw,capture):
        """Reuse prior draft bytes, never prior human acceptance or new approval."""
        if self.arm=='baseline' or self.feature_number<=1 or self.phase_order:
            raise WorkflowFailure('constitution retention only applies at a later feature start')
        target=self.host/self.paths['constitution']
        if not target.is_file() or target.is_symlink() or target.read_bytes()!=raw:
            raise WorkflowFailure('actor/host retained constitution bytes differ')
        if capture.get('partial') or capture.get('uid')!=999 or capture.get('stable_metadata') is not True:
            raise WorkflowFailure('retained constitution capture incomplete')
        text=raw.decode('utf-8')
        if not text.strip() or len(text)>3000:raise WorkflowFailure('invalid retained constitution')
        self.documents['constitution']=text;self.phase_order.append('constitution')
        write_json(self.out/'retained-constitution.json',dict(sha256=hashlib.sha256(raw).hexdigest(),
            capture=capture,feature=self.feature,new_model_calls=0,status='unaccepted prior draft',
            boundary='Project setup retained as data; no human acceptance, independence or stage promotion transferred.'),exclusive=True)

    def command(self,argv,tag):
        log=self.out/'host-commands'/f'{tag}.json'
        start=utc()
        result=subprocess.run(argv,cwd=self.host,env=self.env,capture_output=True,timeout=60)
        write_json(log,dict(argv=argv,started_at=start,ended_at=utc(),exit_code=result.returncode,
            stdout=result.stdout.decode('utf-8',errors='replace'),stderr=result.stderr.decode('utf-8',errors='replace')),exclusive=True)
        if result.returncode:raise WorkflowFailure('trusted framework helper failed: '+tag)

    def document_contract(self,phase):
        expected=('baseline',) if self.arm=='baseline' else PHASES
        if len(self.phase_order)>=len(expected) or phase!=expected[len(self.phase_order)]:
            raise WorkflowFailure('out-of-order framework phase')
        task=dict(public_task=self.task,phase=phase,target=self.paths[phase],
            instruction='Write a concise unaccepted draft, at most 3000 characters. Preserve uncertainty and prior unresolved requirements; no invented tests, human acceptance or independent verification. Public framework templates, placeholder documents and arm-specific hook metadata are initialized in the task workspace before this phase. Trusted framework helpers and configured hooks are host-managed by the controller; do not execute their scripts or hooks in the task runtime. No human interaction is available; retain unresolved questions explicitly rather than inventing answers. Submit only after writing the declared file.',
            prior_documents=self.documents,prior_sequence_context=self.prior_context)
        if self.arm!='baseline':
            task['speckit_command']=(self.source_root/f'prompts/skills/speckit-{phase}.md').read_text(encoding='utf-8').replace('$ARGUMENTS',self.task)
            template={'constitution':'constitution-template.md','specify':'spec-template.md','plan':'plan-template.md','tasks':'tasks-template.md'}[phase]
            task['speckit_template']=(self.source_root/'.specify/templates'/template).read_text(encoding='utf-8')
        if self.previous is not None:
            task['actual_AEE_feedback']={k:self.previous.get(k) for k in ('outcome','summary','findings','next_action')}
        return task

    def receive_document(self,phase,raw,capture):
        self.document_contract(phase)
        if isinstance(raw,bytes):
            received=self.out/'received-proposals'/f'{phase}.bin'
            received.parent.mkdir(parents=True,exist_ok=True)
            saved=raw[:65537]
            with received.open('xb') as handle:handle.write(saved)
            write_json(received.with_suffix('.json'),dict(capture=capture,received_bytes=len(raw),
                retained_bytes=len(saved),retained_sha256=hashlib.sha256(saved).hexdigest(),
                retained_is_prefix=len(raw)>len(saved),
                boundary='Retained proposal input, including invalid attempts; no whole-file identity when the reader/capture is partial.'),exclusive=True)
        if not isinstance(raw,bytes) or len(raw)>65536 or b'\x00' in raw:
            raise WorkflowFailure('invalid/oversized proposed document; no truncation')
        if capture.get('partial') is True:
            raise WorkflowFailure('partial document capture cannot be treated as complete')
        text=raw.decode('utf-8')
        digest=hashlib.sha256(raw).hexdigest()
        if not text.strip() or len(text)>3000 or digest==self.initial.get(phase):
            raise WorkflowFailure('missing/unchanged/over-budget proposed document')
        target=self.host/self.paths[phase];target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_symlink():raise WorkflowFailure('host document path must not be a symlink')
        # Verified write (fleet standard, 2026-10-28): the receipt
        # below pins sha256(raw); the file must provably hold exactly
        # those bytes, so the write verifies by read-back or raises.
        write_bytes_verified(target,raw)
        write_json(self.out/'document-captures'/f'{phase}.json',dict(sha256=digest,
            bytes=len(raw),capture=capture,relative_path=self.paths[phase],
            boundary='Captured untrusted proposal bytes; not semantic proof or human acceptance.'),exclusive=True)
        self.documents[phase]=text;self.phase_order.append(phase)
        if self.arm=='spec_kit_aee' and phase in ('specify','plan','tasks'):
            self.previous=self.assess(phase,text,dict(public_task=self.task,phase=phase,
                documents=self.documents,prior_sequence_context=self.prior_context,captured_artifact_sha256=digest))
        if phase=='tasks':
            self.command([sys.executable,str(self.host/'.specify/scripts/python/check_prerequisites.py'),
                '--json','--require-spec','--require-tasks','--include-tasks'],'check-prerequisites')
        return self.previous

    def assess(self,phase,proposal,context):
        if self.arm!='spec_kit_aee':raise WorkflowFailure('AEE cannot leak into a control arm')
        identity=f'upstream-{self.identity_prefix}-{phase}'
        raw=canonical(context);ref=self.store.artifact(raw)
        if ref['sha256']!=hashlib.sha256(raw).hexdigest():
            raise WorkflowFailure('redaction changed captured context; do not assert byte identity')
        self.store.append('tools',dict(attempt_id=identity,timestamp=utc(),artifact=ref,kind='host_captured_unaccepted_proposal'))
        claims=dict(schema_version='1.0',claims=[dict(id='DRAFT-UPSTREAM-01',text='Draft workflow proposal: '+proposal,
            kind='inference',status='draft',stage='created',boundary=['This captured draft only; no independent correctness, human acceptance or protected identity.'],
            depends_on=[],conflicts_with=[],source_ref=ref['path'],uncertainty='high',
            falsification_tests=['Independent source review or required tests contradict the proposed implementation or requirements.'],
            evidence=[dict(ref=ref['path'],content_hash=ref['sha256'],source_id=ref['sha256'],kind='observed',direction='context',source_quality='primary',description='Actual captured proposal/task bytes; no semantic truth or test success is established by this capture.')])])
        value=assess_project(self.source_root,claims,phase,self.store,identity)
        if value.get('outcome') not in {'pass','warn','iterate','clarify','gather_evidence','block'}:
            raise WorkflowFailure('unknown released AEE/Evaluator outcome')
        if value['outcome']=='block':raise WorkflowFailure('actual AEE hard block; no bypass')
        return value

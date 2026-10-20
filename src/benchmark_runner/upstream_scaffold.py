"""Declare and seed public framework scaffolding before any solver action.

Never copy the controller constitution, scripts, stores, gold or credentials.
The actor's installed metadata is readable; actual helpers/hooks remain trusted
host-managed and the actor cannot supply code for host execution.
"""
import base64
import hashlib
import json
from pathlib import Path
import shlex

from .upstream_agent_adapter import AdmissionError, write_exclusive

WRITER=r'''
import os,sys,json,base64,hashlib,stat
assert os.geteuid()==999
payload=json.loads(base64.b64decode(sys.argv[1]));root='/testbed';written=[]
for item in payload:
 name=item['path'];assert not name.startswith('/') and '..' not in name.split('/')
 parent=root
 for component in name.split('/')[:-1]:
  parent=parent+'/'+component
  if os.path.lexists(parent):assert stat.S_ISDIR(os.lstat(parent).st_mode),'scaffold parent is not a literal directory'
  else:os.mkdir(parent)
 path=root+'/'+name;raw=base64.b64decode(item['base64'])
 if os.path.lexists(path):
  assert stat.S_ISREG(os.lstat(path).st_mode),'scaffold target is not a literal file'
  prior=open(path,'rb').read()
  if item['retain_existing']:
   written.append(dict(path=name,retained=True,sha256=hashlib.sha256(prior).hexdigest()));continue
  assert prior==raw,'retained public framework scaffolding changed'
 else:
  with open(path,'xb') as handle:handle.write(raw)
 if item['readonly']:os.chmod(path,0o444)
 written.append(dict(path=name,retained=False,sha256=hashlib.sha256(raw).hexdigest()))
print(json.dumps(dict(uid=os.geteuid(),files=written)))
'''


def files_for(workflow):
    if workflow.arm=='baseline':return []
    result=[]
    def add(name,raw,readonly=False,retain=False):
        result.append(dict(path=name,base64=base64.b64encode(raw).decode(),readonly=readonly,
            retain_existing=retain))
    directory=workflow.source_root/'.specify/templates'
    for source in sorted(directory.rglob('*')):
        if source.is_file():
            if source.is_symlink():raise AdmissionError('trusted template must not be a symlink')
            add('.specify/templates/'+source.relative_to(directory).as_posix(),source.read_bytes(),True)
    if workflow.arm=='spec_kit_aee':
        raw=(workflow.source_root/'.specify/extensions.yml').read_bytes()
    else:raw=b'installed: []\nsettings:\n  auto_execute_hooks: true\nhooks: {}\n'
    add('.specify/extensions.yml',raw,True)
    for phase,name in workflow.paths.items():
        if phase=='baseline':continue
        host=workflow.host/name
        template={'constitution':'constitution-template.md','specify':'spec-template.md',
                  'plan':'plan-template.md','tasks':'tasks-template.md'}[phase]
        raw=host.read_bytes() if host.is_file() else (directory/template).read_bytes()
        if phase!='constitution' or workflow.feature_number==1:
            workflow.initial[phase]=hashlib.sha256(raw).hexdigest()
        # Warm constitution is actual carried unaccepted data, never overwritten.
        add(name,raw,retain=workflow.feature_number>1 and phase=='constitution')
    return result


def seed(workflow,environment,out,reader_python):
    payload=files_for(workflow);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    write_exclusive(out/'request.json',dict(files=payload,model_calls=0,
        scope='Public pinned templates, arm-specific hook metadata and draft placeholders only. Host helpers/hooks remain controller-managed. No controller constitution, gold, scripts, stores or host credentials.'))
    if not payload:return dict(model_calls=0,files=[],arm='baseline')
    encoded=base64.b64encode(json.dumps(payload).encode()).decode()
    command=shlex.join([reader_python,'-I','-S','-c',WRITER,encoded])
    response=environment.execute(dict(command=command),timeout=60)
    write_exclusive(out/'response.json',dict(response=response,writer_sha256=hashlib.sha256(WRITER.encode()).hexdigest()))
    if response.get('returncode')!=0 or response.get('exception_info'):
        raise AdmissionError('public workflow scaffold initialization failed; no model call')
    actual=json.loads(response['output'])
    if actual['uid']!=999 or {v['path'] for v in actual['files']}!={v['path'] for v in payload}:
        raise AdmissionError('public workflow scaffold observation differs')
    for got,wanted in zip(actual['files'],payload):
        if got['path']!=wanted['path'] or (not got['retained'] and got['sha256']!=hashlib.sha256(base64.b64decode(wanted['base64'])).hexdigest()):
            raise AdmissionError('public workflow scaffold byte mismatch')
    return dict(model_calls=0,files=actual['files'],arm=workflow.arm)

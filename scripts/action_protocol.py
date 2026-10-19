"""Native actions, with explicit claim-bearing phase contracts.

Every tool branch requires its actual arguments before generation. The claim
grammar constrains shape, never truth: strict engine loading and evidence checks
still run on every returned claim. Empty evidence and draft statuses remain valid.
"""
import copy
import base64
import json
import shlex
from pathlib import PurePosixPath, PureWindowsPath

MAX_WRITE_BYTES = 64 * 1024
SHELL_SCHEMA = {'type':'object','properties':{
    'action':{'const':'shell'},'command':{'type':'string','minLength':1}},
    'required':['action','command'],'additionalProperties':False}
EXEC_SCHEMA = {'type':'object','properties':{
    'action':{'const':'exec'},'argv':{'type':'array','minItems':1,'maxItems':128,
        'items':{'type':'string','minLength':1,'maxLength':MAX_WRITE_BYTES}}},
    'required':['action','argv'],'additionalProperties':False}
WRITE_SCHEMA = {'type':'object','properties':{
    'action':{'const':'write_file'},'path':{'type':'string','minLength':1},
    'content':{'type':'string','maxLength':MAX_WRITE_BYTES}},
    'required':['action','path','content'],'additionalProperties':False}
TERMINAL_SCHEMA = {'type':'object','properties':{
    'action':{'type':'string','enum':['done','draft']},'summary':{'type':'string'},
    'completion_asserted':{'type':['boolean','null']},
    'claims':{'type':'object','additionalProperties':True},
    'artifacts':{'type':'array','items':{'type':'string'}}},
    'required':['action'],'additionalProperties':False}
ACTION_RESPONSE_FORMAT = {'type':'json_schema','json_schema':{
    'name':'benchmark_action','strict':True,
    'schema':{'oneOf':[SHELL_SCHEMA,EXEC_SCHEMA,WRITE_SCHEMA,TERMINAL_SCHEMA]}}}


def action_response_format(requires_claims=False):
    if not requires_claims:
        return copy.deepcopy(ACTION_RESPONSE_FORMAT)
    strings = {'type': 'array', 'items': {'type': 'string'}}
    fields = {
        'id': {'type': 'string', 'minLength': 1},
        'text': {'type': 'string', 'minLength': 1},
        'kind': {'type': 'string', 'enum': ['observation', 'requirement', 'assumption', 'inference', 'hypothesis', 'decision', 'prediction', 'compliance']},
        'status': {'type': 'string', 'enum': ['draft', 'supported', 'partially_supported', 'unsupported', 'contradicted', 'unverifiable', 'superseded']},
        'stage': {'type': 'string', 'enum': ['created', 'checked', 'explained', 'accepted', 'digested']},
        'boundary': strings, 'depends_on': strings, 'conflicts_with': strings,
        'falsification_tests': strings, 'source_ref': {'type': 'string'},
        'uncertainty': {'type': 'string', 'enum': ['none', 'low', 'medium', 'high', 'insufficient_evidence']},
        'evidence': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True}},
    }
    bundle = {'type': 'object', 'properties': {
        'schema_version': {'const': '1.0'},
        'claims': {'type': 'array', 'minItems': 1, 'items': {
            'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}},
    }, 'required': ['schema_version', 'claims'], 'additionalProperties': False}
    terminal = copy.deepcopy(TERMINAL_SCHEMA)
    terminal['properties']['claims'] = bundle
    terminal['required'] = ['action', 'claims']
    return {'type': 'json_schema', 'json_schema': {
        'name': 'benchmark_claim_action', 'strict': True,
        'schema': {'oneOf': [copy.deepcopy(SHELL_SCHEMA),copy.deepcopy(EXEC_SCHEMA),copy.deepcopy(WRITE_SCHEMA),terminal]}}}


_WRITE_SCRIPT = '''import base64,hashlib,json,sys
from pathlib import Path
name=base64.b64decode(sys.argv[1],validate=True).decode('utf-8')
root=Path.cwd().resolve(strict=True)
target=root
for part in name.split('/'):
    target=target/part
    if target.is_symlink():raise ValueError('symlinked write path refused')
if not target.resolve(strict=False).is_relative_to(root):raise ValueError('write escaped sandbox root')
target.parent.mkdir(parents=True,exist_ok=True)
data=base64.b64decode(sys.argv[2],validate=True)
target.write_bytes(data)
print(json.dumps(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())))
'''


_EXEC_SCRIPT = '''import base64,json,subprocess,sys
argv=json.loads(base64.b64decode(sys.argv[1],validate=True).decode('utf-8'))
sys.exit(subprocess.run(argv,shell=False).returncode)
'''


_SHELL_SCRIPT = '''import base64,subprocess,sys
command=base64.b64decode(sys.argv[1],validate=True).decode('utf-8')
check=subprocess.run(['bash','--noprofile','--norc','-n','-c',command],capture_output=True)
# Bash can return zero for an unterminated heredoc while warning on stderr.
# Reject every parser diagnostic before executing any part of the command.
if check.returncode or check.stderr:
    sys.stderr.buffer.write(b'ShellSyntaxRejected: command was not executed. Use write_file for literal file content.\\n'+check.stderr)
    sys.exit(2)
sys.exit(subprocess.run(['bash','-lc',command]).returncode)
'''


def action_command(action):
    """Translate a tool action into one sandbox command; never run it on the host.

    Literal UTF-8 file content is transported as base64 data, not shell/Python
    source. This avoids heredoc/quote truncation without repairing model output.
    Shell remains available, with the same budgets and runtime intervention.
    """
    if action.get('action') == 'exec':
        argv=action.get('argv')
        if (not isinstance(argv,list) or not 1<=len(argv)<=128
            or any(not isinstance(arg,str) or not arg or '\x00' in arg for arg in argv)):
            raise ValueError('exec requires 1..128 nonempty NUL-free string arguments')
        data=json.dumps(argv,ensure_ascii=False).encode('utf-8')
        if len(data)>MAX_WRITE_BYTES:
            raise ValueError('exec requires bounded UTF-8 arguments')
        return 'python -c '+shlex.quote(_EXEC_SCRIPT)+' '+shlex.quote(base64.b64encode(data).decode())
    if action.get('action') == 'shell':
        command=action.get('command')
        if not isinstance(command,str) or not command.strip():
            raise ValueError('shell requires a nonempty command')
        if '\x00' in command or len(command.encode('utf-8')) > MAX_WRITE_BYTES:
            raise ValueError('shell requires bounded NUL-free UTF-8 command')
        data=base64.b64encode(command.encode('utf-8')).decode()
        return 'python -c '+shlex.quote(_SHELL_SCRIPT)+' '+shlex.quote(data)
    if action.get('action') != 'write_file':
        raise ValueError('expected exec, shell, write_file or done')
    name=action.get('path');content=action.get('content')
    # Spec Kit also names files under the fixed sandbox mount. Interpret that
    # one prefix as the same workspace; retain every canonical/symlink check.
    if isinstance(name,str) and len(name)<=4096 and name.startswith('/testbed/'):
        name=name[len('/testbed/'):]
    if (not isinstance(name,str) or not name or len(name)>4096
        or '\\' in name or ':' in name or '\x00' in name
        or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute()
        or any(part in ('','..','.') for part in name.split('/'))):
        raise ValueError('write_file requires a canonical sandbox-relative path')
    if not isinstance(content,str) or len(content.encode('utf-8'))>MAX_WRITE_BYTES:
        raise ValueError('write_file requires bounded UTF-8 content')
    # Separate binary arguments bound Linux's per-argument and bash command-size
    # limits even for Unicode and control bytes; no nested JSON expansion.
    path_data=base64.b64encode(name.encode()).decode()
    content_data=base64.b64encode(content.encode()).decode()
    return 'python -c '+shlex.quote(_WRITE_SCRIPT)+' '+shlex.quote(path_data)+' '+shlex.quote(content_data)

"""Retain candidate patches without staging files or running repository filters.

The reader executes inside the isolated task as its unprivileged UID. It hashes
literal file bytes into a temporary index, never executes actor Python/hooks,
and diffs against the separately registered baseline commit. No host extraction
or actor-provided host executable is involved. Captures are scoped observations,
not a guarantee against a concurrent malicious process or kernel compromise.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex

from .upstream_agent_adapter import AdmissionError, write_exclusive


# Python -I -S avoids the task's import path, sitecustomize and user site. This
# code must remain compatible with the selected upstream Python 3.8 runtime.
READER = r'''
import base64,hashlib,json,os,stat,subprocess,sys,tempfile
root,baseline,literal_tree=sys.argv[1:]
root=os.path.realpath(root)
assert root=='/testbed', 'registered task root required'
assert os.getuid()==999, 'registered unprivileged task UID required'
assert len(baseline)==40 and all(c in '0123456789abcdef' for c in baseline)
assert os.path.isdir(root+'/.git') and not os.path.islink(root+'/.git')
env={'PATH':'/usr/bin:/bin','HOME':'/home/fbagent','GIT_CONFIG_NOSYSTEM':'1',
     'GIT_CONFIG_GLOBAL':'/dev/null','GIT_ATTR_NOSYSTEM':'1','LC_ALL':'C'}
git=['/usr/bin/git','--git-dir='+root+'/.git','--work-tree='+root,
     '-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
     '-c','core.attributesFile=/dev/null','-c','core.sparseCheckout=false',
     '-c','core.autocrlf=false']
def run(args,data=None):
    return subprocess.run(git+args,input=data,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,check=True,env=env,cwd=root).stdout
assert run(['rev-parse',baseline+'^{commit}']).strip().decode()==baseline
if literal_tree!='-':
    assert len(literal_tree)==40 and all(c in '0123456789abcdef' for c in literal_tree)
    assert run(['rev-parse',literal_tree+'^{tree}']).strip().decode()==literal_tree
diff_base=baseline if literal_tree=='-' else literal_tree
base=run(['ls-tree','-r','--name-only','-z',baseline]).split(b'\0')
current=run(['ls-files','--cached','--others','--exclude-standard','-z']).split(b'\0')
names=sorted(set(base+current)-{b''})
assert len(names)<=200000, 'candidate file inventory limit'
rows=[];total=0;records=[]
with tempfile.TemporaryDirectory(prefix='benchmark-index-') as temporary:
    env['GIT_INDEX_FILE']=temporary+'/index'
    run(['read-tree','--empty'])
    for raw in names:
        name=raw.decode('utf-8')
        parts=name.split('/')
        assert not name.startswith('/') and not any(p in ('','..','.git') for p in parts)
        path=root+'/'+name
        # Reject directory symlinks instead of following them outside the tree.
        parent=os.path.dirname(path)
        assert os.path.commonpath([root,os.path.realpath(parent)])==root, 'escaping parent'
        try:before=os.lstat(path)
        except FileNotFoundError:
            rows.append({'path':name,'deleted':True});continue
        if stat.S_ISLNK(before.st_mode):
            body=os.fsencode(os.readlink(path));mode='120000'
        else:
            assert stat.S_ISREG(before.st_mode), 'nonregular candidate path'
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as handle:
                actual=os.fstat(handle.fileno())
                assert stat.S_ISREG(actual.st_mode) and actual.st_ino==before.st_ino
                assert actual.st_size<=32*1024*1024, 'single candidate file limit'
                body=handle.read(32*1024*1024+1)
                after=os.fstat(handle.fileno())
            assert (actual.st_size,actual.st_mtime_ns,actual.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
            mode='100755' if before.st_mode&0o111 else '100644'
        total+=len(body)
        assert total<=256*1024*1024 and len(body)<=32*1024*1024, 'candidate byte limit'
        digest=run(['hash-object','--no-filters','-w','--stdin'],body).strip()
        records.append(mode.encode()+b' '+digest+b'\t'+raw+b'\0')
        rows.append({'path':name,'mode':mode,'bytes':len(body),
            'sha256':hashlib.sha256(body).hexdigest(),'git_blob':digest.decode()})
    run(['update-index','-z','--index-info'],b''.join(records))
    tree=run(['write-tree']).strip().decode()
    patch=run(['diff-tree','--no-commit-id','-r','-p','--binary','--full-index',
        '--no-renames','--no-ext-diff','--no-textconv',diff_base,tree,'--'])
    assert len(patch)<=64*1024*1024, 'candidate patch limit'
result={'baseline_commit':baseline,'literal_baseline_tree':None if literal_tree=='-' else literal_tree,
    'candidate_tree':tree,'uid':os.getuid(),
    'files':rows,'literal_file_bytes':total,'patch_base64':base64.b64encode(patch).decode(),
    'patch_sha256':hashlib.sha256(patch).hexdigest(),'patch_bytes':len(patch),
    'scope':'Baseline tracked paths plus current tracked/nonignored untracked paths. Ignored untracked files excluded. No source staging/filter/hook or host execution. Metadata checks do not prove transient immutability.'}
print(json.dumps(result,sort_keys=True))
'''


def capture_snapshot(bridge, out, *, baseline_commit, reader_python, literal_baseline_tree=None):
    """Create one immutable checkpoint, including the original reader response."""
    if not re.fullmatch('[0-9a-f]{40}', baseline_commit):
        raise AdmissionError('registered baseline commit required')
    if literal_baseline_tree is not None and not re.fullmatch('[0-9a-f]{40}', literal_baseline_tree):
        raise AdmissionError('registered initial literal file tree required')
    if reader_python not in ('/usr/bin/python3', '/opt/miniconda3/envs/testbed/bin/python'):
        raise AdmissionError('registered immutable reader required')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    command = shlex.join([reader_python, '-I', '-S', '-c', READER, '/testbed', baseline_commit,
                          literal_baseline_tree or '-'])
    output = bridge.execute({'command': command}, timeout=180)
    write_exclusive(out/'reader-response.json', output)
    if output.get('returncode') != 0 or output.get('exception_info'):
        raise AdmissionError('snapshot reader failed; preserve response and halt')
    result = json.loads(output['output'])
    patch = base64.b64decode(result.pop('patch_base64'), validate=True)
    if result['baseline_commit'] != baseline_commit or result['uid'] != 999:
        raise AdmissionError('snapshot baseline or UID changed')
    if result.get('literal_baseline_tree') != literal_baseline_tree:
        raise AdmissionError('snapshot literal baseline changed')
    if len(patch) != result['patch_bytes'] or hashlib.sha256(patch).hexdigest() != result['patch_sha256']:
        raise AdmissionError('snapshot patch integrity mismatch')
    with (out/'candidate.patch').open('xb') as handle:
        handle.write(patch)
    result['reader_response_sha256'] = hashlib.sha256((out/'reader-response.json').read_bytes()).hexdigest()
    result['reader_source_sha256'] = hashlib.sha256(READER.encode()).hexdigest()
    write_exclusive(out/'snapshot.json', result)
    return result

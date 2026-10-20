"""Carry only a bound literal source tree into a fresh isolated task resource.

The pack contains tree/blob objects, not source Git history. It never executes
on the host. UID-bound Git import/check-out happens only in the separately
prepared, mount-free receiver container. Admission and owned cleanup are the
caller's responsibility. This is a coding sequence adaptation, not an official
standalone starting state or authenticated identity service.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .upstream_agent_adapter import AdmissionError, write_exclusive
from .upstream_docker_transport import PREFIX


EXPORT = r'''
import os,subprocess,sys
assert os.getuid()==999 and os.getcwd()=='/testbed'
tree=sys.argv[1]
assert len(tree)==40 and all(c in '0123456789abcdef' for c in tree)
env={'PATH':'/usr/bin:/bin','HOME':'/home/fbagent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
git=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false']
observed=subprocess.check_output(git+['rev-parse',tree+'^{tree}'],env=env).strip().decode()
assert observed==tree
packed=subprocess.run(git+['pack-objects','--stdout','--revs'],input=(tree+'\n').encode(),
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=True).stdout
assert len(packed)<=128*1024*1024
sys.stdout.buffer.write(packed)
'''

IMPORT = r'''
import hashlib,json,os,shutil,subprocess,sys
assert os.getuid()==999 and os.getcwd()=='/testbed' and os.path.realpath('/testbed')=='/testbed'
tree,expected=sys.argv[1:]
assert len(tree)==40 and all(c in '0123456789abcdef' for c in tree)
raw=sys.stdin.buffer.read(128*1024*1024+1)
assert len(raw)<=128*1024*1024 and hashlib.sha256(raw).hexdigest()==expected
env={'PATH':'/usr/bin:/bin','HOME':'/home/fbagent','GIT_CONFIG_NOSYSTEM':'1',
     'GIT_CONFIG_GLOBAL':'/dev/null','GIT_ATTR_NOSYSTEM':'1',
     'GIT_AUTHOR_NAME':'Benchmark','GIT_AUTHOR_EMAIL':'benchmark@local.invalid',
     'GIT_COMMITTER_NAME':'Benchmark','GIT_COMMITTER_EMAIL':'benchmark@local.invalid',
     'GIT_AUTHOR_DATE':'2026-10-20T00:00:00+0000','GIT_COMMITTER_DATE':'2026-10-20T00:00:00+0000'}
git=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
     '-c','core.autocrlf=false','-c','core.attributesFile=/dev/null']
def run(args,body=None):
    return subprocess.run(git+args,input=body,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,env=env,check=True).stdout
# Exact named workspace only; never enumerate host paths or follow symlinks.
# This receiver has completed trusted resource preparation and no solver has
# run in it. Remove its author baseline, including all original Git objects.
for item in os.scandir('/testbed'):
    if item.is_dir(follow_symlinks=False):shutil.rmtree(item.path)
    else:os.unlink(item.path)
run(['init','--template=','--initial-branch=main'])
run(['index-pack','--stdin','--strict'],raw)
assert run(['rev-parse',tree+'^{tree}']).strip().decode()==tree
run(['read-tree','--reset','-u',tree])
commit=run(['-c','commit.gpgSign=false','commit-tree',tree],b'Retained literal solver source\n').strip().decode()
run(['update-ref','refs/heads/main',commit])
assert run(['rev-list','--all','--count']).strip()==b'1'
assert not run(['remote']).strip()
print(json.dumps({'retained_tree':tree,'baseline_commit':commit,'uid':os.getuid(),
    'pack_sha256':expected,'pack_bytes':len(raw),'author_baseline_replaced':True,
    'scope':'Retained tree/blob pack only; fresh one-commit history. Literal file hashes must still be compared after checkout. Not protected identity or an official standalone starting source.'}))
'''


GRADE_PATCH = r'''
import base64,hashlib,json,os,subprocess,sys
assert os.getuid()==999 and os.getcwd()=='/testbed'
tree,expected,grade_base,projection=sys.argv[1:]
assert projection in ('whole_source','non_test_submission')
assert all(len(v)==40 and all(c in '0123456789abcdef' for c in v) for v in (tree,grade_base))
raw=sys.stdin.buffer.read(128*1024*1024+1)
assert len(raw)<=128*1024*1024 and hashlib.sha256(raw).hexdigest()==expected
env={'PATH':'/usr/bin:/bin','HOME':'/home/fbagent','GIT_CONFIG_NOSYSTEM':'1',
     'GIT_CONFIG_GLOBAL':'/dev/null','GIT_ATTR_NOSYSTEM':'1'}
git=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
     '-c','core.autocrlf=false','-c','core.attributesFile=/dev/null']
def run(args,body=None):
    return subprocess.run(git+args,input=body,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,env=env,check=True).stdout
assert run(['rev-parse',grade_base+'^{tree}']).strip().decode()==grade_base
run(['index-pack','--stdin','--strict'],raw)
assert run(['rev-parse',tree+'^{tree}']).strip().decode()==tree
paths=['.']
if projection=='non_test_submission':
    # Independent author tests must not be replaced by an earlier release's
    # carried tests. These exclusions match the upstream non-test submission
    # boundary, plus the declared host-managed workflow/patch artifacts.
    paths += [':(exclude,glob)**/tests/**',':(exclude,glob)**/test/**',
        ':(exclude,glob)**/conftest.py',':(exclude,glob)**/test_*.py',
        ':(exclude,glob)**/*_test.py',':(exclude,glob).specify/**',
        ':(exclude,glob)specs/[0-9][0-9][0-9]-upstream/**',
        ':(exclude,glob)notes/work-brief.md',
        ':(exclude,glob)notes/work-brief-[0-9][0-9][0-9].md',':(exclude,glob)patch.txt']
def names(specs):
    return set(run(['diff-tree','--no-commit-id','-r','--no-renames','--name-only','-z',
        grade_base,tree,'--']+specs).split(b'\0'))-{b''}
excluded=sorted(p.decode('utf-8') for p in names(['.'])-names(paths))
patch=run(['diff-tree','--no-commit-id','-r','-p','--binary','--full-index',
    '--no-renames','--no-ext-diff','--no-textconv',grade_base,tree,'--']+paths)
assert len(patch)<=64*1024*1024
print(json.dumps(dict(projection=projection,retained_tree=tree,grade_base_tree=grade_base,
    excluded_changed_paths=excluded,patch_base64=base64.b64encode(patch).decode(),
    patch_sha256=hashlib.sha256(patch).hexdigest())))
'''


def _argv(environment, reader_python, script, *args):
    if environment.config.interpreter != PREFIX+['/bin/bash', '-c'] or environment.config.forward_env:
        raise AdmissionError('fixed unprivileged interpreter and no forwarded host environment required')
    if reader_python != '/opt/miniconda3/envs/testbed/bin/python':
        raise AdmissionError('registered Dask resource interpreter required')
    if environment.container_id is None:
        raise AdmissionError('no owned task container')
    return [environment.config.executable, 'exec', '-i', '-w', '/testbed',
            environment.container_id, *PREFIX, reader_python, '-I', '-S', '-c', script, *args]


def _run(argv, raw, out, tag):
    try:
        return subprocess.run(argv, input=raw, capture_output=True, timeout=180, check=False)
    except BaseException as exc:
        stdout = getattr(exc, 'stdout', None) or getattr(exc, 'output', None) or b''
        stderr = getattr(exc, 'stderr', None) or b''
        if isinstance(stdout, str): stdout = stdout.encode('utf-8')
        if isinstance(stderr, str): stderr = stderr.encode('utf-8')
        try:
            (out/(tag+'-partial-stdout.bin')).write_bytes(stdout)
            (out/(tag+'-partial-stderr.bin')).write_bytes(stderr)
            write_exclusive(out/(tag+'-failure.json'), dict(argv=argv, error=repr(exc),
                stdout_bytes=len(stdout), stderr_bytes=len(stderr), retries=0))
        except BaseException as persistence_error:
            raise BaseExceptionGroup('Original tree transfer failure and receipt persistence failure',
                                     [exc, persistence_error])
        raise


def export_tree(environment, out, *, tree, reader_python):
    if not re.fullmatch('[0-9a-f]{40}', tree):
        raise AdmissionError('bound literal candidate tree required')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    argv = _argv(environment, reader_python, EXPORT, tree)
    result = _run(argv, b'', out, 'export')
    (out/'export-stderr.bin').write_bytes(result.stderr)
    (out/'tree.pack').write_bytes(result.stdout)
    receipt = dict(argv=argv, returncode=result.returncode, tree=tree,
                   pack_bytes=len(result.stdout), pack_sha256=hashlib.sha256(result.stdout).hexdigest(),
                   stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
                   reader_sha256=hashlib.sha256(EXPORT.encode()).hexdigest())
    write_exclusive(out/'export.json', receipt)
    if result.returncode or len(result.stdout)>128*1024*1024 or not result.stdout.startswith(b'PACK'):
        raise AdmissionError('retained tree export failed; preserve response and halt')
    return receipt


def import_tree(environment, exported, out, *, reader_python):
    exported, out = Path(exported), Path(out)
    manifest = json.loads((exported/'export.json').read_text())
    raw = (exported/'tree.pack').read_bytes()
    if not re.fullmatch('[0-9a-f]{40}', manifest['tree']) or manifest['returncode'] != 0:
        raise AdmissionError('successful bound literal tree export required')
    if hashlib.sha256(raw).hexdigest()!=manifest['pack_sha256'] or len(raw)!=manifest['pack_bytes']:
        raise AdmissionError('retained tree pack changed before transfer')
    out.mkdir(parents=True, exist_ok=False)
    argv = _argv(environment, reader_python, IMPORT, manifest['tree'], manifest['pack_sha256'])
    result = _run(argv, raw, out, 'import')
    receipt = dict(argv=argv, returncode=result.returncode,
                   stdout=result.stdout.decode('utf-8', errors='replace'),
                   stderr=result.stderr.decode('utf-8', errors='replace'),
                   reader_sha256=hashlib.sha256(IMPORT.encode()).hexdigest())
    write_exclusive(out/'import-response.json', receipt)
    if result.returncode:
        raise AdmissionError('retained tree import failed; preserve original response and halt')
    value = json.loads(receipt['stdout'])
    if value['retained_tree']!=manifest['tree'] or value['pack_sha256']!=manifest['pack_sha256'] or value['uid']!=999:
        raise AdmissionError('retained tree transfer mismatch')
    write_exclusive(out/'import.json', value)
    return value


def make_grader_patch(environment, exported, out, *, registered_grade_base_tree, reader_python,
                      projection='whole_source'):
    """Diff a retained tree against a fresh upstream grading base, without checkout.

    For sequence checkpoint two this produces the entire candidate delta from
    the official second base; it does not replace missing earlier solver work
    with author code. Run only in an independently prepared offline resource.
    """
    if not re.fullmatch('[0-9a-f]{40}', registered_grade_base_tree):
        raise AdmissionError('registered literal grading-base tree required')
    if projection not in ('whole_source','non_test_submission'):
        raise AdmissionError('registered checkpoint submission projection required')
    exported, out = Path(exported), Path(out)
    manifest = json.loads((exported/'export.json').read_text())
    raw = (exported/'tree.pack').read_bytes()
    if not re.fullmatch('[0-9a-f]{40}', manifest['tree']) or manifest['returncode'] != 0:
        raise AdmissionError('successful retained export required')
    if len(raw)!=manifest['pack_bytes'] or hashlib.sha256(raw).hexdigest()!=manifest['pack_sha256']:
        raise AdmissionError('retained pack changed before independent grade conversion')
    out.mkdir(parents=True, exist_ok=False)
    argv = _argv(environment, reader_python, GRADE_PATCH, manifest['tree'],
                 manifest['pack_sha256'], registered_grade_base_tree, projection)
    response = _run(argv, raw, out, 'grade-conversion')
    (out/'stderr.bin').write_bytes(response.stderr)
    (out/'reader-stdout.bin').write_bytes(response.stdout)
    if response.returncode:
        write_exclusive(out/'conversion-failure.json',dict(argv=argv,returncode=response.returncode,
            retained_tree=manifest['tree'],grade_base_tree=registered_grade_base_tree,
            projection=projection,stderr_sha256=hashlib.sha256(response.stderr).hexdigest()))
        raise AdmissionError('independent grade conversion failed; retain response and halt')
    value = json.loads(response.stdout)
    import base64
    patch = base64.b64decode(value['patch_base64'],validate=True)
    if (value['projection']!=projection or value['retained_tree']!=manifest['tree']
            or value['grade_base_tree']!=registered_grade_base_tree
            or hashlib.sha256(patch).hexdigest()!=value['patch_sha256']):
        raise AdmissionError('independent grade projection integrity mismatch')
    (out/'candidate.patch').write_bytes(patch)
    receipt = dict(argv=argv, returncode=response.returncode,
        retained_tree=manifest['tree'], grade_base_tree=registered_grade_base_tree,
        retained_pack_sha256=manifest['pack_sha256'], patch_bytes=len(patch),
        patch_sha256=hashlib.sha256(patch).hexdigest(),projection=projection,
        excluded_changed_paths=value['excluded_changed_paths'],
        stderr_sha256=hashlib.sha256(response.stderr).hexdigest(),
        reader_sha256=hashlib.sha256(GRADE_PATCH.encode()).hexdigest(),
        scope='Literal retained tree diff against independently prepared grading base; no checkout or author source substitution. Original upstream grader/tests still required.')
    write_exclusive(out/'conversion.json', receipt)
    if len(patch)>64*1024*1024:
        raise AdmissionError('independent grade conversion failed; retain response and halt')
    return receipt

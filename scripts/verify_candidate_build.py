"""Verify a downloaded candidate against authenticated same-repository Actions metadata.

The workflow supplies run/artifact metadata via GitHub API and downloads only the
named artifact from that successful trusted-main request workflow. No extraction
or execution occurs here. This is not benchmark approval; release verification
must still resolve the protected benchmark indices.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def verify(repository, run, artifacts, folder):
    if repository not in ('electrohire/applied-epistemic-engineering','electrohire/spec-kit-aee') or run['repository']['full_name']!=repository or run['head_repository']['full_name']!=repository:
        raise ValueError('candidate source repository mismatch')
    if run['event'] not in ('push','workflow_dispatch') or run['head_branch']!='main' or run['path']!='.github/workflows/benchmark-candidate.yml' or run['conclusion']!='success':
        raise ValueError('candidate is not a successful trusted-main request build')
    commit=run['head_sha']
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('invalid candidate source SHA')
    matches=[a for a in artifacts['artifacts'] if a['name']=='benchmark-candidate-'+commit and not a['expired']]
    if len(matches)!=1:raise ValueError('candidate artifact missing/expired/ambiguous')
    if {p.name for p in folder.iterdir()}!={'benchmark-request.json','candidate-bundle.zip'}:raise ValueError('unexpected downloaded artifact inventory')
    request=json.loads((folder/'benchmark-request.json').read_text())
    bundle=folder/'candidate-bundle.zip';digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
    if request['schema']!='benchmark-build-request-v1' or request['repository']!=repository or request['commit']!=commit or request['build_run_id']!=run['id'] or request['artifact_sha256']!=digest:
        raise ValueError('candidate build/request/bundle binding mismatch')
    with zipfile.ZipFile(bundle) as archive:
        names=archive.namelist()
        if not names or len(names)!=len(set(names)) or set(names)!=set(request['distributions']) or any('/' in n or '\\' in n or n in ('.','..') for n in names):raise ValueError('unsafe or changed distribution inventory')
        if sum(i.file_size for i in archive.infolist())>512*1024*1024:raise ValueError('oversized candidate distributions')
        for name in names:
            if hashlib.sha256(archive.read(name)).hexdigest()!=request['distributions'][name]:raise ValueError('distribution changed after request')
    return dict(repository=repository,commit=commit,artifact_sha256=digest,build_run_id=run['id'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',required=True);p.add_argument('--run-json',type=Path,required=True);p.add_argument('--artifacts-json',type=Path,required=True);p.add_argument('--folder',type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(a.repository,json.loads(a.run_json.read_text()),json.loads(a.artifacts_json.read_text()),a.folder),indent=2))

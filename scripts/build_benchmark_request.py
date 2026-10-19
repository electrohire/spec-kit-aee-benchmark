"""Package an already-built candidate and queue metadata; never runs inference."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def prepare(repository, commit, run_id, inputs, output):
    if repository not in ('electrohire/applied-epistemic-engineering','electrohire/spec-kit-aee') or not re.fullmatch('[0-9a-f]{40}',commit) or type(run_id) is not int or run_id <= 0:
        raise ValueError('unsupported candidate source/build identity')
    files=sorted(inputs.iterdir())
    if not files or any(not p.is_file() or p.is_symlink() for p in files):
        raise ValueError('candidate inputs must be regular built distributions only')
    if any(p.suffix not in ('.whl','.gz','.zip') for p in files):
        raise ValueError('unexpected candidate distribution')
    output.mkdir(parents=True,exist_ok=False)
    bundle=output/'candidate-bundle.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            item=zipfile.ZipInfo(path.name,date_time=(1980,1,1,0,0,0));item.external_attr=0o100644 << 16
            archive.writestr(item,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
    value=dict(schema='benchmark-build-request-v1',status='queued_not_executed',repository=repository,commit=commit,build_run_id=run_id,
        build_url=f'https://github.com/{repository}/actions/runs/{run_id}',artifact_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        distributions={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        boundary='Request only, not benchmark success/approval. Worker must verify authenticated build provenance, inventory, isolated dependencies, registered comparable baseline and idle serial admission. No credentials, paid inference or model/service change.')
    (output/'benchmark-request.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',required=True);p.add_argument('--commit',required=True);p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.repository,a.commit,a.run_id,a.inputs,a.output),indent=2))

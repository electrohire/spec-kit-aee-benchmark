"""Run only the maintained offline adapter/integrity checks, never inference."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def paths():
    value=json.loads((ROOT/'benchmarks/maintained-tests.json').read_text())
    files=value['active']
    if not files or len(set(files))!=len(files) or any(not re.fullmatch(r'tests/test_[a-z0-9_]+\.py',name) or not (ROOT/name).is_file() for name in files):
        raise ValueError('maintained test inventory invalid/missing')
    if set(files).intersection(value['archival_opt_in']):
        raise ValueError('active/archive overlap')
    if set(files)|set(value['archival_opt_in'])!={p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_*.py')}:
        raise ValueError('classify new tests explicitly; no silent omissions')
    return files


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--junitxml',type=Path);a=p.parse_args()
    command=[sys.executable,'-m','pytest','-q',*paths()]
    if a.junitxml:command+=['--junitxml',str(a.junitxml.resolve())]
    raise SystemExit(subprocess.run(command,cwd=ROOT).returncode)

"""Read literal candidate package version without importing or executing its code."""
import argparse
import re
import tomllib
from pathlib import Path


def version(source, component):
    if component=='engine':
        value=tomllib.loads((source/'pyproject.toml').read_text())['project']['version']
    elif component=='extension':
        text=(source/'extension.yml').read_text()
        lines=text.splitlines()
        starts=[i for i,line in enumerate(lines) if line=='extension:']
        if len(starts)!=1:raise ValueError('ambiguous/missing extension mapping')
        block=[]
        for line in lines[starts[0]+1:]:
            if line and not line[0].isspace():break
            block.append(line)
        rows=re.findall(r"^  version: [\'\"]?([0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.+-]*)[\'\"]?[ \t]*$",'\n'.join(block),re.M)
        if len(rows)!=1:raise ValueError('ambiguous/missing literal extension version')
        value=rows[0]
    else:raise ValueError('unsupported component')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.+-]*',value):raise ValueError('unsupported literal release version')
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--component',required=True);p.add_argument('--tag',required=True);a=p.parse_args()
    if a.tag!='v'+version(a.source,a.component):raise SystemExit('release tag does not match exact tested source version')
    print(a.tag)

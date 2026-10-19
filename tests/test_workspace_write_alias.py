import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from action_protocol import action_command


@pytest.mark.parametrize('relative',['.specify/memory/constitution.md','specs/001-feature/spec.md'])
def test_fixed_workspace_root_is_a_literal_alias_only(tmp_path,relative):
    content='literal "quoted" content; $(touch NEVER)\nλ\n'
    action=dict(action='write_file',path='/testbed/'+relative,content=content)
    argv=shlex.split(action_command(action));argv[0]=sys.executable
    result=subprocess.run(argv,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
    assert (tmp_path/relative).read_bytes()==content.encode()
    assert json.loads(result.stdout)['path']==relative
    assert not (tmp_path/'NEVER').exists()


@pytest.mark.parametrize('name',['/testbed','/testbed/','/testbed/../outside','/testbed/a/../../outside',
    '/testbed//outside','/testbed/./outside','/testbed/a/../outside','/testbed/a\\outside',
    '/testbed/C:/outside','/testbed/a\x00b','/testbed-other/outside','//testbed/outside','/etc/outside'])
def test_root_alias_cannot_escape_or_relax_canonical_segments(name):
    with pytest.raises(ValueError):action_command(dict(action='write_file',path=name,content='x'))

"""A failed real AEE invocation must leave reviewable diagnostics."""
import json
from pathlib import Path

import pytest

from benchmark_runner.store import Store
from benchmark_runner.workflow import assess

def test_invalid_claim_kind_retains_subprocess_failure(tmp_path):
    store=Store(tmp_path/'evidence')
    claims={'schema_version':'1.0','claims':[{'id':'BAD-1','text':'Invalid claim-kind fixture','kind':'observed'}]}
    with pytest.raises(RuntimeError,match='no evaluator result'):
        assess(Path(__file__).resolve().parents[1],claims,'implement',store)
    errors=store.events('assessment_errors')
    assert len(errors)==1
    diagnostic=json.loads((store.root/errors[0]['artifact']['path']).read_text())
    assert diagnostic['exit_code'] != 0
    assert 'ClaimKind' in diagnostic['stderr'] and 'observed' in diagnostic['stderr']
    assert diagnostic['claims']==claims

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
        assess(Path(__file__).resolve().parents[1],claims,'implement',store,'test-attempt-1')
    errors=store.events('assessment_errors')
    assert len(errors)==1
    diagnostic=json.loads((store.root/errors[0]['artifact']['path']).read_text())
    assert diagnostic['exit_code'] == 2
    # The retained diagnostic is the engine's lenient-load error: the
    # vendored 1.4.0 runner loads through the engine's --lenient path,
    # whose whole message is this one line (verified against the 1.5.0
    # CLI directly). The load-bearing facts: the failure is loud, and
    # the diagnostic names the offending value and the field domain
    # that rejected it. (The strict loader's longer wording — "field
    # 'kind' has invalid value 'observed'; valid values: ..." — is what
    # the old runner retained; it is not the message on this path.)
    assert "'observed' is not a valid ClaimKind" in diagnostic['stderr']
    assert diagnostic['claims']==claims

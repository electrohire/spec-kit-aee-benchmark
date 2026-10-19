"""Native-contract regressions; no model calls or shared-server changes."""
import json
import re
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def test_document_bound_is_split_below_server_repetition_threshold():
    import matched_grammar as g
    text = g.grammar_for('document')
    assert 'document ::= ' in text
    assert 'full-block ::= jchar{100}' in text
    assert 'tail ::= jchar{1,100}' in text
    assert all(int(n) <= 100 for n in re.findall(r'\{(?:\d+,)?(\d+)\}', text))
    assert '{1,3000}' not in text


def test_v3_keeps_v2_schema_and_budgets_changes_decoder_only():
    import matched_hallucinations as m
    old = m.load(m.REGISTRATIONS['matched-source-grounding-v2'])
    new = m.load(m.REGISTRATION)
    assert new['version'] == 'matched-source-grounding-v3'
    assert {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)} == {'version', 'decoder_contract', 'prospective_amendment'}


def test_manual_grammar_receipt_rejects_tampered_decoder_or_missing_schema():
    import matched_grammar as g
    import matched_hallucinations as m
    request = {'grammar': g.grammar_for('document')}
    call = dict(request=request, validation_schema=m.DOC_SCHEMA)
    assert g.receipt_schema(call, m.load(m.REGISTRATION)) == m.DOC_SCHEMA
    for bad in ({**call, 'request': {'grammar': request['grammar'].replace('{1,100}', '{1,3000}')}},
                {'request': request}, {**call, 'request': {**request, 'response_format': {}}}):
        with pytest.raises(ValueError):
            g.receipt_schema(bad, m.load(m.REGISTRATION))


def test_native_boundary_probe_uses_three_technical_checks_not_gold_success():
    import matched_grammar as g
    tests = g.native_probe_contracts()
    assert len(tests) == 3
    assert tests[0]['schema']['properties']['document']['minLength'] == 3000
    assert tests[0]['schema']['properties']['document']['maxLength'] == 3000
    assert all(t['output'] <= 1536 for t in tests)
    assert 'expected_label' not in json.dumps(tests)
    assert tests[2]['schema']['properties']['document']['const'] not in tests[2]['instruction']

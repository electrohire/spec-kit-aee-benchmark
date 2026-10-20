"""Published row/usage/provenance joins, not synthetic treatment efficacy."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/hallucinations/matched-03-recovered-20261020'
spec=importlib.util.spec_from_file_location('recovered_publication',ROOT/'scripts/publish_matched_recovery.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def grade():return json.loads((REPORT/'independent-grade.json').read_text())


def test_author_label_row_join_and_complete_denominators():
    p.validate_grade(grade())
    assert all(r['status']=='graded' for r in grade()['rows'])


@pytest.mark.parametrize('fault',['incomplete','oldpromoted','metric','duplicate','unknown'])
def test_export_refuses_invalid_claims(fault):
    g=grade()
    if fault=='incomplete':g['graded']=719
    if fault=='oldpromoted':g['original03_complete']=True
    if fault=='metric':g['metrics']['halueval_qa']['baseline']['accuracy_all']=1.
    if fault=='duplicate':g['rows'][0]=g['rows'][1]
    if fault=='unknown':g['recovery_accounting']['usage_unknown']=1
    with pytest.raises(ValueError):p.validate_grade(g)


def test_all_calls_and_unknown_usage_retained_separately():
    rows=json.loads((REPORT/'physical-calls.json').read_text())
    assert len(rows)==1487 and len({(r['episode'],r['path']) for r in rows})==1487
    assert sum(not bool(r['usage']) for r in rows)==1
    assert sum((r['usage'] or {}).get('total_tokens',0) for r in rows)==5613402
    failed=[r for r in rows if r['error']]
    assert len(failed)==1 and failed[0]['usage'] is None and failed[0]['unknown_reason']
    assert sum(r['episode']=='recovery04' for r in rows)==18


def test_same_original_worker_sensitivity_is_symmetric():
    g=grade();s=g['original_worker_complete_case_sensitivity'];excluded=set(s['excluded_case_indices'])
    assert len(excluded)==9 and s['graded']==693
    for a in p.ARMS:assert sum(r['index'] not in excluded and r['arm']==a for r in g['rows'])==231


def test_gateview_does_not_erase_raw_classification_errors():
    g=grade()
    assert all(g['gate_metrics'][ds]['spec_kit_aee']['abstentions']==120 for ds in g['metrics'])
    assert g['metrics']['halueval_qa']['spec_kit_aee']['false_acceptances']==10
    assert g['metrics']['ragtruth_test']['spec_kit_aee']['false_acceptances']==7


def test_every_exported_file_matches_its_content_address():
    manifest=json.loads((REPORT/'files-sha256.json').read_text())
    assert set(manifest)=={x.relative_to(REPORT).as_posix() for x in REPORT.rglob('*') if x.is_file() and x.name!='files-sha256.json'}
    for name,digest in manifest.items():assert p.sha(REPORT/name)==digest


def test_generated_summary_renders_as_a_real_table():
    body=p.compact_table(grade());html=MarkdownIt('commonmark').enable('table').render(body)
    assert html.count('<table>')==1 and html.count('<tr>')==3
    assert '70.0%' in html and '57.5%' in html

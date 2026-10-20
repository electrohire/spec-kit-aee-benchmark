"""Proposal boundaries and real framework helper routing, no model calls."""
from pathlib import Path
import json
import pytest
from benchmark_runner.upstream_workflow_adapter import Workflow,WorkflowFailure

ROOT=Path(__file__).resolve().parents[1]


def test_baseline_does_not_receive_framework_or_aee(tmp_path):
    w=Workflow(ROOT,tmp_path/'flow','baseline','public task')
    contract=w.document_contract('baseline')
    assert 'speckit_command' not in contract and 'actual_AEE_feedback' not in contract
    assert not (w.host/'.specify').exists()
    w.receive_document('baseline',b'Unaccepted work brief; correctness and human acceptance are unknown.',dict(role='fixture'))
    with pytest.raises(WorkflowFailure):w.assess('implement','proposal',{})


@pytest.mark.parametrize('raw',[b'',b'\x00',b'x'*3001,b'x'*65537],ids=['empty','nul','character-cap','byte-cap'])
def test_invalid_proposal_is_not_truncated_or_promoted(tmp_path,raw):
    w=Workflow(ROOT,tmp_path/'flow','baseline','public task')
    with pytest.raises(WorkflowFailure):w.receive_document('baseline',raw,dict(role='fixture'))
    assert not w.documents and not w.phase_order
    assert (w.out/'received-proposals/baseline.bin').read_bytes()==raw[:65537]


def test_wrong_phase_is_rejected(tmp_path):
    w=Workflow(ROOT,tmp_path/'flow','baseline','public task')
    with pytest.raises(WorkflowFailure):w.document_contract('specify')


def test_original_public_task_is_retained_without_cli_truncation(tmp_path):
    task='public upstream facts '*4000
    w=Workflow(ROOT,tmp_path/'flow','baseline',task)
    assert (w.out/'public-task.txt').read_bytes()==task.encode()
    assert w.document_contract('baseline')['public_task']==task


def test_prior_sequence_context_remains_explicit(tmp_path):
    prior=dict(requirements=[dict(id='prior-requirement',status='draft',uncertainty='high')],unresolved=['unverified'])
    w=Workflow(ROOT,tmp_path/'flow','baseline','next release',prior_context=prior)
    assert w.document_contract('baseline')['prior_sequence_context']==prior


def test_real_utf8_framework_prompt_survives_windows_default_codec(tmp_path,monkeypatch):
    w=Workflow(ROOT,tmp_path/'flow','spec_kit','public task')
    w.receive_document('constitution',b'Draft rules; human acceptance and correctness unknown.',dict(role='fixture'))
    path=ROOT/'prompts/skills/speckit-specify.md'
    expected=path.read_bytes().decode('utf-8').replace('$ARGUMENTS','public task')
    original=Path.read_text
    def windows_default(self,*args,**kwargs):
        if not args and 'encoding' not in kwargs:kwargs['encoding']='cp1252'
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',windows_default)
    assert w.document_contract('specify')['speckit_command']==expected


def test_short_partial_capture_is_retained_but_not_accepted_as_complete(tmp_path):
    w=Workflow(ROOT,tmp_path/'flow','baseline','public task')
    with pytest.raises(WorkflowFailure):w.receive_document('baseline',b'captured prefix',dict(partial=True))
    assert not w.documents and (w.out/'received-proposals/baseline.bin').read_bytes()==b'captured prefix'


def test_real_project_helpers_retain_constitution_and_create_next_feature(tmp_path):
    first=Workflow(ROOT,tmp_path/'first','spec_kit','first release',continuity_root=tmp_path/'project')
    raw=b'Draft project principles; no independent correctness or human acceptance.'
    first.receive_document('constitution',raw,dict(role='fixture'))
    second=Workflow(ROOT,tmp_path/'second','spec_kit','next release',continuity_root=tmp_path/'project',
                    prior_context=dict(status='unaccepted'),feature_number=2)
    assert second.host==first.host
    second.retain_constitution(raw,dict(uid=999,stable_metadata=True,partial=False,role='synthetic capture metadata'))
    contract=second.document_contract('specify')
    assert contract['target']=='specs/002-upstream/spec.md'
    assert (second.host/'specs/001-upstream/spec.md').is_file()
    assert (second.host/'specs/002-upstream/spec.md').is_file()
    assert not (second.out/'host-commands/git-init.json').exists()
    receipt=json.loads((second.out/'retained-constitution.json').read_text())
    assert receipt['new_model_calls']==0 and receipt['status']=='unaccepted prior draft'


def test_retained_host_helper_change_refuses_execution(tmp_path):
    first=Workflow(ROOT,tmp_path/'first','spec_kit','first release',continuity_root=tmp_path/'project')
    script=first.host/'.specify/scripts/python/common.py'
    script.write_bytes(script.read_bytes()+b'\n# controlled mutation\n')
    with pytest.raises(WorkflowFailure,match='helper bytes changed'):
        Workflow(ROOT,tmp_path/'second','spec_kit','next release',continuity_root=tmp_path/'project',feature_number=2)
    assert not (tmp_path/'second/host-commands').exists()

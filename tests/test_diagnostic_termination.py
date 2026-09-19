"""Structural diagnostic termination: final-step done-only enforcement and
mid-phase draft claims for claim-bearing phases.

Regression tests for the measured failure mode where models exhaust the
diagnose action budget on shell exploration and never emit done (15/16
observed diagnostics ignored the final-call nudge).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('repeated_local', ROOT / 'scripts/repeated_local.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from benchmark_runner.workflow import grounded_claims


def claims_bundle(n=2):
    return {"schema_version": "1.0", "claims": [{
        "id": f"T{i:02d}", "text": f"test hypothesis claim {i}", "kind": "hypothesis",
        "status": "unsupported", "boundary": ["diagnose"],
        "depends_on": [], "conflicts_with": [],
        "falsification_tests": ["re-run and observe"],
        "source_ref": "test", "uncertainty": "high", "evidence": [],
    } for i in range(n)]}


def done_action(bundle):
    import json
    return json.dumps({"action": "done", "summary": "finished", "claims": bundle})


def shell_action(i=0):
    import json
    return json.dumps({"action": "shell", "command": f"echo probe-{i}"})


def draft_action(bundle):
    import json
    return json.dumps({"action": "draft", "claims": bundle})


class ScriptedProvider:
    """Returns scripted JSON actions in order; records every query."""
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []
        self.seen = []

    def query(self, messages, phase, stage, deadline):
        self.calls.append({})
        self.seen.append(list(messages))
        assert self.actions, "provider script exhausted"
        return self.actions.pop(0)


class FakeBox:
    def __init__(self):
        self.commands = []

    def execute(self, command, timeout=60):
        self.commands.append(command)
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}


def run_phase(tmp_path, actions, limit=8, claims=True, phase="diagnose"):
    provider = ScriptedProvider(actions)
    box = FakeBox()
    session = runner.Session(box, provider, runner.Store(tmp_path / "store"), "fixture")
    summary = session.phase(phase, "Read-only review.", "Requirements", 3, limit, 100, claims)
    return summary, provider, box


def test_final_shell_is_not_executed_and_honest_done_recorded(tmp_path):
    # The measured failure: 8/8 shell actions, never done. The final shell must
    # not execute; the phase must complete with an honest terminal done.
    summary, provider, box = run_phase(tmp_path, [shell_action(i) for i in range(8)])
    assert summary["completed"] is True
    assert summary["done"] is not None
    assert summary["done"]["terminal_synthesized"] is True
    assert len(provider.calls) == 8
    # Steps 0-3, 5, 6 executed; the draft-step shell (step 4) was rejected and
    # the final shell (step 7) was coerced -- neither executed.
    assert len(box.commands) == 6
    assert any("TerminalActionCoerced" in e for e in summary["errors"])
    claim = summary["done"]["claims"]["claims"][0]
    assert claim["id"] == "DIAG-NONTERMINATION-01"
    assert claim["status"] == "unsupported"
    assert claim["uncertainty"] == "high"
    assert "did not terminate" in summary["done"]["summary"] or "without the model returning done" in summary["done"]["summary"]


def test_final_message_declares_done_only(tmp_path):
    summary, provider, box = run_phase(tmp_path, [shell_action(i) for i in range(7)] + [done_action(claims_bundle())])
    final_prompt = provider.seen[-1][-1]["content"]
    assert "Only a done action is accepted now" in final_prompt
    assert "last allocated action" in final_prompt
    assert summary["completed"] is True
    assert "terminal_synthesized" not in summary["done"]


def test_mid_phase_draft_step_rejects_shell(tmp_path):
    # Step index 4 of 8 is the draft checkpoint: a shell action there must be
    # rejected (not executed) and recorded as an error.
    actions = [shell_action(i) for i in range(4)] + [shell_action(99), done_action(claims_bundle())]
    summary, provider, box = run_phase(tmp_path, actions)
    assert len(box.commands) == 4
    assert any("Mid-phase draft claims required" in e for e in summary["errors"])
    assert summary["completed"] is True


def test_mid_phase_draft_is_recorded_and_finalized(tmp_path):
    bundle = claims_bundle()
    actions = [shell_action(i) for i in range(4)] + [draft_action(bundle),
                shell_action(5), shell_action(6), done_action(bundle)]
    summary, provider, box = run_phase(tmp_path, actions)
    draft_prompt = provider.seen[4][-1]["content"]
    assert "MID-PHASE CHECKPOINT" in draft_prompt
    assert summary["completed"] is True
    assert summary["done"]["claims"] == bundle
    assert "terminal_synthesized" not in summary["done"]


def test_final_step_adopts_late_draft_as_terminal_claims(tmp_path):
    bundle = claims_bundle()
    actions = [shell_action(i) for i in range(4)] + [shell_action(4), shell_action(5),
                shell_action(6), draft_action(bundle)]
    summary, provider, box = run_phase(tmp_path, actions)
    assert summary["completed"] is True
    assert summary["done"]["terminal_synthesized"] is True
    assert summary["done"]["claims"] == bundle
    assert "draft" in summary["done"]["summary"]


def test_terminal_done_satisfies_assessment_gate(tmp_path):
    # matched_repair.py gates assessment on: summary['done'] and not
    # diagnostic_changed. The old non-termination shape (done=None) failed the
    # gate; the synthesized terminal done passes it with valid claims.
    summary, provider, box = run_phase(tmp_path, [shell_action(i) for i in range(8)])
    assert summary["done"]  # gate conjunct 1 (source unchanged in this fixture)
    store = runner.Store(tmp_path / "store2")
    grounded = grounded_claims(summary["done"]["claims"], store, "fixture")
    assert grounded["claims"][0]["id"] == "DIAG-NONTERMINATION-01"


def test_non_claim_phases_keep_previous_behavior(tmp_path):
    # claims=False phases: no coercion, no draft checkpoint, honest non-completion.
    summary, provider, box = run_phase(tmp_path, [shell_action(0), shell_action(1)], limit=2, claims=False)
    assert summary["completed"] is False
    assert summary["done"] is None
    assert not any("TerminalActionCoerced" in e for e in summary["errors"])
    assert len(box.commands) == 2
    assert "last allocated action" in provider.seen[-1][-1]["content"]


def test_small_claim_limits_skip_draft_checkpoint(tmp_path):
    # limit < 6 leaves no room for a mid-phase draft; final-step enforcement
    # still applies.
    summary, provider, box = run_phase(tmp_path, [shell_action(i) for i in range(4)], limit=4)
    assert not any("MID-PHASE CHECKPOINT" in m["content"] for seen in provider.seen for m in seen if m["role"] == "user")
    assert summary["completed"] is True
    assert summary["done"]["terminal_synthesized"] is True


def test_freeze_covers_protocol_scripts():
    from benchmark_runner.experiment import frozen_paths
    paths = frozen_paths(ROOT)
    assert "scripts/repeated_local.py" in paths
    assert "scripts/matched_repair.py" in paths
    assert not any("__pycache__" in p for p in paths)

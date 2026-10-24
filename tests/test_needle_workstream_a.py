"""Needle program Workstream A (plan 2026-10-21, section 2, items A1-A3).

A1: compact assessment feedback in the coding workflow (runner).
A2: delta claim submissions after the first assessed phase, repair rounds
    included; malformed deltas are model outcomes fed back in-phase.
A3: claim-count discipline text, a soft cap of 12 claims per phase bundle
    with exactly one consolidation request per phase, and per-phase claim
    counts on the assessments store record.

All offline and scripted: providers are fakes in the pattern of
tests/test_workflow.py / tests/test_spec006_lane_harness.py, and assess()
is stubbed except where a test names the real deterministic assess().
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner import runner
from benchmark_runner.store import Store, read_json
from benchmark_runner.workflow import (DeltaFormatError, assess, compact_feedback,
                                       grounded_claims, phase_prompt,
                                       resolve_claim_submission)

ROOT = Path(__file__).parents[1]

COMPACT_KEYS = {"outcome", "findings", "next_action", "confidence", "uncertainty",
                "gate_outcome", "lanes", "recorded_acts_summary"}

CFG = {"timeout_seconds": 60, "max_input_tokens": 100, "max_output_tokens": 100,
       "token_cap": 100000, "max_calls": 60, "max_recovery_rounds": 2}


# ---------------------------------------------------------------------------
# Fixtures: claims, providers, assess stubs
# ---------------------------------------------------------------------------

def claim(cid, text=None):
    return {"id": cid, "text": text or f"Requirement {cid} holds",
            "kind": "requirement", "status": "draft", "boundary": ["fixture"],
            "depends_on": [], "conflicts_with": [],
            "falsification_tests": [f"A test observes {cid} failing"],
            "source_ref": "spec.md", "uncertainty": "low", "evidence": []}


def bundle(*claims):
    return {"schema_version": "1.0", "claims": list(claims)}


def delta(upsert=(), withdraw=()):
    return {"schema_version": "1.0",
            "delta": {"upsert": list(upsert), "withdraw": list(withdraw)}}


def rich_result(outcome="pass", claims=()):
    """An assess() stand-in result carrying every field the full-JSON
    feedback used to leak into the conversation, plus the Spec 006
    augmentation (gate outcome, lanes, recorded-acts summary)."""
    return {"outcome": outcome,
            "findings": [{"id": "F1", "severity": "low", "kind": "other",
                          "subject": c["id"]} for c in claims],
            "next_action": {"kind": outcome, "target_phase": None,
                            "message": f"Composed outcome: {outcome}."},
            "confidence": 0.9, "uncertainty": "low",
            "gate_outcome": outcome,
            "lanes": {"lane_1": {"outcome": outcome, "threshold": 0.7},
                      "lane_2": {"stage_counts": {"created": len(claims)},
                                 "claims_below_explained": len(claims),
                                 "exposition_missing_claims": len(claims)}},
            "recorded_acts_summary": {"count": 2, "basis_types": ["test-verdict"],
                                      "actor": "benchmark-pipeline"},
            "summary": "Verbose summary that must not enter the conversation",
            "state": {"aee": {"claims": "bulk that must not enter the conversation"}},
            "metadata": {"evaluator_results": ["bulk"] * 50},
            "evaluator": {"id": "composed", "version": "1.0"},
            "schema_version": "1.0", "phase": "after_specify"}


class AssessRecorder:
    """assess() stub: records every bundle it is asked to assess and
    answers from a per-call outcome queue (default: pass). Findings are
    derived from the bundle, so identical bundles give identical
    composed outcomes and findings."""

    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.bundles = []  # [(phase, bundle)]

    def __call__(self, root, claims, phase, store, attempt_id):
        self.bundles.append((phase, copy.deepcopy(claims)))
        outcome = self.outcomes.pop(0) if self.outcomes else "pass"
        return rich_result(outcome, claims.get("claims") or [])


class ScriptedProvider:
    """Provider-protocol fake: each query for a phase returns the next
    scripted done action for that phase (or a bare done). Every message
    content it is shown is recorded for feedback assertions."""

    def __init__(self, script=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.seen = []
        self.messages_seen = []  # per query: [message contents]

    def query(self, messages, phase, timeout):
        self.seen.append(phase)
        self.messages_seen.append([m.get("content", "") for m in messages])
        queue = self.script.get(phase) or []
        if queue:
            return json.dumps({"action": "done", "summary": f"{phase} done",
                               "claims": queue.pop(0)})
        return json.dumps({"action": "done", "summary": f"{phase} done"})

    def first_appearances(self, marker):
        """How many distinct conversation messages containing marker the
        harness added (a message re-sent in later history counts once)."""
        seen, count = set(), 0
        for contents in self.messages_seen:
            for content in contents:
                if marker in content and content not in seen:
                    seen.add(content)
                    count += 1
        return count

    def feedback_payloads(self):
        """Unique parsed AEE/Evaluator feedback payloads shown to the model."""
        payloads = []
        for contents in self.messages_seen:
            for content in contents:
                if content.startswith("AEE/Evaluator result: "):
                    payload = json.loads(content.split(": ", 1)[1])
                    if payload not in payloads:
                        payloads.append(payload)
        return payloads


class FakeSandbox:
    def stage_workflow(self, root):
        pass

    def execute(self, command, timeout=60):
        return {"exit_code": 0,
                "stdout": "SYNTHETIC PATCH" if "git diff" in command else "1 passed",
                "stderr": ""}


def run_attempt(tmp_path, monkeypatch, provider, recorder, script_arm="spec_kit_aee"):
    monkeypatch.setattr(runner, "assess", recorder)
    store = Store(tmp_path)
    result = runner.execute_attempt(
        ROOT, {"problem_statement": "SYNTHETIC task"}, script_arm, provider,
        FakeSandbox(), store, {"attempt_id": "test"},
        dict(CFG))
    return result, store


def full_script(**phase_submissions):
    """Script every AEE phase; unspecified phases submit one fresh claim."""
    script = {}
    for phase in ("specify", "plan", "tasks", "implement"):
        script[phase] = phase_submissions.get(phase) or [bundle(claim(f"{phase}-1"))]
    return script


# ---------------------------------------------------------------------------
# A1: compact assessment feedback
# ---------------------------------------------------------------------------

def test_compact_feedback_key_set_is_exact():
    result = rich_result("iterate", [claim("C1")])
    compact = compact_feedback(result)
    assert set(compact) == COMPACT_KEYS
    assert compact["outcome"] == "iterate"
    assert compact["findings"] == result["findings"]
    assert compact["next_action"] == result["next_action"]
    assert compact["confidence"] == 0.9 and compact["uncertainty"] == "low"
    assert compact["gate_outcome"] == "iterate"
    # The lane pair is slimmed: lane 1 keeps only its outcome; lane 2
    # keeps only the stage counts and the below-explained count.
    assert compact["lanes"] == {"lane_1": {"outcome": "iterate"},
                                 "lane_2": {"stage_counts": {"created": 1},
                                            "claims_below_explained": 1}}
    assert compact["recorded_acts_summary"] == {
        "count": 2, "basis_types": ["test-verdict"], "actor": "benchmark-pipeline"}
    assert len(json.dumps(compact)) < len(json.dumps(result))


def test_scripted_attempt_feedback_messages_are_compact(tmp_path, monkeypatch):
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script())
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert result["patch"]["sha256"]
    payloads = provider.feedback_payloads()
    assert len(payloads) == 4  # one per assessed phase
    for payload in payloads:
        assert set(payload) == COMPACT_KEYS
    # Nothing else from the full result leaked into the conversation.
    shown = "\n".join(c for contents in provider.messages_seen for c in contents)
    assert "Verbose summary that must not enter the conversation" not in shown
    assert "bulk that must not enter the conversation" not in shown


def retained_composed_results():
    """(attempt, phase, composed result) per retained assessment record
    in reports/local/current-study-01's AEE attempts. The composed
    result of a record is its last artifact whose evaluator id is
    'composed' (the canonical stored copy)."""
    rows = []
    base = ROOT / "reports/local/current-study-01"
    for evidence in sorted(base.glob("*spec_kit_aee/evidence")):
        for line in (evidence / "assessments.jsonl").read_text().splitlines():
            record = json.loads(line)
            composed = None
            for artifact in record["artifacts"]:
                try:
                    payload = json.loads((evidence / artifact["path"]).read_bytes())
                except (OSError, ValueError):
                    continue
                if isinstance(payload, dict) and (payload.get("evaluator") or {}).get("id") == "composed":
                    composed = payload
            assert composed is not None, f"no composed result retained for {record}"
            rows.append((evidence.parent.name, record["phase"], composed))
    return rows


def replay_measurements():
    """Per-phase old (full-JSON) vs new (compact) feedback payload sizes
    reconstructed from the retained current-study-01 AEE records."""
    measurements = []
    for attempt, phase, composed in retained_composed_results():
        old = "AEE/Evaluator result: " + json.dumps(composed)
        new = "AEE/Evaluator result: " + json.dumps(compact_feedback(composed))
        measurements.append({"attempt": attempt, "phase": phase,
                             "old_chars": len(old), "new_chars": len(new)})
    return measurements


def test_replay_retained_current_study_01_compact_shrinks_every_phase():
    rows = retained_composed_results()
    # The retained set is six specify-phase assessments across four
    # AEE attempts (the attempts stopped after specify); that is what
    # exists, and the replay covers exactly those records.
    assert len(rows) == 6
    assert {attempt for attempt, _, _ in rows} == {
        "cachetools-20261016-spec_kit_aee", "cachetools-20261017-spec_kit_aee",
        "tinydb-20261016-spec_kit_aee", "tinydb-20261017-spec_kit_aee"}
    for attempt, phase, composed in rows:
        compact = compact_feedback(composed)
        assert set(compact) == COMPACT_KEYS
        # The projection must not change the composed outcome or
        # findings (plan tripwire: shrinkage only, never a new verdict).
        assert compact["outcome"] == composed["outcome"]
        assert compact["findings"] == composed["findings"]
        old = "AEE/Evaluator result: " + json.dumps(composed)
        new = "AEE/Evaluator result: " + json.dumps(compact)
        assert len(new) < len(old), f"{attempt}/{phase}: {len(new)} !< {len(old)}"


# ---------------------------------------------------------------------------
# A2: delta claim submissions
# ---------------------------------------------------------------------------

def test_delta_merge_matches_full_resubmission(tmp_path, monkeypatch):
    c1, c2 = claim("C1"), claim("C2")
    c2_revised = claim("C2", "Requirement C2 holds, revised in plan")
    c3 = claim("C3")
    delta_script = full_script(
        specify=[bundle(c1, c2)],
        plan=[delta(upsert=[c2_revised])],
        tasks=[delta(upsert=[c3])],
        implement=[delta()])
    full_script_ = full_script(
        specify=[bundle(c1, c2)],
        plan=[bundle(c1, c2_revised)],
        tasks=[bundle(c1, c2_revised, c3)],
        implement=[bundle(c1, c2_revised, c3)])
    outcomes = {}
    for name, script in (("delta", delta_script), ("full", full_script_)):
        recorder = AssessRecorder()
        provider = ScriptedProvider(script)
        result, _ = run_attempt(tmp_path / name, monkeypatch, provider, recorder)
        assert result["patch"]["sha256"] and not result.get("blocked")
        outcomes[name] = recorder.bundles
    # Same assessed bundles, hence same composed outcomes and findings,
    # whether phase 2+ submitted deltas or a full re-draft.
    assert outcomes["delta"] == outcomes["full"]


def test_delta_withdrawal_removes_exactly_the_named_claim(tmp_path, monkeypatch):
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(
        specify=[bundle(claim("C1"), claim("C2"), claim("C3"))],
        plan=[delta(withdraw=["C2"])]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert not result.get("blocked")
    plan_bundles = [b for phase, b in recorder.bundles if phase == "plan"]
    assert len(plan_bundles) == 1
    assert [c["id"] for c in plan_bundles[0]["claims"]] == ["C1", "C3"]


def test_repair_round_delta_is_scoped_to_findings(tmp_path, monkeypatch):
    # First specify assessment says iterate (a repair round follows);
    # the repair submission is a delta touching only the found claim.
    recorder = AssessRecorder(outcomes=["iterate"])
    provider = ScriptedProvider(full_script(
        specify=[bundle(claim("C1"), claim("C2")),
                 delta(upsert=[claim("C2", "Requirement C2 holds, repaired")])]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert not result.get("blocked") and result["repair_count"] == 1
    specify_bundles = [b for phase, b in recorder.bundles if phase == "specify"]
    assert len(specify_bundles) == 2
    first, repaired = specify_bundles
    assert [c["id"] for c in repaired["claims"]] == ["C1", "C2"]
    assert repaired["claims"][0] == first["claims"][0]  # untouched claim carried over
    assert repaired["claims"][1]["text"] == "Requirement C2 holds, repaired"


def test_malformed_delta_is_model_feedback_not_harness_error(tmp_path, monkeypatch):
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(
        specify=[bundle(claim("C1"), claim("C2"))],
        plan=[delta(withdraw=["NOPE"]),                       # unknown id
              {"schema_version": "1.0", "delta": {"upsert": [{"text": "no id"}]}},
              delta(upsert=[claim("C2", "Requirement C2 holds, revised")])]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    # The attempt completed normally: no exception, no blocked return,
    # and the malformed submissions were never assessed.
    assert result["patch"]["sha256"] and not result.get("blocked")
    assert provider.first_appearances("Claims submission rejected") == 2
    plan_bundles = [b for phase, b in recorder.bundles if phase == "plan"]
    assert len(plan_bundles) == 1
    assert plan_bundles[0]["claims"][1]["text"] == "Requirement C2 holds, revised"


def test_delta_on_first_assessed_phase_is_format_feedback(tmp_path, monkeypatch):
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(
        specify=[delta(upsert=[claim("C1")]), bundle(claim("C1"))]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert result["patch"]["sha256"] and not result.get("blocked")
    assert provider.first_appearances("Claims submission rejected") == 1
    assert [phase for phase, _ in recorder.bundles].count("specify") == 1


# ---------------------------------------------------------------------------
# A3: claim-count discipline, soft cap, instrumentation
# ---------------------------------------------------------------------------

def test_discipline_text_in_phase_prompt_and_claims_instruction():
    prompt = phase_prompt(ROOT, "spec_kit_aee", "specify")
    assert runner.CLAIM_DISCIPLINE in prompt
    full = runner.claims_instruction(ROOT, delta=False)
    delta_text = runner.claims_instruction(ROOT, delta=True)
    assert runner.CLAIM_DISCIPLINE in full
    assert runner.CLAIM_DISCIPLINE in delta_text
    # The delta form is described for subsequent phases: upserts as
    # full claim objects, withdrawals by claim id.
    assert "upsert" in delta_text and "withdraw" in delta_text


def test_consolidation_fires_once_on_13_claims(tmp_path, monkeypatch):
    thirteen = bundle(*[claim(f"C{i:02d}") for i in range(13)])
    revised = bundle(claim("C00"), claim("C01"), claim("C02"))
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(specify=[thirteen, revised]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert not result.get("blocked")
    assert provider.first_appearances("Consolidation requested") == 1
    specify_bundles = [b for phase, b in recorder.bundles if phase == "specify"]
    assert len(specify_bundles) == 1
    assert specify_bundles[0] == revised  # the revised bundle is what was assessed


def test_consolidation_not_refired_when_revision_still_over_cap(tmp_path, monkeypatch):
    thirteen = bundle(*[claim(f"C{i:02d}") for i in range(13)])
    still_thirteen = bundle(*[claim(f"D{i:02d}") for i in range(13)])
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(specify=[thirteen, still_thirteen]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert not result.get("blocked")
    assert provider.first_appearances("Consolidation requested") == 1
    specify_bundles = [b for phase, b in recorder.bundles if phase == "specify"]
    assert len(specify_bundles) == 1 and len(specify_bundles[0]["claims"]) == 13


def test_no_consolidation_on_12_claims(tmp_path, monkeypatch):
    twelve = bundle(*[claim(f"C{i:02d}") for i in range(12)])
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(specify=[twelve]))
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    assert not result.get("blocked")
    assert provider.first_appearances("Consolidation requested") == 0
    specify_bundles = [b for phase, b in recorder.bundles if phase == "specify"]
    assert len(specify_bundles) == 1 and len(specify_bundles[0]["claims"]) == 12


def test_real_assess_records_claim_count_and_acts_summary(tmp_path):
    store = Store(tmp_path / "run")
    claims = read_json(ROOT / ".specify/extensions/aee/templates/aee-claims.json")
    extra = copy.deepcopy(claims["claims"][0])
    extra["id"] = "REQ-EXTRA-002"
    claims["claims"].append(extra)
    for c in claims["claims"]:
        c["status"] = "unsupported"
        c["evidence"] = []
    result = assess(ROOT, claims, "specify", store, "att-counts")
    (event,) = store.events("assessments")
    # A3(c): the assessments record carries the per-phase claim count.
    assert event["claim_count"] == 2
    # A1: the returned augmentation carries the recorded-acts summary;
    # the stored full result remains available for audit.
    summary = result["recorded_acts_summary"]
    assert summary["count"] == len(event["recorded_acts"])
    assert summary["actor"] == "benchmark-pipeline"
    assert set(summary) == {"count", "basis_types", "actor"}
    compact = compact_feedback(result)
    assert set(compact) == COMPACT_KEYS
    assert len(json.dumps(compact)) < len(json.dumps(result))


# ---------------------------------------------------------------------------
# Regression: malformed submission entry shapes (Stage B attempt-8 defect)
#
# In the Stage B candidate leg (2026-10-23), attempt 8 (pytest-5809,
# spec_kit_aee) died with AttributeError: 'str' object has no attribute
# 'get' — classified unknown/unclassified_error, halting the study. The
# A2 design intent (CHANGELOG, 2026-10-21) is that a malformed claims
# submission is a model outcome fed back in-phase, never an unhandled
# harness exception; delta submissions already enforce that through
# DeltaFormatError, but the full-bundle path validated only that
# "claims" is a list — not the shapes of its entries — so a bundle
# whose claim entries, evidence entries, or evidence field are strings
# (or an evidence field that is not a list at all) reached
# grounded_claims and raised the unclassified AttributeError. These
# tests pin the defined behavior for every such shape.
# ---------------------------------------------------------------------------

def _assert_format_error(submission, base=None):
    try:
        resolve_claim_submission(base, submission)
    except DeltaFormatError:
        return
    raise AssertionError(f"submission was accepted: {submission!r}")


def test_string_claim_entries_are_format_errors():
    _assert_format_error({"claims": ["Requirement C1 holds"]})
    _assert_format_error({"claims": [claim("C1"), "Requirement C2 holds"]})


def test_string_evidence_entries_are_format_errors():
    bad = claim("C1")
    bad["evidence"] = ["ran the tests"]
    _assert_format_error({"claims": [bad]})


def test_non_list_evidence_field_is_a_format_error():
    as_string = claim("C1")
    as_string["evidence"] = "ran the tests"
    _assert_format_error({"claims": [as_string]})
    as_object = claim("C1")
    as_object["evidence"] = {"kind": "observed"}
    _assert_format_error({"claims": [as_object]})


def test_delta_upsert_with_malformed_evidence_is_a_format_error():
    bad = claim("C2")
    bad["evidence"] = "ran the tests"
    _assert_format_error({"delta": {"upsert": [bad]}},
                         base=bundle(claim("C1")))


def test_wellformed_entry_shapes_still_resolve():
    with_evidence = claim("C1")
    with_evidence["evidence"] = [{"kind": "observed", "source_id": "x",
                                  "ref": "y", "description": "d"}]
    resolved = resolve_claim_submission(None, bundle(with_evidence, claim("C2")))
    assert [c["id"] for c in resolved["claims"]] == ["C1", "C2"]


def test_grounded_claims_rejects_malformed_bundle_shapes(tmp_path):
    store = Store(tmp_path / "run")
    for bad_bundle in ({"claims": ["Requirement C1 holds"]},
                       {"claims": "Requirement C1 holds"},
                       {"claims": None},
                       {"claims": [{"id": "C1", "evidence": "ran the tests"}]}):
        try:
            grounded_claims(bad_bundle, store, "att-x")
        except DeltaFormatError:
            continue
        raise AssertionError(f"grounded_claims accepted: {bad_bundle!r}")


def test_malformed_full_bundle_is_model_feedback_not_harness_error(tmp_path, monkeypatch):
    recorder = AssessRecorder()
    provider = ScriptedProvider(full_script(
        specify=[{"schema_version": "1.0",
                  "claims": ["Requirement C1 holds"]},          # malformed
                 bundle(claim("C1"))]))                          # resubmission
    result, _ = run_attempt(tmp_path, monkeypatch, provider, recorder)
    # The attempt completed normally: no exception escaped, the
    # malformed submission was fed back as a format rejection, and
    # only the well-formed resubmission was assessed.
    assert result["patch"]["sha256"] and not result.get("blocked")
    assert provider.first_appearances("Claims submission rejected") == 1
    specify_bundles = [b for phase, b in recorder.bundles if phase == "specify"]
    assert len(specify_bundles) == 1
    assert [c["id"] for c in specify_bundles[0]["claims"]] == ["C1"]

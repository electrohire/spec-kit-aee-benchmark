"""Frozen skill adapter and explicit deterministic AEE/Evaluator execution."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .store import canonical, read_json, sha, utc, write_json

PHASES = ("constitution", "specify", "plan", "tasks", "implement", "converge")
AEE_PHASES = {"specify", "plan", "tasks", "implement"}


def grounded_claims(claims, store, attempt_id):
    """A model cannot promote invented evidence to a recorded observation.

    Grounding applies to every evidence kind (FR-7.4): any item whose ref
    cannot be verified against this attempt's own tool artifacts is
    downgraded to an asserted model claim, whatever kind it declared.
    Kind labels confer no exemption.
    """
    claims = json.loads(json.dumps(claims))
    allowed = {e["artifact"]["sha256"]: e["artifact"] for e in store.events("tools")
               if e.get("attempt_id") == attempt_id}
    for claim in claims.get("claims", []):
        for evidence in claim.get("evidence", []):
            digest = evidence.get("source_id")
            ref = allowed.get(digest)
            verified = ref and evidence.get("ref") == ref["path"] and sha((store.root/ref["path"]).read_bytes()) == digest
            if not verified:
                evidence["kind"] = "asserted"
                evidence["source_quality"] = "model"
                evidence["description"] = "Unverified model assertion: "+evidence.get("description", "")
    return claims


PIPELINE_ACTOR = "benchmark-pipeline"


def _test_text(value):
    return " ".join(str(value).lower().split())


def _command_matches_tests(command, tests):
    """The executed command is one of the claim's declared tests when
    either text names the other (the engine's test-verdict reference
    rule, applied to harness records). Returns the declared test text
    it matches, or None."""
    if not command:
        return None
    cmd = _test_text(command)
    for test in tests:
        text = _test_text(test)
        if text and (text in cmd or cmd in text):
            return test
    return None


# Commands that run a project's tests, for the citation link in
# executed_tests: a claim's own verified citation can tie it to a
# test run whose command does not textually name the declared test,
# but never to a non-test artifact (a spec read, a file listing).
_TEST_RUNNER_MARKERS = ("pytest", "unittest", "npm test", "yarn test", "go test",
                        "cargo test", "jest", "mocha", "rspec", "phpunit",
                        "mvn test", "gradle test", "ctest", "tox",
                        "make test", "make check")


def executed_tests(claims, store, attempt_id):
    """Per-claim record of falsification tests actually executed in
    this attempt (protocol amendment 2026-10-20, PC-1).

    A test counts as executed when a tool artifact of this attempt is
    tied to the claim in either of two inspectable ways: the artifact
    records a command matching one of the claim's declared
    falsification tests, or the claim's evidence cites the artifact,
    the citation verifies against the store (the grounded_claims
    predicate) and the artifact records a test-runner command.
    ``passed`` is True only when every tied tool event exited 0; a
    missing exit code is unknown, never a pass. ``acceptance`` names
    the declared test a passing executed run was a run of, when one
    was, with that run's artifact digest; only the command-match
    link names a declared test, so only it can carry acceptance.
    """
    events = {}
    for event in store.events("tools"):
        if event.get("attempt_id") != attempt_id:
            continue
        artifact = event.get("artifact") or {}
        if artifact.get("sha256"):
            events[artifact["sha256"]] = event

    def artifact_content(event):
        path = store.root/event["artifact"]["path"]
        if not path.is_file():
            return {}
        try:
            content = read_json(path)
        except (OSError, ValueError):
            return {}
        return content if isinstance(content, dict) else {}

    executed = {}
    for claim in claims.get("claims", []):
        tests = [t for t in claim.get("falsification_tests", [])
                 if isinstance(t, str) and t.strip()]
        tied = {}
        for digest, event in events.items():
            if _command_matches_tests(artifact_content(event).get("command"), tests):
                tied[digest] = event
        for evidence in claim.get("evidence", []):
            digest = evidence.get("source_id")
            event = events.get(digest)
            if not event or digest in tied:
                continue
            ref = event["artifact"]
            path = store.root/ref["path"]
            if (evidence.get("ref") != ref["path"] or not path.is_file()
                    or sha(path.read_bytes()) != digest):
                continue
            command = _test_text(artifact_content(event).get("command"))
            if any(marker in command for marker in _TEST_RUNNER_MARKERS):
                tied[digest] = event
        if not tied:
            continue
        artifacts = []
        acceptance = None
        for digest, event in sorted(tied.items()):
            command = artifact_content(event).get("command")
            artifacts.append(dict(sha256=digest, path=event["artifact"]["path"],
                                  command=command, exit_code=event.get("exit_code")))
            if acceptance is None and event.get("exit_code") == 0:
                matched = _command_matches_tests(command, tests)
                if matched:
                    acceptance = dict(test=matched, sha256=digest)
        executed[claim["id"]] = dict(
            artifacts=artifacts,
            passed=all(a["exit_code"] == 0 for a in artifacts),
            acceptance=acceptance)
    return executed


def attach_verification_evidence(claims, executed):
    """Attach the phase's real verification artifacts as distinct
    evidence sources (PC-1): one observed item per executed artifact
    on the claims that artifact verifies, unless the claim already
    cites that artifact. The engine's independence component then
    counts distinct real sources instead of one shared source."""
    claims = json.loads(json.dumps(claims))
    for claim in claims.get("claims", []):
        record = executed.get(claim.get("id"))
        if not record:
            continue
        cited = {e.get("source_id") for e in claim.get("evidence", [])}
        for artifact in record["artifacts"]:
            if artifact["sha256"] in cited:
                continue
            claim.setdefault("evidence", []).append(dict(
                kind="observed", source_id=artifact["sha256"], ref=artifact["path"],
                source_quality="test",
                description="Phase verification artifact: "
                            + (artifact["command"] or "tool run")
                            + f" (exit code {artifact['exit_code']})"))
            cited.add(artifact["sha256"])
    return claims


def composed_lanes(composed):
    """The engine's lane pair carried through composition (Spec 004
    R6.2): lane 1 machine verification, lane 2 human acceptance
    state, verbatim — never blended, never rescored here."""
    states = (composed.get("metadata") or {}).get("lane_states") or []
    for state in states:
        if isinstance(state, dict) and isinstance(state.get("lane_1"), dict):
            return {"lane_1": state["lane_1"], "lane_2": state.get("lane_2")}
    return {}


def gate_outcome_of(result):
    """Gate eligibility reads lane 1 (PC-2): the lane 1 outcome when
    the result carries one, else the headline outcome."""
    lanes = result.get("lanes") or composed_lanes(result)
    lane_1 = lanes.get("lane_1") or {}
    return lane_1.get("outcome") or result["outcome"]


def compact_feedback(result):
    """Compact projection of an assessment result for the persistent
    conversation (needle program Workstream A1). The full composed
    result stays in the run store for audit; only this projection is
    appended to the conversation, where it is re-sent on every later
    call. It mirrors matched_repair.compact_assessment's base keys
    (outcome, findings, next_action, confidence, uncertainty),
    extended with the Spec 006 additions: the gate outcome, the lane
    pair slimmed to what a repair decision needs (lane 1 outcome;
    lane 2 stage counts and claims below explained), and the
    recorded-acts summary. The key set is exactly these eight keys."""
    lanes = result.get("lanes") or composed_lanes(result)
    lane_1 = lanes.get("lane_1") or {}
    lane_2 = lanes.get("lane_2") or {}
    summary = result.get("recorded_acts_summary")
    if isinstance(summary, dict):
        summary = {"count": summary.get("count", 0),
                   "basis_types": summary.get("basis_types") or [],
                   "actor": summary.get("actor") or PIPELINE_ACTOR}
    else:
        acts = result.get("recorded_acts") or []
        summary = {"count": len(acts),
                   "basis_types": sorted({a.get("basis_type") for a in acts
                                          if isinstance(a, dict) and a.get("basis_type")}),
                   "actor": PIPELINE_ACTOR}
    return {
        "outcome": result.get("outcome"),
        "findings": result.get("findings"),
        "next_action": result.get("next_action"),
        "confidence": result.get("confidence"),
        "uncertainty": result.get("uncertainty"),
        "gate_outcome": result.get("gate_outcome") or lane_1.get("outcome")
                        or result.get("outcome"),
        "lanes": {"lane_1": {"outcome": lane_1.get("outcome")},
                  "lane_2": {"stage_counts": lane_2.get("stage_counts"),
                             "claims_below_explained": lane_2.get("claims_below_explained")}},
        "recorded_acts_summary": summary,
    }


class DeltaFormatError(ValueError):
    """A claims submission the harness cannot merge (needle program
    Workstream A2). This is a model outcome: the runner feeds the
    reason back inside the phase and the model resubmits; it is never
    an infrastructure error."""


def merge_claim_delta(standing, submission):
    """Merge a delta submission into the standing bundle.

    Delta form: {"delta": {"upsert": [full claim objects, each
    carrying its claim id], "withdraw": [claim ids]}}. Upserts given
    as an object keyed by claim id are also accepted, provided each
    key equals its claim's id. Withdrawals are applied first, then
    upserts (an upsert of a withdrawn id re-adds it). An upsert
    replaces the standing claim with the same id in place; a new id
    is appended. Raises DeltaFormatError on any malformed shape, on
    an upsert without an id, and on a withdrawal naming an unknown
    claim id."""
    if not isinstance(standing, dict) or not isinstance(standing.get("claims"), list):
        raise DeltaFormatError("no standing claims bundle to merge a delta into")
    delta = submission.get("delta") if isinstance(submission, dict) else None
    if not isinstance(delta, dict):
        raise DeltaFormatError("claims delta must be an object with 'upsert' and/or 'withdraw'")
    unknown = set(delta) - {"upsert", "withdraw"}
    if unknown:
        raise DeltaFormatError(f"unknown delta keys: {sorted(unknown)}")
    upsert_raw = delta.get("upsert") or []
    if isinstance(upsert_raw, dict):
        upserts = []
        for key, claim_obj in upsert_raw.items():
            if not isinstance(claim_obj, dict) or claim_obj.get("id") != key:
                raise DeltaFormatError(
                    f"delta upsert keyed by {key!r} must be a full claim object with that id")
            upserts.append(claim_obj)
    elif isinstance(upsert_raw, list):
        upserts = upsert_raw
    else:
        raise DeltaFormatError("delta 'upsert' must be a list of full claim objects")
    for claim_obj in upserts:
        if not isinstance(claim_obj, dict) or not claim_obj.get("id"):
            raise DeltaFormatError("each delta upsert must be a full claim object with an 'id'")
    withdraw_raw = delta.get("withdraw") or []
    if (not isinstance(withdraw_raw, list)
            or not all(isinstance(w, str) and w for w in withdraw_raw)):
        raise DeltaFormatError("delta 'withdraw' must be a list of claim ids")
    merged = json.loads(json.dumps(standing))
    claims = merged["claims"]
    index = {c.get("id"): i for i, c in enumerate(claims) if isinstance(c, dict)}
    for claim_id in withdraw_raw:
        if claim_id not in index:
            raise DeltaFormatError(f"delta withdraws unknown claim id: {claim_id}")
        claims.pop(index[claim_id])
        index = {c.get("id"): i for i, c in enumerate(claims) if isinstance(c, dict)}
    for claim_obj in upserts:
        claim_id = claim_obj["id"]
        if claim_id in index:
            claims[index[claim_id]] = json.loads(json.dumps(claim_obj))
        else:
            index[claim_id] = len(claims)
            claims.append(json.loads(json.dumps(claim_obj)))
    return merged


def resolve_claim_submission(base, submission):
    """Resolve one phase's claims submission to the bundle to assess
    (Workstream A2). A full bundle (a 'claims' list) replaces the
    base; a delta merges into the base. ``base`` is the standing
    bundle, or the pending consolidation candidate when a phase is
    revising after a consolidation request. Raises DeltaFormatError
    for malformed submissions, for a submission carrying both forms,
    and for a delta with no base to merge into."""
    if not isinstance(submission, dict) or not submission:
        raise DeltaFormatError(
            "claims submission must be an object: a full claims bundle or a delta")
    if "delta" in submission:
        if "claims" in submission:
            raise DeltaFormatError(
                "submit either a full claims bundle or a delta, not both")
        if base is None:
            raise DeltaFormatError(
                "the first assessed phase must submit a full claims bundle; "
                "a delta has no standing bundle to merge into")
        return merge_claim_delta(base, submission)
    if isinstance(submission.get("claims"), list):
        return json.loads(json.dumps(submission))
    raise DeltaFormatError(
        "claims submission must carry a 'claims' list (full bundle) or a 'delta' object")


def campaign_setup(store, setup_key):
    """The frozen campaign setup record for a task (PC-3), or None.
    With setup sharing enabled, the first attempt that completes the
    constitution phase freezes its completion record once per
    campaign and task; later attempts reuse it."""
    for event in store.events("campaign_setups"):
        if event.get("setup_key") == setup_key:
            return event
    return None


def record_phase_acts(bundle, claims, executed, phase, env):
    """Recorded acts on the assessed bundle (PC-1), issued through
    the engine's own recorded-act commands so every act carries its
    basis type in the bundle and the acts ledger. The harness records
    no human act and never records ``explained`` (a named human's
    exposition); acceptance is recorded only on a test verdict, and
    only where an executed passing run is the claim's own declared
    acceptance test. A refused act is recorded, never hidden."""
    acts = []
    by_id = {c.get("id"): c for c in claims.get("claims", [])}
    ledger = bundle.parent/"recorded-acts-ledger.jsonl"
    for claim_id, record in executed.items():
        claim = by_id.get(claim_id) or {}
        tests = [t for t in claim.get("falsification_tests", [])
                 if isinstance(t, str) and t.strip()]
        first = record["artifacts"][0]
        test_id = tests[0] if tests else (first["command"] or first["sha256"])
        verdict = "pass" if record["passed"] else "fail"
        commands = "; ".join(a["command"] or a["sha256"] for a in record["artifacts"])

        def run(kind, *args, act_test_id=None, act_test_hash=None, act_verdict=None):
            result = subprocess.run([sys.executable, "-m", "aee", *args],
                                    capture_output=True, env=env, timeout=60)
            entry = dict(claim_id=claim_id, kind=kind, basis_type="test-verdict",
                         test_id=act_test_id or test_id,
                         test_hash=act_test_hash or first["sha256"],
                         test_result=act_verdict or verdict,
                         exit_code=result.returncode)
            if result.returncode:
                entry["error"] = result.stderr.decode("utf-8", errors="replace").strip()[:300]
            acts.append(entry)
            return result.returncode == 0

        stage_now = claim.get("stage") or "created"
        if stage_now == "created":
            if run("stage", "stage", str(bundle), "--claim", claim_id, "--to", "checked",
                   "--basis", f"Phase {phase} executed falsification tests: {commands}",
                   "--recorded-by", PIPELINE_ACTOR, "--basis-type", "test-verdict",
                   "--test-id", test_id, "--test-hash", first["sha256"],
                   "--test-result", verdict, "--ledger", str(ledger)):
                stage_now = "checked"
        if record["passed"] and (claim.get("status") or "draft") == "draft" and stage_now != "created":
            run("ratify", "ratify", str(bundle), "--claim", claim_id, "--status", "supported",
                "--basis", f"Phase {phase} checks passed: {commands}",
                "--recorded-by", PIPELINE_ACTOR, "--basis-type", "test-verdict",
                "--test-id", test_id, "--test-hash", first["sha256"],
                "--test-result", "pass", "--ledger", str(ledger))
        acceptance = record.get("acceptance")
        if record["passed"] and acceptance and stage_now == "checked":
            run("stage", "stage", str(bundle), "--claim", claim_id, "--to", "accepted",
                "--basis", f"Acceptance test executed and passed in phase {phase}: {acceptance['test']}",
                "--recorded-by", PIPELINE_ACTOR, "--basis-type", "test-verdict",
                "--test-id", acceptance["test"], "--test-hash", acceptance["sha256"],
                "--test-result", "pass", "--ledger", str(ledger),
                act_test_id=acceptance["test"], act_test_hash=acceptance["sha256"],
                act_verdict="pass")
    return acts


def phases(arm):
    if arm == "baseline":
        return ("solve",)
    if arm not in ("spec_kit", "spec_kit_aee"):
        raise ValueError("unknown arm")
    return PHASES


def phase_prompt(root, arm, phase):
    base = (Path(root)/"prompts"/"common.md").read_text(encoding="utf-8")
    if arm == "baseline":
        return base
    skill = (Path(root)/"prompts"/"skills"/f"speckit-{phase}.md").read_text(encoding="utf-8")
    return base + "\n" + (Path(root)/"prompts"/"adapter.md").read_text() + "\n" + skill


def _installed_evaluator_file(sandbox, path):
    """True for files of the evaluator extension installed into the
    sandbox project — everything under .specify/extensions/evaluator
    except the results the run itself produced there. Installed bytes
    are the vendored pin's, not assessment evidence."""
    rel = path.relative_to(sandbox).parts
    return rel[:3] == (".specify", "extensions", "evaluator") and rel[3:4] != ("results",)


def assess(root, claims, phase, store, attempt_id):
    if not isinstance(claims, dict) or not claims.get("claims"):
        raise ValueError("AEE phase must submit explicit claim JSON")
    # PC-1: the phase's real verification artifacts are attached as
    # distinct evidence sources before the assessment runs, so the
    # engine scores independence from what the phase actually ran.
    executed = executed_tests(claims, store, attempt_id)
    claims = attach_verification_evidence(claims, executed)
    # Fresh project root prevents timestamp collisions and cross-attempt discovery.
    with tempfile.TemporaryDirectory(prefix="aee-assessment-") as folder:
        sandbox = Path(folder)
        write_json(sandbox/"claims.json", claims)
        # The pair is one system (AEE extension Spec 005 ER-01): the
        # vendored runner's assess refuses (exit 2) unless the
        # evaluator extension is installed in the project, so the fresh
        # project gets the vendored evaluator tree installed, as the
        # frozen-input projects get both extensions (experiment.py).
        # The vendored results/ directory is benchmark-local output,
        # not part of the installed extension, and is not copied.
        shutil.copytree(Path(root)/".specify/extensions/evaluator",
                        sandbox/".specify/extensions/evaluator",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "results"))
        env = {**os.environ, "PATH": str(Path(sys.executable).parent)+os.pathsep+os.environ.get("PATH", ""),
               "PYTHONUTF8": "1"}
        script = Path(root)/".specify/extensions/aee/scripts/python/run_aee.py"
        result = subprocess.run([sys.executable, str(script), "--project-root", folder, "assess",
                                 "--input", "claims.json", "--phase", "after_"+phase],
                                capture_output=True, env=env, timeout=60)
        result_dir = sandbox/".specify/extensions/evaluator/results"
        files = list(result_dir.glob("*.json"))
        if not files:
            diagnostic=store.artifact(canonical(dict(phase=phase,claims=claims,
                exit_code=result.returncode,stdout=result.stdout.decode('utf-8',errors='replace'),
                stderr=result.stderr.decode('utf-8',errors='replace'))))
            store.append("assessment_errors",dict(phase=phase,timestamp=utc(),artifact=diagnostic))
            raise RuntimeError("AEE emitted no evaluator result")
        result_path = sandbox/"composed.json"
        compose = Path(root)/".specify/extensions/evaluator/scripts/python/compose_results.py"
        # Upstream schema lookup is relative to script; installed extension remains intact.
        # Compose exit codes are the FR-6 gate contract, not process failure:
        # 0 = pass/warn, 1 = iterate/clarify/gather_evidence, 2 = block (or a
        # hard error, which writes no output). A composed file is a valid
        # result at any of these exits; only a missing file is an error.
        composed_run = subprocess.run([sys.executable, str(compose), "--results-dir", str(result_dir),
                        "--phase", "after_"+phase, "--strategy", "strict", "--output", str(result_path)],
                       capture_output=True, env=env, timeout=60)
        if not result_path.exists():
            raise RuntimeError("evaluator composition produced no result: "
                               + composed_run.stderr.decode("utf-8", errors="replace"))
        composed = read_json(result_path)
        # The vendored evaluator (FR-6 build) composes schema-valid output.
        # These two normalizations remain as defense against legacy composed
        # files only: Evaluator 1.0.0 emitted model_routing:null contrary to
        # its schema and injected _evaluator_id into findings.
        if composed.get("model_routing", "absent") is None:
            composed.pop("model_routing")
        for finding in composed.get("findings", []):
            # Internal composition provenance is retained in raw output and
            # evaluator summaries, but is not a finding-schema property.
            finding.pop("_evaluator_id", None)
        import jsonschema
        jsonschema.validate(composed, read_json(Path(root)/".specify/extensions/evaluator/schemas/evaluator-result.schema.json"))
        if composed["metadata"]["evaluator_count"] != 1:
            raise RuntimeError("composition did not consume the expected AEE result")
        # PC-2: the lane pair rides on the returned result (never on
        # the schema-valid composed record stored below); gate
        # eligibility reads lane 1.
        lanes = composed_lanes(composed)
        gate_outcome = (lanes.get("lane_1") or {}).get("outcome") or composed["outcome"]
        # PC-1: recorded acts land on the assessed bundle after the
        # assessment, so the stored bundle carries the stage events,
        # any ratification and the attached verification evidence.
        acts = record_phase_acts(sandbox/"claims.json", claims, executed, phase, env) if executed else []
        refs = [store.artifact(p.read_bytes()) for p in sandbox.rglob("*.json")
                if not _installed_evaluator_file(sandbox, p)]
        acts_ledger = sandbox/"recorded-acts-ledger.jsonl"
        if acts_ledger.is_file():
            refs.append(store.artifact(acts_ledger.read_bytes()))
        refs.append(store.artifact(canonical(composed)))
        report = f"# Evaluator report — after_{phase}\n\nOutcome: {composed['outcome']}\n"
        report += f"Gate outcome (lane 1, machine verification): {gate_outcome}\n"
        if lanes:
            lane_2 = lanes.get("lane_2") or {}
            report += ("Lane 2 (human acceptance): stages "
                       + json.dumps(lane_2.get("stage_counts") or {}, sort_keys=True)
                       + f"; claims below explained: {lane_2.get('claims_below_explained')}\n")
        if acts:
            report += (f"Recorded acts: {len(acts)} on a test-verdict basis "
                       f"by {PIPELINE_ACTOR} (see the assessments record)\n")
        report += "\n"
        report += "\n".join(json.dumps(f, sort_keys=True) for f in composed.get("findings", []))
        report += "\n\nNext action: " + json.dumps(composed.get("next_action")) + "\n"
        refs.append(store.artifact(report.encode()))
        lane_2 = lanes.get("lane_2") or {}
        store.append("assessments", dict(attempt_id=attempt_id, phase=phase, timestamp=utc(),
                                          outcome=composed["outcome"],
                                          gate_outcome=gate_outcome,
                                          lane_1_outcome=(lanes.get("lane_1") or {}).get("outcome"),
                                          lane_2_stage_counts=lane_2.get("stage_counts"),
                                          recorded_acts=acts,
                                          # A3(c): per-phase claim count of the
                                          # assessed bundle, so the next study
                                          # can measure claim-count discipline.
                                          claim_count=len(claims.get("claims") or []),
                                          aee_exit_code=result.returncode, artifacts=refs))
        augmented = dict(composed)
        augmented["gate_outcome"] = gate_outcome
        if lanes:
            augmented["lanes"] = lanes
        # A1: a small recorded-acts summary rides on the returned
        # augmentation only (the stored composed record above stays
        # schema-valid and untouched), so the compact conversation
        # projection can carry it without the full acts list.
        augmented["recorded_acts_summary"] = {
            "count": len(acts),
            "basis_types": sorted({a.get("basis_type") for a in acts if a.get("basis_type")}),
            "actor": PIPELINE_ACTOR}
        return augmented

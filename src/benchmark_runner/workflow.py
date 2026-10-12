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
        refs = [store.artifact(p.read_bytes()) for p in sandbox.rglob("*.json")
                if not _installed_evaluator_file(sandbox, p)]
        refs.append(store.artifact(canonical(composed)))
        report = f"# Evaluator report — after_{phase}\n\nOutcome: {composed['outcome']}\n\n"
        report += "\n".join(json.dumps(f, sort_keys=True) for f in composed.get("findings", []))
        report += "\n\nNext action: " + json.dumps(composed.get("next_action")) + "\n"
        refs.append(store.artifact(report.encode()))
        store.append("assessments", dict(attempt_id=attempt_id, phase=phase, timestamp=utc(),
                                          outcome=composed["outcome"],
                                          aee_exit_code=result.returncode, artifacts=refs))
        return composed

"""Frozen skill adapter and explicit deterministic AEE/Evaluator execution."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .store import canonical, read_json, sha, utc, write_json

PHASES = ("constitution", "specify", "plan", "tasks", "implement", "converge")
AEE_PHASES = {"specify", "plan", "tasks", "implement"}


def grounded_claims(claims, store, attempt_id):
    """A model cannot promote invented evidence to a recorded observation."""
    claims = json.loads(json.dumps(claims))
    allowed = {e["artifact"]["sha256"]: e["artifact"] for e in store.events("tools")
               if e.get("attempt_id") == attempt_id}
    for claim in claims.get("claims", []):
        for evidence in claim.get("evidence", []):
            digest = evidence.get("source_id")
            ref = allowed.get(digest)
            verified = ref and evidence.get("ref") == ref["path"] and sha((store.root/ref["path"]).read_bytes()) == digest
            if evidence.get("kind") == "observed" and not verified:
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


def assess(root, claims, phase, store):
    if not isinstance(claims, dict) or not claims.get("claims"):
        raise ValueError("AEE phase must submit explicit claim JSON")
    # Fresh project root prevents timestamp collisions and cross-attempt discovery.
    with tempfile.TemporaryDirectory(prefix="aee-assessment-") as folder:
        sandbox = Path(folder)
        write_json(sandbox/"claims.json", claims)
        env = {**os.environ, "PATH": str(Path(sys.executable).parent)+os.pathsep+os.environ.get("PATH", ""),
               "PYTHONUTF8": "1"}
        script = Path(root)/".specify/extensions/aee/scripts/python/run_aee.py"
        result = subprocess.run([sys.executable, str(script), "--project-root", folder, "assess",
                                 "--input", "claims.json", "--phase", "after_"+phase],
                                capture_output=True, env=env, timeout=60)
        result_dir = sandbox/".specify/extensions/evaluator/results"
        files = list(result_dir.glob("*.json"))
        if not files:
            raise RuntimeError("AEE emitted no evaluator result")
        result_path = sandbox/"composed.json"
        compose = Path(root)/".specify/extensions/evaluator/scripts/python/compose_results.py"
        # Upstream schema lookup is relative to script; installed extension remains intact.
        subprocess.run([sys.executable, str(compose), "--results-dir", str(result_dir),
                        "--phase", "after_"+phase, "--strategy", "strict", "--output", str(result_path)],
                       check=True, capture_output=True, env=env, timeout=60)
        composed = read_json(result_path)
        # Evaluator 1.0.0 emits optional model_routing:null, contrary to its schema.
        # Preserve raw output below, normalize only absent optional routing in adapter.
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
        refs = [store.artifact(p.read_bytes()) for p in sandbox.rglob("*.json")]
        refs.append(store.artifact(canonical(composed)))
        report = f"# Evaluator report — after_{phase}\n\nOutcome: {composed['outcome']}\n\n"
        report += "\n".join(json.dumps(f, sort_keys=True) for f in composed.get("findings", []))
        report += "\n\nNext action: " + json.dumps(composed.get("next_action")) + "\n"
        refs.append(store.artifact(report.encode()))
        store.append("assessments", dict(phase=phase, timestamp=utc(), outcome=composed["outcome"],
                                          aee_exit_code=result.returncode, artifacts=refs))
        return composed

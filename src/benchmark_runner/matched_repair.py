"""Cloud port of the matched-repair protocol (scripts/matched_repair.py).

Runs the paired identical-start repair design on the cloud runner's
OpenAIProvider: one shared read-only diagnostic per fixture pair, then two
repair arms (ordinary vs AEE-guided) from the same pristine fixture snapshot.
Hidden grading happens after all runs; hidden outcomes are never fed back.

Arms: ``diagnose``, ``repair_ordinary``, ``repair_guided``.

The v3 structural diagnostic-termination fix from scripts/repeated_local.py
(Session.phase) is ported here verbatim in spirit: claim-bearing phases get a
done-only final step and a mid-phase draft-claims checkpoint, and a
non-terminating phase records an honest terminal done (adopting a valid
mid-phase draft, or a single explicit DIAG-NONTERMINATION-01 claim) instead of
executing a coerced action.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import random
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from .accounting import TOKEN_FIELDS, request_prices
from .experiment import frozen_paths, source_hash
from .isolation import docker_args
from .store import Store, canonical, read_json, sha, utc, write_json
from .workflow import assess, grounded_claims

ROOT = Path(__file__).resolve().parents[2]

MATCHED_ARMS = ("diagnose", "repair_ordinary", "repair_guided")

# (before, after, seeded_requirements) — ported from scripts/matched_repair.py.
VARIANTS = {
    "tinydb": {
        "bool_id": ("type(ident) is not int", "not isinstance(ident, int)", ["R04"]),
        "token_alias": ("self.tokens[token] = (deepcopy(operations), deepcopy(inserted))",
                        "self.tokens[token] = (deepcopy(operations), inserted)", ["R08"]),
        "partial_commit": ("docs[next_id] = deepcopy(op['document'])",
                           "docs[next_id] = deepcopy(op['document']); self.db.storage.write({'_default':docs})",
                           ["R02", "R05"]),
        "clean": (None, None, []),
    },
    "cachetools": {
        "expiry_boundary": ("now >= entry[2]", "now > entry[2]", ["R07", "R08"]),
        "value_alias": ("return deepcopy(self._cache[key][0])", "return self._cache[key][0]", ["R01", "R06"]),
        "boolean_ttl": ("isinstance(ttl, bool) or not isinstance(ttl, (int,float))",
                        "not isinstance(ttl, (int,float))", ["R07"]),
        "clean": (None, None, []),
    },
}

# Synthetic benchmark module placed into the real upstream package, mirroring
# scripts/repeated_local.py PROJECTS (module = synthetic file under test).
PROJECTS = {
    "tinydb": {"upstream": "/tmp/upstreams/tinydb", "package": "tinydb",
               "module": "tinydb/journal.py", "revision": "19066e03139e904c24410e23901e4b069d715a2e"},
    "cachetools": {"upstream": "/tmp/upstreams/cachetools", "package": "src/cachetools",
                   "module": "src/cachetools/tagged.py", "revision": "c403f9f4185e58090b904c1915345b9ba46d5a08"},
}

SEEDS = [20260918, 20260919]

DIAGNOSTIC_CALLS = 8
REPAIR_ROUNDS = 2
CALLS_PER_ROUND = 8

COMMON = """You are a capable software engineering agent in an isolated real repository.
Return exactly one JSON action: {"action":"shell","command":"..."} or
{"action":"done","summary":"..."}.
Use shell to inspect/edit source and run tests. No internet or human assistance.
Do not modify upstream tests or acceptance_public.py. You may add your own tests.
All shell commands run in /testbed. Use PYTHONPATH=src:. for repository imports.
Do not fabricate test evidence. Hidden acceptance is unavailable. Inspect concise
outputs; full tool outputs are retained as evidence.
"""

CLAIMS = """At phase completion, include a claims object in your done JSON. Extract actual
observations, not generic assertions. Example shape (replace example values):
"claims":{"schema_version":"1.0","claims":[{"id":"D01","text":"bounded claim",
"kind":"hypothesis","status":"unsupported","boundary":["diagnose"],
"depends_on":[],"conflicts_with":[],"falsification_tests":["specific counterexample"],
"source_ref":"phase transcript","uncertainty":"high","evidence":[]}]}
Inside its evidence array, for actual shell evidence use kind="observed",
ref=<evidence_ref returned by shell>, source_id=<source_id returned by shell>,
direction="supports" and a scoped description. Unverified prose stays asserted.
"""

PAIR_RE = re.compile(r"^mr-([a-z]+)-([a-z_]+)-(\d+)$")


def pair_of(instance_id):
    m = PAIR_RE.fullmatch(instance_id)
    if not m:
        raise ValueError(f"not a matched-repair instance id: {instance_id}")
    project, variant, seed = m.group(1), m.group(2), int(m.group(3))
    if project not in PROJECTS or variant not in VARIANTS[project]:
        raise ValueError(f"unknown matched-repair pair: {instance_id}")
    return project, variant, seed


def variant_source(project, variant):
    text = (ROOT / "benchmarks/repeated_local" / project / "reference.py").read_text()
    before, after, _ = VARIANTS[project][variant]
    if before:
        assert text.count(before) == 1, f"variant anchor not unique: {project}/{variant}"
        text = text.replace(before, after)
    return text.encode()


def spec_text(project):
    task = ROOT / "benchmarks/repeated_local" / project
    return "\n\n".join((task / f"stage{i}.md").read_text() for i in (1, 2, 3))


def compact_assessment(value):
    return {k: value.get(k) for k in ("outcome", "findings", "next_action", "confidence", "uncertainty") if k in value}


def tests_for(project, stage, public):
    source = (ROOT / "benchmarks/repeated_local" / project / "tests.py").read_text()
    parts = source.split("# STAGE2")
    first = parts[0]
    second, third = parts[1].split("# STAGE3")
    chosen = first + (second if stage >= 2 else "") + (third if stage >= 3 else "")
    if not public:
        return chosen.encode()
    tree = ast.parse(chosen)
    keep = [node for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or not node.name.startswith("test_") or node.name.startswith("test_public_")]
    tree.body = keep
    return ast.unparse(tree).encode()


# ---------------------------------------------------------------------------
# v3 structural termination port (from scripts/repeated_local.py Session.phase)
# ---------------------------------------------------------------------------

from .runner import LimitHit, MiniEnvironment, MiniModel, remaining  # noqa: E402


class MatchedModel(MiniModel):
    """MiniModel that also accepts a draft claims action in claim-bearing phases."""

    def begin_phase(self, claims, limit):
        self.claims_phase = claims
        self.limit = limit

    def query(self, messages):
        cleaned = [{"role": m["role"], "content": m["content"]} for m in messages]
        text = self.provider.query(cleaned, self.phase, min(remaining(self.deadline), 120))
        try:
            action = json.loads(text)
            allowed = ("shell", "done") + (("draft",) if self.claims_phase else ())
            if not isinstance(action, dict) or action.get("action") not in allowed:
                raise ValueError("expected shell, done" + (", or draft" if self.claims_phase else ""))
            if action["action"] == "shell" and not isinstance(action.get("command"), str):
                raise ValueError("shell command must be string")
            self.last = action
        except (ValueError, TypeError):
            self.last = {"action": "invalid"}
            action = self.last
        return {"role": "assistant", "content": text,
                "extra": {"actions": [action] if action["action"] == "shell" else []}}


def _terminal_done(phase, limit, draft_claims):
    """Honest terminal done for a claim-bearing phase that exhausts its action
    budget without the model returning done. Ported from Session._terminal_done:
    never invents grounded claims."""
    from aee.model import Claim
    if draft_claims is not None:
        bundle = draft_claims
        summary = ("Phase %s ended without an explicit done: the model did not terminate within its %d allocated actions. "
                   "The recorded mid-phase draft claims are reported as the terminal claims; treat them as unrefined." % (phase, limit))
    else:
        bundle = {"schema_version": "1.0", "claims": [{
            "id": "DIAG-NONTERMINATION-01",
            "text": ("The %s phase exhausted its %d allocated actions without the model returning done. "
                     "No grounded defect claims were established; every defect claim remains unsupported." % (phase, limit)),
            "kind": "hypothesis", "status": "unsupported", "boundary": [phase],
            "depends_on": [], "conflicts_with": [],
            "falsification_tests": ["Re-run the phase and observe whether done is returned within the action budget"],
            "source_ref": "phase transcript", "uncertainty": "high", "evidence": []}]}
        summary = ("Phase %s exhausted its %d allocated actions without the model returning done. "
                   "No grounded claims were produced; the terminal claim records this non-termination honestly." % (phase, limit))
    for c in bundle["claims"]:
        Claim.from_dict(c)
    return {"action": "done", "summary": summary, "claims": bundle, "terminal_synthesized": True}


def _validate_claims_bundle(bundle, draft=False):
    from aee.model import Claim
    if not isinstance(bundle, dict) or not bundle.get("claims"):
        raise ValueError("Nonempty %s claims required" % ("draft" if draft else ""))
    for c in bundle["claims"]:
        Claim.from_dict(c)
    return bundle


def run_matched_phase(agent, model, store, identity, cfg, phase, instructions, spec, limit, deadline, claims):
    """One phase with the v3 structural termination discipline. Returns a
    summary dict mirroring Session.phase: {phase, done, completed, errors, calls}."""
    model.phase = phase
    model.begin_phase(claims, limit)
    agent.add_messages(
        {"role": "system", "content": COMMON + "\nCURRENT PHASE: " + phase + "\n" + instructions + ("\n" + CLAIMS if claims else "")},
        {"role": "user", "content": spec})
    agent.add_messages({"role": "user", "content": (
        f"Begin the current {phase} phase now. You have at most {limit} actions in this phase, including done. "
        "Complete its requested deliverable, then return done.")})
    done, errors = None, []
    draft_step = limit // 2 if (claims and limit >= 6) else None
    draft_claims = None
    start_calls = agent.n_calls
    for step in range(limit):
        if (store.root / "CANCEL").exists():
            raise KeyboardInterrupt("cancelled")
        if step == limit - 1 and claims:
            agent.add_messages({"role": "user", "content": (
                'FINAL STEP: this is the last allocated action for this phase. Only a done action is accepted now. '
                'Return {"action":"done","summary":"...","claims":{"schema_version":"1.0","claims":[...]}} with your best current claims object'
                + (' (finalize your recorded mid-phase draft)' if draft_claims else '')
                + '. Shell actions are no longer available: any other action ends the phase and the harness records an honest terminal done.')})
        elif step == limit - 1:
            agent.add_messages({"role": "user", "content": (
                "This is the last allocated action for this phase. Return done now with an honest summary of completed and unresolved work. "
                "Do not perform another shell action.")})
        elif draft_step is not None and step == draft_step:
            agent.add_messages({"role": "user", "content": (
                'MID-PHASE CHECKPOINT (action %d of %d). Return a draft claims object now: '
                '{"action":"draft","claims":{"schema_version":"1.0","claims":[...]}} with your current best hypothesis claims; '
                "they may be refined later, and you may also return done if finished. Shell exploration may continue afterwards, "
                "but this step does not accept shell actions." % (step + 1, limit))})
        elif step == limit - 2:
            agent.add_messages({"role": "user", "content": (
                "Two actions remain in this phase. Finish the requested artifact/check now and use done to report its actual state; "
                "preserve unresolved issues.")})
        calls = [c for c in store.events("calls") if c["attempt_id"] == identity["attempt_id"]]
        if calls and any(c["input_tokens"] is None or c["output_tokens"] is None for c in calls):
            raise LimitHit("unknown token usage; cannot enforce attempt token ceiling")
        used = sum(c["input_tokens"] + c["output_tokens"] for c in calls)
        if used + cfg["max_input_tokens"] + cfg["max_output_tokens"] > cfg["token_cap"]:
            raise LimitHit("next request token reservation exceeds attempt cap")
        if agent.n_calls >= cfg["max_calls"]:
            raise LimitHit("call limit")
        try:
            message = agent.query()
            action = model.last
            if claims and step == limit - 1 and action.get("action") != "done":
                # Structural termination: a non-done final action is not
                # executed. A draft returned on the final step is adopted as
                # the terminal claims; otherwise an honest terminal done is
                # synthesized (never inventing grounded claims).
                if action.get("action") == "draft":
                    try:
                        draft_claims = _validate_claims_bundle(action.get("claims"), draft=True)
                    except (ValueError, TypeError) as exc:
                        errors.append("FinalDraftInvalid: " + str(exc)[:200])
                done = _terminal_done(phase, limit, draft_claims)
                errors.append("TerminalActionCoerced: non-done action on the final step was not executed; recorded honest terminal done")
                break
            if draft_step is not None and step == draft_step and action.get("action") not in ("draft", "done"):
                raise ValueError("Mid-phase draft claims required on this step: return {\"action\":\"draft\",\"claims\":{...}} or done")
            if claims and action.get("action") == "draft":
                draft_claims = _validate_claims_bundle(action.get("claims"), draft=True)
                agent.add_messages({"role": "user", "content": (
                    "Draft claims recorded (%d claim(s)). Continue exploration or refinement; "
                    "your final done must still include the complete claims object." % len(draft_claims["claims"]))})
                continue
            if action.get("action") == "done":
                if claims:
                    _validate_claims_bundle(action.get("claims"))
                done = action
                break
            # shell actions execute; invalid actions yield the model's own
            # correction prompt via format_observation_messages (no execution).
            agent.execute_actions(message)
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc)[:500])
            if isinstance(exc, (LimitHit, KeyboardInterrupt)):
                raise
            agent.add_messages({"role": "user", "content": "Last action/request failed: " + errors[-1] + ". Correct the action; do not invent evidence."})
    artifact = store.artifact(canonical({"phase": phase, "done": done, "errors": errors}))
    store.append("phases", {**identity, "phase": phase, "timestamp": utc(), "artifact": artifact,
                            "completed": done is not None, "calls": agent.n_calls - start_calls})
    return {"phase": phase, "done": done, "completed": done is not None, "errors": errors,
            "calls": agent.n_calls - start_calls}


# ---------------------------------------------------------------------------
# Sandbox helpers: public tests, package snapshots, git state
# ---------------------------------------------------------------------------

PYTEST_CMD = ("PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null "
              "-q /testbed/acceptance_public.py --junitxml=/tmp/grade.xml")


def parse_junit(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    cases = []
    for n in root.iter("testcase"):
        failed = any(n.find(k) is not None for k in ("failure", "error", "skipped"))
        cases.append({"name": n.attrib.get("name"), "file": n.attrib.get("classname"), "passed": not failed,
                      "failures": [{"kind": c.tag, "message": c.attrib.get("message"), "text": c.text}
                                   for c in n if c.tag in ("failure", "error", "skipped")]})
    return cases


def run_public_tests(sandbox):
    result = sandbox.execute(PYTEST_CMD, 180)
    xml = sandbox.execute("cat /tmp/grade.xml")["stdout"]
    cases = parse_junit(xml)
    return {"passed": result["exit_code"] == 0 and bool(cases) and all(c["passed"] for c in cases),
            "test_count": len(cases), "cases": cases,
            "output": result["stdout"] + result["stderr"]}


def git_clean(sandbox):
    check = sandbox.execute("git status --porcelain", 30)
    return check["exit_code"] == 0 and check["stdout"].strip() == ""


def snapshot_package(sandbox, package_dir):
    """Tar only the package .py files for grading — solver tests/config/hooks
    never cross into grading (mirrors ProjectSandbox.snapshot)."""
    command = ("import io,tarfile,pathlib,sys; b=io.BytesIO(); t=tarfile.open(fileobj=b,mode='w'); "
               f"files=sorted(pathlib.Path({package_dir!r}).rglob('*.py')); "
               "assert files and all(not p.is_symlink() for p in files); "
               "[t.add(p,arcname=str(p)) for p in files]; t.close(); sys.stdout.buffer.write(b.getvalue())")
    out = subprocess.run(["docker", "exec", sandbox.name, "python", "-c", command],
                         capture_output=True, timeout=60)
    if out.returncode:
        raise RuntimeError("package snapshot failed: " + out.stderr.decode(errors="replace")[:500])
    return out.stdout


# ---------------------------------------------------------------------------
# Attempt drivers
# ---------------------------------------------------------------------------

def _new_agent(provider, deadline):
    import os
    import shutil
    import tempfile
    from minisweagent.agents.default import DefaultAgent
    global_config = Path(tempfile.mkdtemp(prefix="mini-clean-config-"))
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_config)
    os.environ["MSWEA_SILENT_STARTUP"] = "1"
    try:
        agent = DefaultAgent(MatchedModel(provider, deadline), None,
                             system_template="", instance_template="", cost_limit=0)
    finally:
        shutil.rmtree(global_config, ignore_errors=True)
    return agent


def run_diagnostic(root, task, provider, sandbox, store, identity, cfg):
    project, variant, seed = pair_of(task["instance_id"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    agent = _new_agent(provider, deadline)
    agent.env = MiniEnvironment(sandbox, deadline, store, identity)
    model = agent.model

    public = run_public_tests(sandbox)
    store.append("public_feedback", {**identity, "stage": "diagnostic", "timestamp": utc(),
                                     "passed": public["passed"], "test_count": public["test_count"],
                                     "output_tail": public["output"][-4000:]})
    instruction = ("Read-only review of the implementation and public test feedback. It may be correct or contain defects. "
                   "Do not edit source. Inspect relevant code/tests, then return grounded requirement claims, explicit "
                   "uncertainty and concrete suspected defects if any. Do not invent observations.\nPublic feedback:\n"
                   + public["output"][-10000:])
    summary = run_matched_phase(agent, model, store, identity, cfg, "diagnose", instruction,
                                spec_text(project), DIAGNOSTIC_CALLS, deadline, claims=True)
    diagnostic_changed = not git_clean(sandbox)
    claims, evaluation, assessment_seconds = None, None, 0
    if summary["done"] and not diagnostic_changed:
        claims = grounded_claims(summary["done"]["claims"], store, identity["attempt_id"])
        begin = time.monotonic()
        evaluation = assess(root, claims, "implement", store)
        assessment_seconds = time.monotonic() - begin
    event = {**identity, "project": project, "variant": variant, "seed": seed,
             "summary": summary, "diagnostic_changed_source": diagnostic_changed,
             "claims": claims, "evaluation": evaluation,
             "assessment_seconds": assessment_seconds, "timestamp": utc()}
    store.append("diagnostics", event)
    return {"diagnostic_valid": claims is not None, "diagnostic_changed_source": diagnostic_changed,
            "tool_calls": agent.env.tool_calls,
            "package_snapshot": store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))}


def _diagnostic_for(store, manifest, task):
    pair = task["instance_id"]
    diag_id = next((e["attempt_id"] for e in manifest["schedule"]
                    if e["task_id"] == pair and e["arm"] == "diagnose"), None)
    if diag_id is None:
        raise RuntimeError("no diagnostic attempt scheduled for " + pair)
    for event in store.events("diagnostics"):
        if event["attempt_id"] == diag_id:
            return event
    raise RuntimeError("diagnostic evidence not recorded for " + diag_id)


def run_repair(root, task, arm, provider, sandbox, store, identity, cfg, manifest):
    project, variant, seed = pair_of(task["instance_id"])
    deadline = time.monotonic() + cfg["timeout_seconds"]
    agent = _new_agent(provider, deadline)
    agent.env = MiniEnvironment(sandbox, deadline, store, identity)
    model = agent.model

    diag = _diagnostic_for(store, manifest, task)
    public = run_public_tests(sandbox)
    spec = spec_text(project)
    guided = arm == "repair_guided"
    evaluation = diag.get("evaluation")
    assessment_note = (json.dumps(compact_assessment(evaluation))
                       if evaluation else "{'error': 'Shared diagnostic incomplete; no valid assessment'}")
    rounds = []
    current_output = public["output"]
    for iteration in (1, 2):
        instruction = ("Review and repair if necessary using requirements, source and public feedback. "
                       "This may be a clean negative control: do not change correct code without a concrete reason. "
                       "Preserve existing APIs and tests.\nShared diagnostic (assertions are not proof):\n"
                       + json.dumps(diag["summary"].get("done")) + "\nPublic feedback:\n" + current_output[-10000:])
        if guided:
            instruction += ("\nActual AEE/Evaluator findings (not hidden test results):\n" + assessment_note)
        phase = run_matched_phase(agent, model, store, identity, cfg, f"repair_round{iteration}",
                                  instruction, spec, CALLS_PER_ROUND, deadline, claims=False)
        snap = store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))
        current = run_public_tests(sandbox)
        current_output = current["output"]
        rounds.append({"round": iteration, "phase": phase, "public": current,
                       "snapshot": snap, "source_changed": not git_clean(sandbox)})
        store.append("repair_rounds", {**identity, "round": iteration, "timestamp": utc(),
                                       "public_passed": current["passed"], "snapshot": snap})
    final_snapshot = store.artifact(snapshot_package(sandbox, PROJECTS[project]["package"]))
    patch = sandbox.execute("git add -N . && git diff --binary HEAD", 60)
    return {"patch": store.artifact(patch["stdout"].encode()),
            "package_snapshot": final_snapshot,
            "diagnostic_valid": diag["summary"].get("done") is not None and not diag["diagnostic_changed_source"],
            "guided_with_assessment": guided and evaluation is not None,
            "repair_rounds": rounds, "tool_calls": agent.env.tool_calls}


def execute_matched_attempt(root, task, arm, provider, sandbox, store, identity, cfg, manifest):
    if arm == "diagnose":
        return run_diagnostic(root, task, provider, sandbox, store, identity, cfg)
    if arm in ("repair_ordinary", "repair_guided"):
        return run_repair(root, task, arm, provider, sandbox, store, identity, cfg, manifest)
    raise ValueError("unknown matched-repair arm: " + arm)


# ---------------------------------------------------------------------------
# Fixture Docker images (offline; no model calls)
# ---------------------------------------------------------------------------

REGISTRY = "localhost:5000"
IMAGE_PREFIX = "mr-fixture"


def image_name(project, variant):
    return f"{REGISTRY}/{IMAGE_PREFIX}-{project}-{variant}"


def _copy_package_into(context, project):
    meta = PROJECTS[project]
    upstream = Path(meta["upstream"])
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if actual != meta["revision"]:
        raise ValueError(f"upstream {project} not at pinned revision {meta['revision']}: {actual}")
    if subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip():
        raise ValueError(f"upstream {project} checkout is dirty")
    package_src = upstream / meta["package"]
    package_dst = context / meta["package"]
    package_dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(package_src, package_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    return meta


def build_fixture_image(project, variant, push=True):
    """Build the fixture image: upstream package + synthetic variant module +
    public acceptance tests, committed as a clean git repo at /testbed.
    Returns (pinned_image_ref, base_commit)."""
    meta = PROJECTS[project]
    with tempfile.TemporaryDirectory(prefix="mr-fixture-") as tmp:
        context = Path(tmp)
        _copy_package_into(context, project)
        (context / meta["module"]).write_bytes(variant_source(project, variant))
        (context / "acceptance_public.py").write_bytes(tests_for(project, 3, True))
        (context / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            "RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git "
            "&& rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pytest\n"
            "WORKDIR /testbed\n"
            "COPY . /testbed/\n"
            "RUN git init -q && git add -A && "
            "git -c user.name=Benchmark -c user.email=benchmark@example.invalid commit -qm fixture\n")
        tag = image_name(project, variant) + ":build"
        subprocess.run(["docker", "build", "-q", "-t", tag, str(context)],
                       check=True, capture_output=True, timeout=600)
        base_commit = subprocess.check_output(
            ["docker", "run", "--rm", tag, "git", "rev-parse", "HEAD"], text=True, timeout=60).strip()
        if push:
            subprocess.run(["docker", "tag", tag, image_name(project, variant) + ":smoke"],
                           check=True, capture_output=True, timeout=60)
            subprocess.run(["docker", "push", image_name(project, variant) + ":smoke"],
                           check=True, capture_output=True, timeout=600)
            digests = json.loads(subprocess.check_output(
                ["docker", "inspect", image_name(project, variant) + ":smoke"], timeout=60))
            repo_digests = digests[0].get("RepoDigests") or []
            pinned = next((d for d in repo_digests if d.startswith(image_name(project, variant) + "@sha256:")), None)
            if pinned is None:
                raise RuntimeError("no registry digest after push for " + image_name(project, variant))
            return pinned, base_commit
        return tag, base_commit


def ensure_registry():
    running = subprocess.run(["docker", "inspect", "mr-registry"], capture_output=True)
    if running.returncode == 0:
        return
    subprocess.run(["docker", "run", "-d", "--restart=always", "--name", "mr-registry",
                    "-p", "5000:5000", "registry:2"], check=True, capture_output=True, timeout=300)
    for _ in range(30):
        time.sleep(2)
        probe = subprocess.run(["docker", "exec", "mr-registry", "true"], capture_output=True)
        if probe.returncode == 0:
            return
    raise RuntimeError("local registry did not start")


# ---------------------------------------------------------------------------
# Hidden grading (offline; runs in clean fixture containers)
# ---------------------------------------------------------------------------

def grade_snapshot(pinned_image, snapshot_bytes, project, expected_test_count=None):
    """Apply a package snapshot to a pristine fixture container and run the
    hidden acceptance tests. Hidden tests never enter solver images."""
    name = "mr-grade-" + sha(snapshot_bytes)[:12]
    hidden = tests_for(project, 3, False)
    with tempfile.TemporaryDirectory(prefix="mr-grade-") as tmp:
        snap_path = Path(tmp) / "snapshot.tar"
        snap_path.write_bytes(snapshot_bytes)
        hidden_path = Path(tmp) / "test_acceptance.py"
        hidden_path.write_bytes(hidden)
        try:
            subprocess.run(docker_args(pinned_image, name), check=True, capture_output=True, timeout=120)
            subprocess.run(["docker", "cp", str(snap_path), name + ":/tmp/snapshot.tar"],
                           check=True, capture_output=True, timeout=60)
            subprocess.run(["docker", "cp", str(hidden_path), name + ":/grade/test_acceptance.py"],
                           check=True, capture_output=True, timeout=60)
            setup = subprocess.run(
                ["docker", "exec", name, "bash", "-lc",
                 "mkdir -p /grade && tar -xf /tmp/snapshot.tar -C /testbed && "
                 "PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null "
                 "-q /grade/test_acceptance.py --junitxml=/tmp/grade.xml; echo EXIT=$?"],
                capture_output=True, timeout=300)
            xml = subprocess.run(["docker", "exec", name, "cat", "/tmp/grade.xml"],
                                 capture_output=True, timeout=30).stdout.decode(errors="replace")
            cases = parse_junit(xml)
            passed = ("EXIT=0" in setup.stdout.decode(errors="replace") and bool(cases)
                      and all(c["passed"] for c in cases)
                      and (expected_test_count is None or len(cases) == expected_test_count))
            failed = [c["name"] for c in cases if not c["passed"]]
            return {"passed": passed, "test_count": len(cases), "expected": expected_test_count,
                    "failed_cases": failed, "cases": cases,
                    "output": setup.stdout.decode(errors="replace")[-4000:] + setup.stderr.decode(errors="replace")[-2000:]}
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


def calibrate_fixtures(out, pairs):
    """Offline fixture calibration: seeded variants must fail hidden grading,
    clean controls must pass. Mirrors scripts/matched_repair.py calibration."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for project, variant in pairs:
        pinned, base_commit = build_fixture_image(project, variant)
        name = "mr-calib-" + sha(f"{project}-{variant}".encode())[:12]
        try:
            subprocess.run(docker_args(pinned, name), check=True, capture_output=True, timeout=120)
            snap = snapshot_package(_NamedSandbox(name), PROJECTS[project]["package"])
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        result = grade_snapshot(pinned, snap, project)
        ok = result["passed"] == (variant == "clean")
        rows.append({"project": project, "variant": variant, "image": pinned, "base_commit": base_commit,
                     "grade": result, "calibrated": ok,
                     "seeded_requirements": VARIANTS[project][variant][2]})
        if not ok:
            raise RuntimeError(f"fixture calibration FAILED: {project}/{variant}: {result}")
        print(f"CALIBRATION {project}/{variant}: passed={result['passed']} tests={result['test_count']}", flush=True)
    write_json(out / "calibration.json", {"passed": True, "fixtures": rows, "timestamp": utc()}, exclusive=True)
    return rows


class _NamedSandbox:
    """Minimal adapter so snapshot_package can target an already-running container."""
    def __init__(self, name):
        self.name = name


# ---------------------------------------------------------------------------
# Solver image audit (offline): no hidden grader material in solver images
# ---------------------------------------------------------------------------

def audit_solver_image(pinned_image, project):
    """Verify the solver image contains no hidden tests or grader material:
    only the package, the synthetic module, acceptance_public.py, and git metadata."""
    name = "mr-audit-" + sha(pinned_image.encode())[:12]
    try:
        subprocess.run(docker_args(pinned_image, name), check=True, capture_output=True, timeout=120)
        listing = subprocess.run(["docker", "exec", name, "bash", "-lc",
                                  "find /testbed -type f | sort"],
                                 capture_output=True, timeout=60).stdout.decode()
        files = [l for l in listing.splitlines() if l]
        hidden_markers = [f for f in files
                          if "test_acceptance" in f and "acceptance_public" not in f
                          or "hidden" in f.lower() or "/grade/" in f]
        git_check = subprocess.run(["docker", "exec", name, "bash", "-lc",
                                    "git -C /testbed rev-parse HEAD && git -C /testbed status --porcelain"],
                                   capture_output=True, timeout=60).stdout.decode().strip().splitlines()
        base_commit = git_check[0].strip() if git_check else None
        clean = len(git_check) == 1
        return {"image": pinned_image, "files": files, "hidden_markers": hidden_markers,
                "base_commit": base_commit, "git_clean": clean,
                "audit_pass": not hidden_markers and clean and base_commit is not None}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


# ---------------------------------------------------------------------------
# Reservation-bound verification (operator gate before freezing)
# ---------------------------------------------------------------------------

# GPT-6 Astra documented limits (developers.openai.com/api/docs/models, checked 2026-09-20).
ASTRA_MAX_INPUT_TOKENS = 922000
ASTRA_MAX_OUTPUT_TOKENS = 128000


def verify_reservation_bounds(cfg):
    """Verify the model-specific reservation bound the provider enforces.
    Returns the verified numbers; raises on any inconsistency.

    The reservation uses the conservative maximum of the short and long
    price tiers, exactly as provider.query() reserves via request_prices().
    The long-context tier (272K+ input tokens) is provably unreachable
    because max_input_tokens (32,768) is a hard ceiling well below the
    threshold, so the short-tier prices would suffice — but the bound is
    checked against the same conservative reservation the budget enforces,
    never a weaker one."""
    if cfg["model"] != "gpt-6-astra":
        raise ValueError("reservation bounds verified only for gpt-6-astra")
    if cfg["max_input_tokens"] > ASTRA_MAX_INPUT_TOKENS:
        raise ValueError("max_input_tokens exceeds Astra documented max input")
    if cfg["max_output_tokens"] > ASTRA_MAX_OUTPUT_TOKENS:
        raise ValueError("max_output_tokens exceeds Astra documented max output")
    if cfg["max_input_tokens"] >= cfg["long_context_threshold"]:
        raise ValueError("max_input_tokens reaches long-context tier; "
                         "long-tier prices would require official verification")
    # Conservative maximum rates, exactly as the provider reserves
    # (request_prices with no usage returns the max of short/long tiers).
    tier = request_prices(cfg)
    per_call = ((Decimal(cfg["max_input_tokens"]) * Decimal(str(tier["input"]))
                 + Decimal(cfg["max_output_tokens"]) * Decimal(str(tier["output"]))) / Decimal(1_000_000))
    worst = {
        "per_call_usd": str(per_call),
        "diagnostic_attempt_usd": str(per_call * DIAGNOSTIC_CALLS),
        "repair_attempt_usd": str(per_call * REPAIR_ROUNDS * CALLS_PER_ROUND),
    }
    if Decimal(worst["repair_attempt_usd"]) > Decimal(str(cfg["attempt_cap_usd"])):
        raise ValueError("worst-case repair reservation exceeds attempt cap")
    if Decimal(worst["diagnostic_attempt_usd"]) > Decimal(str(cfg["attempt_cap_usd"])):
        raise ValueError("worst-case diagnostic reservation exceeds attempt cap")
    return worst


# ---------------------------------------------------------------------------
# Smoke freeze builder (freeze v4)
# ---------------------------------------------------------------------------

SMOKE_PAIR = ("tinydb", "bool_id", 20260918)

BUDGET_AUTHORIZATION = (
    "On 2026-09-20 Tristen authorized a 3-attempt development smoke with attempt_cap_usd=25 and global_cap_usd=100."
)

PRICE_SOURCE = (
    "https://openai.com/fr-CA/api/pricing/ and https://developers.openai.com/api/docs/models "
    "(checked 2026-09-20): GPT-6 Astra list $10/1M input, $1/1M cached input, $50/1M output; "
    "requests above 272,000 input tokens bill $20/1M input, $2/1M cached input, $75/1M output "
    "for the full request. Model id gpt-6-astra is the only published snapshot/alias. "
    "Cross-checked 2026-09-20 against multiple outlets citing OpenAI's pricing page "
    "(cloudzero.com, laozhang.ai, devtoollab.com, kingy.ai): $10/$1/$50 standard; "
    "$20/$2/$75 above 272K input tokens for the entire request; API model string gpt-6-astra; "
    "~1.1M token context window."
)


def smoke_config():
    return {
        "schema_version": 1,
        "purpose": "development_smoke",
        "seed": 20260920,
        "repeats": 1,
        "runner": "mini-swe-agent-2.4.6-instrumented",
        "model": "gpt-6-astra",
        "reasoning_effort": "medium",
        "temperature": None,
        "max_input_tokens": 32768,
        "max_output_tokens": 4096,
        "token_cap": 1000000,
        "global_cap_usd": 100,
        "attempt_cap_usd": 25,
        "timeout_seconds": 1800,
        "max_calls": 24,
        "max_recovery_rounds": 2,
        "price_snapshot_id": "openai-list-2026-09-20",
        "price_source": PRICE_SOURCE,
        "prices": {"input": 10.0, "cached_input": 1.0, "output": 50.0},
        "long_context_prices": {"input": 20.0, "cached_input": 2.0, "output": 75.0},
        "long_context_threshold": 272000,
        "currency": "USD",
        "service_tier": "default",
        "budget_authorization": BUDGET_AUTHORIZATION,
        "reservation_bound_verified": False,
        "grader_smoke_verified": False,
        "real_smoke_verified": False,
        "solver_image_audit_verified": False,
    }


def run_grade_smoke(calibration):
    """Independent grader smoke (gate): a seeded-bug snapshot must fail hidden
    grading and a clean snapshot must pass — exercises the full
    snapshot -> grade path on both outcomes. Raises on failure."""
    results = {}
    for project in ("tinydb", "cachetools"):
        bad = next(f for f in calibration["fixtures"] if f["project"] == project and f["variant"] != "clean")
        good = next(f for f in calibration["fixtures"] if f["project"] == project and f["variant"] == "clean")
        project_results = {}
        for fixture, key in ((bad, "bad"), (good, "good")):
            name = f"mr-gsmoke-{project}-{key}"
            try:
                subprocess.run(docker_args(fixture["image"], name), check=True,
                               capture_output=True, timeout=120)
                snap = snapshot_package(_NamedSandbox(name), PROJECTS[project]["package"])
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            project_results[key] = grade_snapshot(fixture["image"], snap, project)
        print(f"GRADER SMOKE {project}: bad_passed={project_results['bad']['passed']} "
              f"good_passed={project_results['good']['passed']} "
              f"tests={project_results['good']['test_count']}", flush=True)
        if project_results["bad"]["passed"] or not project_results["good"]["passed"]:
            raise ValueError(f"grader smoke failed for {project}")
        results[project] = {k: {"passed": v["passed"], "test_count": v["test_count"],
                                "failed_cases": v["failed_cases"]}
                            for k, v in project_results.items()}
    print("GRADER SMOKE PASS", flush=True)
    return results


def build_smoke_freeze(output, calibration):
    """Build freeze v4 for the 3-attempt development smoke. `calibration` is the
    fixture calibration record (image refs + base commits). Runs every offline
    gate itself — reservation bounds, solver image audit, grader smoke — and
    sets the verification flags True only when each gate genuinely passes.
    Fails closed otherwise."""
    project, variant, seed = SMOKE_PAIR
    pair_id = f"mr-{project}-{variant}-{seed}"
    fixture = next(f for f in calibration["fixtures"]
                   if (f["project"], f["variant"]) == (project, variant))
    cfg = smoke_config()
    reservation = verify_reservation_bounds(cfg)
    audit = audit_solver_image(fixture["image"], project)
    if not audit["audit_pass"]:
        raise ValueError("solver image audit failed: " + json.dumps(audit["hidden_markers"]))
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True
    problem_statement = (
        f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
        f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
        "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
        "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
        "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
        "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
        "Hidden acceptance tests grade the final package snapshots after all runs; hidden outcomes are never "
        "fed back to any attempt.")
    tasks = {"schema_version": 1, "seed": cfg["seed"],
             "selection": "matched-repair development smoke: single excluded pair",
             "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                  if (p, v, s) != SMOKE_PAIR),
             "tasks": [{"instance_id": pair_id, "repo": "matched-repair-fixture",
                        "base_commit": fixture["base_commit"], "problem_statement": problem_statement,
                        "image": fixture["image"], "language": "python"}]}
    arms = ["repair_ordinary", "repair_guided"]
    random.Random(seed + len(variant)).shuffle(arms)
    ordered_arms = ["diagnose"] + arms
    schedule = [dict(task_id=pair_id, arm=arm, repeat=1, attempt_id=f"{pair_id}--{arm}")
                for arm in ordered_arms]
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": tasks,
        "schedule": schedule,
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden outcomes never feed back. The smoke pair "
                    "is excluded from any future scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audit": audit,
        "grade_smoke": grade_smoke,
        "fixture": {"project": project, "variant": variant, "seed": seed,
                    "image": fixture["image"], "base_commit": fixture["base_commit"],
                    "hidden_test_count": fixture["grade"]["test_count"]},
        "notes": ("Freeze v4: development smoke only. Real smoke is an integration and spend-measurement check, "
                  "not a performance comparison. Historical freezes v2/v3 and all prior evidence are untouched."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v4-smoke.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Matched-repair cloud port")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-images").add_argument("--no-push", action="store_true")
    p = sub.add_parser("calibrate"); p.add_argument("out", type=Path)
    p = sub.add_parser("audit"); p.add_argument("image"); p.add_argument("project")
    p = sub.add_parser("freeze"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("grade-smoke"); p.add_argument("--calibration", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build-images":
        ensure_registry()
        for project, variants in VARIANTS.items():
            for variant in variants:
                pinned, commit = build_fixture_image(project, variant, push=not args.no_push)
                print(f"BUILT {project}/{variant}: {pinned} commit={commit[:12]}", flush=True)
    elif args.command == "calibrate":
        ensure_registry()
        pairs = [(p, v) for p in VARIANTS for v in VARIANTS[p]]
        calibrate_fixtures(args.out, pairs)
    elif args.command == "audit":
        print(json.dumps(audit_solver_image(args.image, args.project), indent=2))
    elif args.command == "freeze":
        manifest = build_smoke_freeze(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
    elif args.command == "grade-smoke":
        # Independent grader smoke (gate): a seeded-bug snapshot must fail hidden
        # grading and a clean snapshot must pass — exercises the full
        # snapshot -> grade path on both outcomes.
        run_grade_smoke(read_json(args.calibration))


if __name__ == "__main__":
    main()

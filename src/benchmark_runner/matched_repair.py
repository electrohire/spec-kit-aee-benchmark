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
#
# Hard-pair track (freeze v7): `before` may also be a list of
# (before, after) edit pairs (with `after=None`) for multi-edit variants
# such as coupled defects; variant_source applies them in order.
VARIANTS = {
    "tinydb": {
        "bool_id": ("type(ident) is not int", "not isinstance(ident, int)", ["R04"]),
        "token_alias": ("self.tokens[token] = (deepcopy(operations), deepcopy(inserted))",
                        "self.tokens[token] = (deepcopy(operations), inserted)", ["R08"]),
        "partial_commit": ("docs[next_id] = deepcopy(op['document'])",
                           "docs[next_id] = deepcopy(op['document']); self.db.storage.write({'_default':docs})",
                           ["R02", "R05"]),
        # H2: eager idempotency-key reservation; failed batches consume the
        # token, violating R07 ("Failed batches do not consume a token").
        "token_reserve": ("        storage, next_id, inserted = self._simulate(operations)\n",
                          "        if token is not None:\n"
                          "            self.tokens[token] = (deepcopy(operations), [])\n"
                          "        storage, next_id, inserted = self._simulate(operations)\n",
                          ["R07"]),
        # H4: _simulate aliases live storage; preview() (R05 side-effect-free)
        # poisons the database, symptom surfaces two hops away at db.insert.
        "storage_alias": ("        storage = deepcopy(self.db.storage.read() or {})\n",
                          "        storage = self.db.storage.read() or {}\n",
                          ["R05"]),
        "clean": (None, None, []),
    },
    "cachetools": {
        "expiry_boundary": ("now >= entry[2]", "now > entry[2]", ["R07", "R08"]),
        "value_alias": ("return deepcopy(self._cache[key][0])", "return self._cache[key][0]", ["R01", "R06"]),
        "boolean_ttl": ("isinstance(ttl, bool) or not isinstance(ttl, (int,float))",
                        "not isinstance(ttl, (int,float))", ["R07"]),
        # H1: deleting the empty-tags guard makes invalidate_many([], 'all')
        # remove everything. The stage-2 spec's conflicting evidence packet
        # (old note: "empty all-tags matches every key", superseded by R04)
        # asserts exactly this buggy behavior.
        "empty_tags": ("        if not tags:\n            return 0\n",
                       "",
                       ["R04"]),
        # H3: overwrite without ttl retains the prior expiry, violating R08
        # ("Overwriting an entry replaces its prior expiry").
        "expiry_retain": ("        expiry = None if ttl is None else self._timer() + ttl\n",
                          "        if ttl is None:\n"
                          "            try:\n"
                          "                expiry = Cache.__getitem__(self._cache, key)[2]\n"
                          "            except KeyError:\n"
                          "                expiry = None\n"
                          "        else:\n"
                          "            expiry = self._timer() + ttl\n",
                          ["R08"]),
        # H6: coupled defects; diagnosis must be complete (fixing only the
        # obvious boundary defect still fails hidden acceptance).
        "coupled": ([("now >= entry[2]", "now > entry[2]"),
                     ("        if not tags:\n            return 0\n", "")],
                    None,
                    ["R07", "R08", "R04"]),
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
    # Multi-edit variants pass a list of (before, after) pairs as `before`
    # with `after=None`; edits apply in order, each anchor asserted unique.
    edits = before if isinstance(before, list) else [(before, after)]
    for b, a in edits:
        if b:
            assert text.count(b) == 1, f"variant anchor not unique: {project}/{variant}"
            text = text.replace(b, a)
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

# PYTHONDONTWRITEBYTECODE=1 keeps run_public_tests from dirtying the clean fixture
# worktree: without it, pytest writes untracked __pycache__/ dirs under /testbed and
# git_clean() (git status --porcelain) reports the tree dirty before the agent acts,
# which silently discards all diagnostic claims. Real agent edits are still detected.
PYTEST_CMD = ("PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -c /dev/null "
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
            # Surface the daemon's stderr on failure: a bare CalledProcessError
            # hides the real cause (refused/denied/500) behind exit status 1.
            pr = subprocess.run(["docker", "push", image_name(project, variant) + ":smoke"],
                                capture_output=True, text=True, timeout=600)
            if pr.returncode != 0:
                detail = (pr.stderr or pr.stdout or "").strip()
                raise RuntimeError(
                    f"docker push failed for {image_name(project, variant)}:smoke "
                    f"(exit {pr.returncode}):\n{detail}")
            digests = json.loads(subprocess.check_output(
                ["docker", "inspect", image_name(project, variant) + ":smoke"], timeout=60))
            repo_digests = digests[0].get("RepoDigests") or []
            pinned = next((d for d in repo_digests if d.startswith(image_name(project, variant) + "@sha256:")), None)
            if pinned is None:
                raise RuntimeError("no registry digest after push for " + image_name(project, variant))
            return pinned, base_commit
        return tag, base_commit


def ensure_registry():
    probe = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "mr-registry"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        if probe.stdout.strip() == "true":
            return
        # Container exists but is stopped (e.g. after a host reboot): start it
        # rather than failing on the name conflict a fresh `docker run` would hit.
        subprocess.run(["docker", "start", "mr-registry"],
                       check=True, capture_output=True, timeout=60)
    else:
        subprocess.run(["docker", "run", "-d", "--restart=always", "--name", "mr-registry",
                        "-p", "5000:5000", "registry:2"], check=True, capture_output=True, timeout=300)
    # Wait for the registry HTTP API itself, not just the container: the
    # registry server takes a few seconds to listen after the container
    # reports running, and pushing before that fails with connection refused.
    import urllib.request
    for _ in range(60):
        time.sleep(2)
        try:
            with urllib.request.urlopen("http://localhost:5000/v2/", timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
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
            # Fixture images do not ship /grade; this Docker's `cp` will not
            # create missing parent dirs, so create it before copying in.
            subprocess.run(["docker", "exec", name, "mkdir", "-p", "/grade"],
                           check=True, capture_output=True, timeout=60)
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
# Post-run hidden acceptance grading (offline; Docker only, no model calls)
# ---------------------------------------------------------------------------

def grade_run(run_dir, grade_fn=None):
    """Grade a completed scored run's repair snapshots with the hidden
    acceptance tests. Runs after ALL attempts are done: hidden outcomes are
    recorded in the `hidden_grades` event stream and never fed back to any
    attempt. Offline (Docker only, no model calls) and idempotent: attempts
    already graded are skipped. Fails closed on missing snapshots or hash
    mismatches."""
    grade_fn = grade_fn or grade_snapshot
    run_dir = Path(run_dir)
    manifest = read_json(run_dir / "freeze.json")
    tasks = {t["instance_id"]: t for t in manifest["tasks"]["tasks"]}
    store = Store(run_dir)
    graded = {e["attempt_id"] for e in store.events("hidden_grades")}
    latest = {}
    for e in store.events("attempts"):
        latest[e["attempt_id"]] = e
    results = []
    for attempt_id in sorted(latest):
        attempt = latest[attempt_id]
        if attempt_id in graded:
            continue
        if attempt.get("arm") not in ("repair_ordinary", "repair_guided"):
            continue
        identity = {"attempt_id": attempt_id, "task_id": attempt["task_id"], "arm": attempt["arm"],
                    "experiment_id": manifest["freeze_id"], "run_id": manifest["freeze_id"][:16],
                    "purpose": manifest["config"]["purpose"]}
        if attempt.get("status") != "completed":
            store.append("hidden_grades", {**identity, "graded": False,
                                           "reason": "attempt status %s; no final snapshot to grade"
                                                     % attempt.get("status"),
                                           "timestamp": utc()})
            results.append((attempt_id, "skipped"))
            print(f"GRADE {attempt_id}: skipped ({attempt.get('status')})", flush=True)
            continue
        snap_ref = attempt.get("package_snapshot")
        if not snap_ref:
            raise ValueError(f"completed repair attempt {attempt_id} has no package_snapshot")
        snap_path = store.root / snap_ref["path"]
        data = snap_path.read_bytes()
        if sha(data) != snap_ref["sha256"]:
            raise ValueError(f"package snapshot changed for {attempt_id}")
        project, _, _ = pair_of(attempt["task_id"])
        task = tasks[attempt["task_id"]]
        grade = grade_fn(task["image"], data, project, task.get("hidden_test_count"))
        store.append("hidden_grades", {**identity, "graded": True,
                                       "hidden_passed": grade["passed"],
                                       "test_count": grade["test_count"],
                                       "expected_test_count": grade["expected"],
                                       "failed_cases": grade["failed_cases"],
                                       "grade_artifact": store.artifact(canonical(grade)),
                                       "timestamp": utc()})
        results.append((attempt_id, grade["passed"]))
        print(f"GRADE {attempt_id}: hidden_passed={grade['passed']} "
              f"tests={grade['test_count']} failed={grade['failed_cases']}", flush=True)
    return results


def graded_comparison(run_dir):
    """Per-pair ordinary-vs-guided hidden outcomes from the hidden_grades
    stream. Only graded attempts appear; pairs with a missing arm are honest
    about it (no imputation). hidden_pass_rate is the primary comparison
    metric for hard pairs where partial passes are expected."""
    grades = {}
    for e in Store(Path(run_dir)).events("hidden_grades"):
        grades[e["attempt_id"]] = e
    pairs = {}
    for g in grades.values():
        row = pairs.setdefault(g["task_id"], {})
        if g.get("graded"):
            failed = g["failed_cases"] or []
            total = g["test_count"]
            rate = (total - len(failed)) / total if total else None
            row[g["arm"]] = {"hidden_passed": g["hidden_passed"],
                             "test_count": total,
                             "failed_cases": failed,
                             "hidden_pass_rate": rate}
        else:
            row[g["arm"]] = {"hidden_passed": None, "reason": g.get("reason")}
    return pairs


# ---------------------------------------------------------------------------
# Smoke freeze builder (freeze v4)
# ---------------------------------------------------------------------------

SMOKE_PAIR = ("tinydb", "bool_id", 20260918)

# First scored pair: the smoke pair above is excluded from every scored freeze,
# so the pilot starts on the next tinydb variant with the same scored seed.
SCORED_PAIR = ("tinydb", "token_alias", 20260918)

BUDGET_AUTHORIZATION = (
    "On 2026-09-20 Tristen authorized a 3-attempt development smoke with attempt_cap_usd=25 and global_cap_usd=100."
)

SCORED_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized a fresh 3-attempt scored matched-repair comparison "
    "(freeze v5, pair tinydb/token_alias, seed 20260918, model gpt-6-astra) with attempt_cap_usd=25 "
    "and global_cap_usd=100. Prior measured spend: $1.4831 (smoke v4, 2026-09-21). The 2026-09-20 "
    "failed run's unmeasured charge was discounted by Tristen on 2026-09-21 as unverifiable."
)

REAL_SMOKE_EVIDENCE = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC: 3/3 attempts completed "
    "(diagnose $0.3728, repair_ordinary $0.4815, repair_guided $0.6287), 32 model calls, "
    "$1.4831 measured spend. Validated in production: provider telemetry-identity check "
    "before the HTTP request (fail fast before spending) and budget settlement in a finally "
    "block. real_smoke_verified=True is grounded on this completed smoke run."
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


def scored_config():
    """Frozen config for the first scored matched-repair comparison (freeze v5).

    Same model, caps, and token bounds as the smoke. real_smoke_verified=True is
    grounded on the completed freeze-v4 smoke (see REAL_SMOKE_EVIDENCE); the scored
    seed is 20260918 per the standing benchmark plan."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": 20260918,
        "budget_authorization": SCORED_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE,
    })
    return cfg


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
# Scored freeze builder (freeze v5)
# ---------------------------------------------------------------------------

def build_scored_freeze(output, calibration):
    """Build freeze v5: the first scored matched-repair comparison. Same three
    arms and the same offline gates as the smoke; runs scored (hidden grading
    after the run), so real_smoke_verified must be True — grounded on the
    completed freeze-v4 smoke (see REAL_SMOKE_EVIDENCE). The smoke pair
    (tinydb/bool_id) is excluded by construction. Fails closed otherwise."""
    project, variant, seed = SCORED_PAIR
    pair_id = f"mr-{project}-{variant}-{seed}"
    fixture = next(f for f in calibration["fixtures"]
                   if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config()
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
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    tasks = {"schema_version": 1, "seed": cfg["seed"],
             "selection": "matched-repair scored comparison: single pair (smoke pair excluded)",
             "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                  if (p, v, s) != SCORED_PAIR),
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
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audit": audit,
        "grade_smoke": grade_smoke,
        "fixture": {"project": project, "variant": variant, "seed": seed,
                    "image": fixture["image"], "base_commit": fixture["base_commit"],
                    "hidden_test_count": fixture["grade"]["test_count"]},
        "notes": ("Freeze v5: first scored matched-repair comparison. Scored seed 20260918, model gpt-6-astra. "
                  "Freeze v4 (development smoke) and all prior evidence are untouched; negative and partial "
                  "outcomes are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v5-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v6): full scored set with hidden grading
# ---------------------------------------------------------------------------

# Every variant at the scored seed except the smoke pair
# (tinydb/bool_id/20260918), which is excluded from every scored freeze.
# Clean variants are negative controls: the agent must not change correct
# code without a concrete reason; hidden grading expects them to pass.
#
# Pinned explicitly (not derived from VARIANTS): the v7 hard-pair variants
# added to VARIANTS must not leak into the frozen v6 set.
SCORED_SEED_V6 = 20260918
SCORED_PAIRS_V6 = (
    ("tinydb", "token_alias", SCORED_SEED_V6),
    ("tinydb", "partial_commit", SCORED_SEED_V6),
    ("tinydb", "clean", SCORED_SEED_V6),
    ("cachetools", "expiry_boundary", SCORED_SEED_V6),
    ("cachetools", "value_alias", SCORED_SEED_V6),
    ("cachetools", "boolean_ttl", SCORED_SEED_V6),
    ("cachetools", "clean", SCORED_SEED_V6),
)

SCORED_V6_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized a scored matched-repair campaign with attempt_cap_usd=25 and "
    "global_cap_usd=100 (freeze v5: 3 attempts on tinydb/token_alias, seed 20260918, model gpt-6-astra), "
    "and on 2026-09-21 further authorized rerunning the full scored set with hidden acceptance grading "
    "in the mix (freeze v6: all 7 scored pairs at seed 20260918, 21 attempts) under the same $25/attempt "
    "and $100 global caps. Prior measured spend: $1.4831 (smoke v4) + $1.5029 (scored v5) = $2.9860; "
    "$97.0140 of the global cap remains. Expected v6 spend ~$10.50 at v5's $1.50/pair rate. "
    "The 2026-09-20 failed run's unmeasured charge was discounted by Tristen on 2026-09-21 as unverifiable. "
    "Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V6 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured) and "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true). "
    "real_smoke_verified=True is grounded on both completed runs."
)


def scored_config_v6():
    """Frozen config for the full scored campaign (freeze v6).

    Same model, caps, and token bounds as v5. real_smoke_verified=True is
    grounded on the completed v4 smoke AND the completed v5 scored run
    (see REAL_SMOKE_EVIDENCE_V6)."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V6,
        "budget_authorization": SCORED_V6_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V6,
    })
    return cfg


def scored_v6_schedule():
    """Deterministic 21-attempt schedule for freeze v6: per pair, diagnose
    first, then the two repair arms in seeded-shuffled order. Pure function of
    SCORED_PAIRS_V6 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V6):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v6(output, calibration):
    """Build freeze v6: the full scored campaign with hidden acceptance
    grading in the mix. Seven pairs at the scored seed (smoke pair excluded),
    three arms each, 21 attempts. Same offline gates as v5 — reservation
    bounds, per-fixture solver image audit, grader smoke — plus
    real_smoke_verified grounded on the completed v4 and v5 runs. Fails
    closed otherwise."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V6:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v6()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
            "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
            "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
            "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
            "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
            "After all runs, the final package snapshots are graded with hidden acceptance tests; "
            "hidden outcomes are never fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V6:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": "matched-repair scored campaign: all pairs at the scored seed (smoke pair excluded)",
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V6)),
                  "tasks": tasks},
        "schedule": scored_v6_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V6],
        "notes": ("Freeze v6: full scored campaign (7 pairs x 3 arms = 21 attempts) with post-run hidden "
                  "acceptance grading of every completed repair snapshot. Reruns the v5 pair (tinydb/token_alias) "
                  "so grading is in the mix for the whole set. Freezes v4/v5 and all prior evidence untouched; "
                  "negative and partial outcomes are preserved in the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v6-scored.json", manifest, exclusive=True)
    return manifest


# ---------------------------------------------------------------------------
# Scored freeze builder (freeze v7): hard pairs designed to separate the arms
# ---------------------------------------------------------------------------

# After the v6 null result (all 14 repair snapshots 16/16 hidden, ordinary and
# guided identical), v7 keeps the tinydb/token_alias anchor and both clean
# negative controls, and adds five hard pairs. Every hard pair was verified
# offline 2026-09-21: all 4 public tests pass on the seeded defect, at least
# one hidden test fails, and the reference passes the full hidden set.
# v6-only single-defect variants (bool_id, partial_commit, value_alias,
# boolean_ttl, expiry_boundary) are excluded; the expiry_boundary defect
# returns inside the coupled pair.
SCORED_SEED_V7 = 20260918
SCORED_PAIRS_V7 = (
    ("tinydb", "token_alias", SCORED_SEED_V7),
    ("cachetools", "empty_tags", SCORED_SEED_V7),
    ("tinydb", "token_reserve", SCORED_SEED_V7),
    ("cachetools", "expiry_retain", SCORED_SEED_V7),
    ("tinydb", "storage_alias", SCORED_SEED_V7),
    ("cachetools", "coupled", SCORED_SEED_V7),
    ("tinydb", "clean", SCORED_SEED_V7),
    ("cachetools", "clean", SCORED_SEED_V7),
)

SCORED_V7_BUDGET_AUTHORIZATION = (
    "On 2026-09-21 Tristen authorized the freeze-v7 hard-pair scored campaign: "
    "24 attempts (8 pairs x diagnose/ordinary/guided) on gpt-6-astra with "
    "attempt_cap_usd=25 and global_cap_usd=100. Expected spend ~$14-19. "
    "Prior measured spend: $11.8730 against the $100 global cap ($88.1270 remaining). "
    "Spend settles to measured usage; unknown usage is never released."
)

REAL_SMOKE_EVIDENCE_V7 = (
    "Freeze v4 development smoke completed 2026-09-21 ~01:03 UTC (3/3 attempts, $1.4831 measured), "
    "freeze v5 scored comparison completed 2026-09-21 ~12:23 UTC (3/3 attempts on tinydb/token_alias, "
    "$1.5029 measured, diagnostic_valid=true, guided_with_assessment=true), and freeze v6 full scored "
    "campaign completed 2026-09-21 ~13:25 UTC (21/21 attempts, $8.8870 measured, hidden acceptance "
    "grading 14/14 PASS). real_smoke_verified=True is grounded on these completed runs: the paid model "
    "path is proven end to end."
)


def scored_config_v7():
    """Frozen config for the hard-pair scored campaign (freeze v7).

    Same model, caps, and token bounds as v6. real_smoke_verified=True is
    grounded on the completed v4/v5/v6 runs (see REAL_SMOKE_EVIDENCE_V7).
    Tristen authorized this campaign on 2026-09-21 (see
    SCORED_V7_BUDGET_AUTHORIZATION); the host RUN gate still takes his typed
    RUN as the fresh confirmation before any paid call."""
    cfg = smoke_config()
    cfg.update({
        "purpose": "scored_comparison",
        "seed": SCORED_SEED_V7,
        "budget_authorization": SCORED_V7_BUDGET_AUTHORIZATION,
        "real_smoke_verified": True,
        "real_smoke_evidence": REAL_SMOKE_EVIDENCE_V7,
    })
    return cfg


def scored_v7_schedule():
    """Deterministic 24-attempt schedule for freeze v7: per pair, diagnose
    first, then the two repair arms in seeded-shuffled order. Pure function of
    SCORED_PAIRS_V7 (no Docker, no model calls)."""
    schedule = []
    for i, (project, variant, seed) in enumerate(SCORED_PAIRS_V7):
        pair_id = f"mr-{project}-{variant}-{seed}"
        arms = ["repair_ordinary", "repair_guided"]
        random.Random(seed + len(variant) + i).shuffle(arms)
        for arm in ["diagnose"] + arms:
            schedule.append(dict(task_id=pair_id, arm=arm, repeat=1,
                                 attempt_id=f"{pair_id}--{arm}"))
    return schedule


def build_scored_freeze_v7(output, calibration):
    """Build freeze v7: the hard-pair scored campaign. Eight pairs at the
    scored seed (token_alias anchor, five hard pairs, both clean controls),
    three arms each, 24 attempts. Same offline gates as v6 — reservation
    bounds, per-fixture solver image audit, grader smoke. Fails closed
    otherwise. Offline only: no model calls, no spend."""
    fixtures = {}
    for project, variant, seed in SCORED_PAIRS_V7:
        fixtures[(project, variant)] = next(
            f for f in calibration["fixtures"]
            if (f["project"], f["variant"]) == (project, variant))
    cfg = scored_config_v7()
    reservation = verify_reservation_bounds(cfg)
    audits = {}
    for (project, variant), fixture in fixtures.items():
        audit = audit_solver_image(fixture["image"], project)
        if not audit["audit_pass"]:
            raise ValueError(f"solver image audit failed for {project}/{variant}: "
                             + json.dumps(audit["hidden_markers"]))
        audits[f"{project}/{variant}"] = audit
    grade_smoke = run_grade_smoke(calibration)
    cfg["reservation_bound_verified"] = True
    cfg["grader_smoke_verified"] = True
    cfg["solver_image_audit_verified"] = True

    def problem_statement(pair_id, project):
        return (
            f"Matched-repair pair {pair_id}: the /testbed repository may contain a seeded defect "
            f"in {PROJECTS[project]['module']} (or may be a clean negative control). "
            "Protocol: (1) a shared read-only diagnostic attempt reviews the implementation and public test "
            "feedback and returns grounded requirement claims with explicit uncertainty; (2) two repair attempts "
            "(ordinary and AEE-guided) start from the same pristine snapshot and each get two repair rounds. "
            "The guided arm additionally receives the actual AEE/Evaluator findings from the shared diagnostic. "
            "After all runs, the final package snapshots are graded with hidden acceptance tests; "
            "hidden outcomes are never fed back to any attempt.")

    tasks = []
    for project, variant, seed in SCORED_PAIRS_V7:
        pair_id = f"mr-{project}-{variant}-{seed}"
        fixture = fixtures[(project, variant)]
        tasks.append({"instance_id": pair_id, "repo": "matched-repair-fixture",
                      "base_commit": fixture["base_commit"],
                      "problem_statement": problem_statement(pair_id, project),
                      "image": fixture["image"], "language": "python",
                      "hidden_test_count": fixture["grade"]["test_count"]})
    smoke_pair_id = "mr-%s-%s-%s" % SMOKE_PAIR
    manifest = {
        "schema_version": 1,
        "files": {name: source_hash(ROOT / name) for name in frozen_paths(ROOT)},
        "config": cfg,
        "tasks": {"schema_version": 1, "seed": cfg["seed"],
                  "selection": ("matched-repair scored campaign: hard pairs at the scored seed "
                                "(token_alias anchor, five hard pairs, both clean controls)"),
                  "exclusions": sorted(f"mr-{p}-{v}-{s}" for p in VARIANTS for v in VARIANTS[p] for s in SEEDS
                                       if (p, v, s) not in set(SCORED_PAIRS_V7)),
                  "tasks": tasks},
        "schedule": scored_v7_schedule(),
        "pairing": ("Shared read-only diagnostic and raw claims, identical start/feedback/tools; only the guided "
                    "repair arm receives actual AEE findings. Repair instructions embed the recorded diagnostic "
                    "summary (frozen template + stored evidence); hidden grading of final snapshots happens after "
                    "all runs and is never fed back. The smoke pair "
                    f"({smoke_pair_id}) is excluded from every scored freeze."),
        "reservation_verification": reservation,
        "solver_image_audits": audits,
        "grade_smoke": grade_smoke,
        "pairs": [{"project": p, "variant": v, "seed": s,
                   "image": fixtures[(p, v)]["image"],
                   "base_commit": fixtures[(p, v)]["base_commit"],
                   "hidden_test_count": fixtures[(p, v)]["grade"]["test_count"]}
                  for p, v, s in SCORED_PAIRS_V7],
        "notes": ("Freeze v7: hard-pair scored campaign (8 pairs x 3 arms = 24 attempts) designed to separate "
                  "ordinary vs guided repair after the v6 null result (all 14 repair snapshots 16/16 hidden). "
                  "Five hard pairs (empty_tags, token_reserve, expiry_retain, storage_alias, coupled) target "
                  "diagnosis adjudication rather than defect visibility; the tinydb/token_alias anchor is kept "
                  "for longitudinal comparison and now carries the replay-detach trap test; both clean negative "
                  "controls are kept. Per-arm hidden pass-rate is the primary comparison metric. Freezes "
                  "v4/v5/v6 and all prior evidence untouched; negative and partial outcomes are preserved in "
                  "the append-only event streams."),
    }
    manifest["freeze_id"] = sha(canonical({k: v for k, v in manifest.items() if k != "freeze_id"}))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "freeze-v7-scored.json", manifest, exclusive=True)
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
    p = sub.add_parser("freeze-scored"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v6"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("freeze-scored-v7"); p.add_argument("out", type=Path); p.add_argument("--calibration", type=Path, required=True)
    p = sub.add_parser("grade-run"); p.add_argument("--run", type=Path, required=True,
        help="completed run directory (reads freeze.json + attempts, appends hidden_grades)")
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
    elif args.command == "freeze-scored":
        manifest = build_scored_freeze(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
    elif args.command == "freeze-scored-v6":
        manifest = build_scored_freeze_v6(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "freeze-scored-v7":
        manifest = build_scored_freeze_v7(args.out, read_json(args.calibration))
        print("FREEZE", manifest["freeze_id"])
        print("reservation:", json.dumps(manifest["reservation_verification"]))
        print("pairs:", len(manifest["pairs"]), "attempts:", len(manifest["schedule"]))
    elif args.command == "grade-run":
        results = grade_run(args.run)
        print("GRADED", len(results))
        for attempt_id, outcome in results:
            print(f"  {attempt_id}: {outcome}")
    elif args.command == "grade-smoke":
        # Independent grader smoke (gate): a seeded-bug snapshot must fail hidden
        # grading and a clean snapshot must pass — exercises the full
        # snapshot -> grade path on both outcomes.
        run_grade_smoke(read_json(args.calibration))


if __name__ == "__main__":
    main()

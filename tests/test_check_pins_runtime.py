"""check_pins.py: the git-ignored `.runtime/` scratch directory at
a vendored extension's root is excluded from the tree digest,
and nothing else is.

Acceptance (amendment package Item 4, 2026-10-26), both directions
against the real script's `main()` over a synthetic repository:

* (a) a run with a populated `.runtime/` scratch directory passes
  — the digest covers the vendored tree as committed, and scratch
  that exists only in a local working tree is not part of it (CI
  never saw this defect because CI checkouts carry no scratch);
* (b) a run with a genuinely drifted tracked vendored file still
  fails — the falsifier for this fix is any version of it that
  also hides real drift;
* the exclusion is scoped to the ignored path exactly
  (`.gitignore`: `/.specify/extensions/*/.runtime/`): a `.runtime`
  name deeper in the tree is vendored content and its drift fails.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_check_pins():
    spec = importlib.util.spec_from_file_location(
        "check_pins_under_test", ROOT / "scripts" / "check_pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_repo(tmp_path):
    """A minimal repository the real check_pins.main() accepts,
    with the recorded digests computed from the trees as built."""
    mod = load_check_pins()
    root = tmp_path / "repo"
    (root / "manifests").mkdir(parents=True)
    (root / ".specify" / "extensions").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\ndependencies = [\n"
        '  "applied-epistemic-engineering>=1.6.0,<2",\n'
        '  "specify-cli==0.9.0",\n]\n')
    versions = {"aee_engine": "1.6.0", "specify": "0.9.0",
                "aee_extension": "2.0.0", "evaluator_extension": "3.0.0",
                "vendored_sha256": {},
                "extension_commits": {"aee": "a" * 40,
                                      "evaluator": "b" * 40}}
    registry = {"extensions": {}}
    for key, dirname, ver in (("aee_extension", "aee", "2.0.0"),
                              ("evaluator_extension", "evaluator", "3.0.0")):
        base = root / ".specify" / "extensions" / dirname
        base.mkdir(parents=True)
        (base / "extension.yml").write_text(
            f"extension:\n  name: {dirname}\n  version: {ver}\n")
        (base / "payload.txt").write_text(f"vendored {dirname} bytes\n")
        versions["vendored_sha256"][dirname] = mod.tree_digest(
            base, mod.LOCAL_ARTIFACTS[dirname])
        registry["extensions"][dirname] = {
            "version": ver,
            "manifest_hash": "sha256:" + hashlib.sha256(
                (base / "extension.yml").read_bytes()).hexdigest()}
    (root / "manifests" / "versions.json").write_text(
        json.dumps(versions, indent=2))
    (root / ".specify" / "extensions" / ".registry").write_text(
        json.dumps(registry, indent=2))
    (root / ".specify" / "integration.json").write_text(
        json.dumps({"version": "0.9.0"}))
    mod.ROOT = root
    return mod, root


def test_clean_synthetic_repo_passes(tmp_path):
    mod, _root = build_repo(tmp_path)
    assert mod.main() == 0


def test_populated_runtime_scratch_still_passes(tmp_path):
    mod, root = build_repo(tmp_path)
    scratch = root / ".specify" / "extensions" / "aee" / ".runtime"
    (scratch / "nested").mkdir(parents=True)
    (scratch / "scratch.bin").write_bytes(b"local scratch" * 64)
    (scratch / "nested" / "state.json").write_text("{}")
    eval_scratch = root / ".specify" / "extensions" / "evaluator" / ".runtime"
    eval_scratch.mkdir(parents=True)
    (eval_scratch / "scratch.bin").write_bytes(b"local scratch" * 64)
    assert mod.main() == 0


def test_drifted_tracked_vendored_file_still_fails(tmp_path):
    mod, root = build_repo(tmp_path)
    payload = root / ".specify" / "extensions" / "aee" / "payload.txt"
    payload.write_bytes(payload.read_bytes() + b"drift")
    assert mod.main() == 1


def test_runtime_name_deeper_in_tree_is_not_excluded(tmp_path):
    mod, root = build_repo(tmp_path)
    deep = (root / ".specify" / "extensions" / "aee" / "sub" / ".runtime")
    deep.mkdir(parents=True)
    (deep / "kept.txt").write_text("vendored content\n")
    assert mod.main() == 1

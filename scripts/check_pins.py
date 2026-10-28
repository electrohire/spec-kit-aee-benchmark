"""Drift check: recorded pins vs. vendored bytes (Spec 003 FR-7.2/T708).

Fails (exit 1) when any recorded pin diverges from what is vendored or
required:

- pyproject.toml's engine pin vs ``manifests/versions.json`` ``aee_engine``
- each vendored extension's ``extension.yml`` version vs ``versions.json``
- each vendored extension tree's digest vs ``versions.json``
  ``vendored_sha256`` — digest recipe: sha256 over the sorted lines
  ``<relpath>\0<file sha256>\n`` for every vendored file except
  benchmark-local artifacts (``aee-config.yml``, ``assessments/``,
  ``ledger/``, evaluator ``results/``), ``__pycache__``, and the
  git-ignored ``.runtime/`` scratch directory at the extension root
  (``.gitignore``: ``/.specify/extensions/*/.runtime/``) — the digest
  covers the vendored tree as committed, and scratch that only
  exists in a local working tree is not part of it
- ``.specify/extensions/.registry`` versions and manifest hashes vs the
  vendored ``extension.yml`` files

Run from anywhere: ``python scripts/check_pins.py``.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ARTIFACTS = {"aee": {"aee-config.yml", "assessments", "ledger"},
                   "evaluator": {"results"}}
EXTENSIONS = (("aee_extension", "aee"), ("evaluator_extension", "evaluator"))
# Git-ignored scratch at the extension root (.gitignore anchors it
# exactly there: /.specify/extensions/*/.runtime/). Only that
# top-level directory is excluded; a ".runtime" name anywhere deeper
# is vendored content and stays in the digest.
SCRATCH_TOP = {".runtime"}


def tree_digest(base, excluded_top):
    lines = []
    for path in sorted(base.rglob("*"), key=lambda p: p.relative_to(base).as_posix()):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(base).as_posix()
        if rel.split("/")[0] in excluded_top or rel.split("/")[0] in SCRATCH_TOP:
            continue
        lines.append(f"{rel}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def extension_version(base):
    match = re.search(r"^\s+version:\s*(\S+)", (base/"extension.yml").read_text(), re.M)
    return match.group(1)


def engine_requirement(text):
    """The engine requirement declared in pyproject text, as
    (operator, version): the exact `==X.Y.Z` form, or the range
    `>=X.Y.Z,<2` form adopted for the Spec 006 migration (protocol
    amendment 2026-10-20, PC-5), whose floor is the recorded pin.
    Returns None when no supported form is declared."""
    match = re.search(r"applied-epistemic-engineering==([0-9.]+)", text)
    if match:
        return "==", match.group(1)
    match = re.search(r"applied-epistemic-engineering>=([0-9.]+),\s*<\s*2", text)
    if match:
        return ">=", match.group(1)
    return None


def main():
    versions = json.loads((ROOT/"manifests/versions.json").read_text())
    errors = []
    requirement = engine_requirement((ROOT/"pyproject.toml").read_text())
    if requirement is None:
        errors.append("engine pin: pyproject declares no supported "
                      "applied-epistemic-engineering requirement")
    elif requirement[1] != versions["aee_engine"]:
        errors.append(f"engine pin: pyproject requires {requirement[0]}{requirement[1]}, "
                      f"versions.json records {versions['aee_engine']}")
    registry = json.loads((ROOT/".specify/extensions/.registry").read_text())
    specify_pin = re.search(r"specify-cli==([0-9.]+)", (ROOT/"pyproject.toml").read_text())
    integration = json.loads((ROOT/".specify/integration.json").read_text())
    if not specify_pin or specify_pin.group(1) != versions["specify"] or integration["version"] != versions["specify"]:
        errors.append("Specify CLI pin, installed integration and versions.json differ")
    for key, dirname in EXTENSIONS:
        base = ROOT/".specify/extensions"/dirname
        found = extension_version(base)
        if found != versions[key]:
            errors.append(f"{dirname}: vendored extension.yml is {found}, "
                          f"versions.json records {versions[key]}")
        digest = tree_digest(base, LOCAL_ARTIFACTS[dirname])
        if digest != versions["vendored_sha256"][dirname]:
            errors.append(f"{dirname}: vendored tree digest {digest[:12]}... "
                          f"!= recorded {versions['vendored_sha256'][dirname][:12]}...")
        entry = registry["extensions"][dirname]
        if entry["version"] != versions[key]:
            errors.append(f"{dirname}: .registry records {entry['version']}, "
                          f"versions.json records {versions[key]}")
        manifest_hash = "sha256:" + hashlib.sha256((base/"extension.yml").read_bytes()).hexdigest()
        if entry["manifest_hash"] != manifest_hash:
            errors.append(f"{dirname}: .registry manifest_hash does not match "
                          "the vendored extension.yml")
    if errors:
        print("Pin drift detected:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"Pins consistent: engine {versions['aee_engine']}, "
          f"aee extension {versions['aee_extension']} @ {versions['extension_commits']['aee'][:7]}, "
          f"evaluator {versions['evaluator_extension']} @ {versions['extension_commits']['evaluator'][:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

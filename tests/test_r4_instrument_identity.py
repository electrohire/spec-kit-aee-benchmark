"""R-4 (Benchmarking Improvement Program, 2026-10-25):
pooling requires a proven-identical instrument.

The recorded seed-1/seed-2 check, mechanized: over the range
5937194f..125ce770 the changed files are exactly the allowed
set (CHANGELOG.md, src/benchmark_runner/workflow.py,
tests/test_needle_workstream_a.py) and no measured-path file
changed, so the seeds pool. The reproduction runs when the
checkout carries those commits (a full clone); the drills
below prove the machinery anywhere: a planted measured-path
change refuses the pooling with the file named, and an
unexpected change outside the allowed set refuses it too.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from benchmark_runner.preflight import instrument_identity

ROOT = Path(__file__).parents[1]
ALLOWED = ["CHANGELOG.md", "src/benchmark_runner/workflow.py",
           "tests/test_needle_workstream_a.py"]


def _has(ref):
    return subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-t", ref],
        capture_output=True).returncode == 0


@pytest.mark.skipif(not (_has("5937194f") and _has("125ce770")),
                    reason="probe freeze commits not in this "
                           "checkout (shallow clone)")
def test_recorded_seed_range_is_poolable():
    out = instrument_identity(str(ROOT), "5937194f", "125ce770",
                              allowed=ALLOWED)
    assert out["changed"] == sorted(ALLOWED)
    assert out["differing_measured"] == []
    assert out["poolable"]


@pytest.mark.skipif(not _has("b1b7331e"),
                    reason="phase-2 merge not in this checkout")
def test_doctored_range_refuses_with_the_file_named():
    # From the same freeze to the Phase 2 merge, runner.py —
    # a measured-path file — changed (the C-1/C-4 wiring).
    # Pooling across that range must be refused, named.
    out = instrument_identity(str(ROOT), "5937194f", "b1b7331e",
                              allowed=ALLOWED)
    assert not out["poolable"]
    assert "src/benchmark_runner/runner.py" in \
        out["differing_measured"]


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args],
                       check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / "src").mkdir()
    (repo / "src" / "runner.py").write_text("v1\n")
    (repo / "notes.md").write_text("n1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    return repo, git, base


def _head(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True).stdout.strip()


def test_drill_allowed_change_only_pools(tmp_path):
    repo, git, base = _repo(tmp_path)
    (repo / "notes.md").write_text("n2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "allowed")
    out = instrument_identity(str(repo), base, _head(repo),
                              measured=["src/runner.py"],
                              allowed=["notes.md"])
    assert out["poolable"]


def test_drill_measured_change_refuses(tmp_path):
    repo, git, base = _repo(tmp_path)
    (repo / "src" / "runner.py").write_text("v2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "measured change")
    out = instrument_identity(str(repo), base, _head(repo),
                              measured=["src/runner.py"],
                              allowed=["notes.md"])
    assert not out["poolable"]
    assert out["differing_measured"] == ["src/runner.py"]


def test_drill_unexpected_change_refuses(tmp_path):
    repo, git, base = _repo(tmp_path)
    (repo / "other.py").write_text("x\n")
    git("add", "-A")
    git("commit", "-q", "-m", "unexpected")
    out = instrument_identity(str(repo), base, _head(repo),
                              measured=["src/runner.py"],
                              allowed=["notes.md"])
    assert not out["poolable"]
    assert out["unexpected"] == ["other.py"]

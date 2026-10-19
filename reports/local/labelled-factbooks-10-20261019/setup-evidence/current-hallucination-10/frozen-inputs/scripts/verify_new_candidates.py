"""Local pre-calibration verification for new Claim-A candidate variants.

For each (project, variant): apply variant_files(), build a runnable package
overlay, run public tests (must ALL pass) and the full hidden suite (must fail
>=1 test, and specifically the declared new tests). Also verifies the clean
reference passes everything.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.home() / "workspace" / "spec-kit-aee-benchmark-local"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path.home() / "workspace" / "venvs" / "claim-a-test" / "lib" / "python3.12" / "site-packages"))

from benchmark_runner.matched_repair import variant_files, VARIANTS  # noqa: E402

SITE = Path.home() / "workspace" / "venvs" / "claim-a-test" / "lib" / "python3.12" / "site-packages"

NEW_VARIANTS = {
    "minisched": ["config_snapshot_stale", "done_status_mismatch",
                  "list_pending_returns_live", "update_unknown_silent"],
    "cachetools": ["resize_drops_expiry", "len_no_expire", "get_no_recency_refresh"],
    "tinydb": ["conflict_mutates_before_raise", "stale_table_cache",
               "tokens_shared_across_instances", "next_id_not_written_back"],
}

# hidden tests that must fail for each new variant (declared pins)
DECLARED_FAILS = {
    ("minisched", "config_snapshot_stale"): ["test_R04_config_change_honored", "test_R04_config_replaced"],
    ("minisched", "done_status_mismatch"): ["test_R08_done_token_stored_exact", "test_R08_terminal_statuses_exact"],
    ("minisched", "list_pending_returns_live"): ["test_R05_list_pending_detached"],
    ("minisched", "update_unknown_silent"): ["test_R02_update_unknown"],
    ("cachetools", "resize_drops_expiry"): ["test_R05_resize_preserves_expiry", "test_R05_resize_preserves_expiry_shrink"],
    ("cachetools", "len_no_expire"): ["test_R08_len_counts_live"],
    ("cachetools", "get_no_recency_refresh"): ["test_R02_get_refreshes_recency"],
    ("tinydb", "conflict_mutates_before_raise"): ["test_R07_conflict_leaves_data_unchanged"],
    ("tinydb", "stale_table_cache"): ["test_R02_retained_cache", "test_R02_retained_handle_sees_apply"],
    ("tinydb", "tokens_shared_across_instances"): ["test_R08_tokens_belong_to_instance"],
    ("tinydb", "next_id_not_written_back"): ["test_R05_next_id_monotonic"],
}


def build_overlay(project, variant):
    tmp = Path(tempfile.mkdtemp(prefix=f"verify-{project}-{variant}-"))
    files = variant_files(project, variant)
    if project == "minisched":
        for rel, data in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
    elif project == "tinydb":
        pkg = tmp / "tinydb"
        shutil.copytree(SITE / "tinydb", pkg)
        (pkg / "journal.py").write_bytes(files["tinydb/journal.py"])
    elif project == "cachetools":
        pkg = tmp / "cachetools"
        shutil.copytree(SITE / "cachetools", pkg, ignore=shutil.ignore_patterns("__pycache__"))
        (pkg / "tagged.py").write_bytes(files["src/cachetools/tagged.py"])
    # copy the fixture tests.py (full hidden suite)
    shutil.copy(ROOT / "benchmarks" / "repeated_local" / project / "tests.py", tmp / "tests.py")
    return tmp


def run_pytest(tmp, selector):
    cmd = [sys.executable, "-m", "pytest", "tests.py", "-q", "-p", "no:cacheprovider",
           "--deselect", "tests.py::test_placeholder_never_matches_xyz"]
    if selector == "public":
        cmd += ["-k", "test_public"]
    r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPATH": str(tmp)})
    return r


def parse_results(output):
    passed, failed, failed_names = 0, 0, []
    for line in output.splitlines():
        if line.startswith("FAILED"):
            failed += 1
            failed_names.append(line.split()[1])
        elif line.startswith("ERROR"):
            failed += 1
            failed_names.append("ERROR:" + line.split()[1])
    # summary line like "3 failed, 40 passed in 0.5s"
    for line in output.splitlines():
        if " passed" in line or " failed" in line:
            summary = line.strip()
    return summary, failed_names


def main():
    problems = []
    for project, variants in NEW_VARIANTS.items():
        for variant in variants + ["clean"]:
            tmp = build_overlay(project, variant)
            try:
                # public tests must pass
                r = run_pytest(tmp, "public")
                summary, failed = parse_results(r.stdout + r.stderr)
                if failed:
                    problems.append(f"{project}/{variant}: PUBLIC FAILURES: {failed}")
                    print(f"[FAIL-public] {project}/{variant}: {summary} :: {failed}")
                else:
                    print(f"[ok-public]   {project}/{variant}: {summary}")
                if variant == "clean":
                    r = run_pytest(tmp, "all")
                    summary, failed = parse_results(r.stdout + r.stderr)
                    if failed:
                        problems.append(f"{project}/clean: REFERENCE FAILURES: {failed}")
                        print(f"[FAIL-ref]    {project}/clean: {summary} :: {failed}")
                    else:
                        print(f"[ok-ref]      {project}/clean: {summary}")
                else:
                    r = run_pytest(tmp, "all")
                    summary, failed = parse_results(r.stdout + r.stderr)
                    declared = DECLARED_FAILS[(project, variant)]
                    missing = [d for d in declared
                               if not any(d in f for f in failed)]
                    if not failed:
                        problems.append(f"{project}/{variant}: seeded defect fails NO hidden test")
                        print(f"[FAIL-seed]   {project}/{variant}: defect invisible! {summary}")
                    elif missing:
                        problems.append(f"{project}/{variant}: declared pins not failing: {missing} (failed: {failed})")
                        print(f"[FAIL-pin]    {project}/{variant}: {summary} :: missing {missing}")
                    else:
                        print(f"[ok-seed]     {project}/{variant}: {summary} :: failed={failed}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("ALL NEW VARIANTS VERIFIED")


if __name__ == "__main__":
    main()

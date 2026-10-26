"""Standing pre-spend machinery (Benchmarking Improvement
Program R-2, R-3, R-4, 2026-10-25).

Three checks the probe test built by hand, made permanent:

- R-2 seed independence: (a) a code-level check that the seed
  is a campaign label no sampler input consumes — the module
  that builds the provider payload must not reference it;
  (b) an empirical check over two seeds' stores: byte-identical
  call-1 requests must yield different call-1 responses, pair
  by pair — identical responses would mean the "seeds" are the
  same draw.
- R-3 serving identity: a campaign admits no scored call
  until the serving fingerprint taken from the server itself
  matches the frozen recipe, field by field; the decision
  record exists before any call.
- R-4 instrument identity: two runs pool only if every file
  on the measured path is byte-identical across their range;
  a differing measured-path file refuses the pooling, named.
"""
import json
import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------- R-2

def call1_hashes(calls_path):
    """(request_sha256, response_sha256) of the first recorded
    call in a store's calls stream."""
    for line in Path(calls_path).read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            arts = rec["artifacts"]
            return (arts["request"]["sha256"],
                    arts["response"]["sha256"])
    raise ValueError(f"no calls recorded in {calls_path}")


def seed_independence_empirical(seed_stores):
    """seed_stores: {seed: {(arm, task): calls_jsonl_path}}.
    For every (arm, task) present under two seeds, the call-1
    requests must be byte-identical and the responses must
    differ. Returns the proof artifact."""
    seeds = sorted(seed_stores)
    pairs = []
    if len(seeds) >= 2:
        s1, s2 = seeds[0], seeds[-1]
        for key in sorted(set(seed_stores[s1])
                          & set(seed_stores[s2])):
            r1 = call1_hashes(seed_stores[s1][key])
            r2 = call1_hashes(seed_stores[s2][key])
            pairs.append({
                "arm": key[0], "task": key[1],
                "request_identical": r1[0] == r2[0],
                "response_differs": r1[1] != r2[1],
                "seed1_response": r1[1], "seed2_response": r2[1]})
    return {"pairs": pairs, "pairs_checked": len(pairs),
            "ok": bool(pairs) and all(
                p["request_identical"] and p["response_differs"]
                for p in pairs)}


_SEED_WORD = re.compile(r"\bseed\b", re.IGNORECASE)


def seed_references(source_text):
    """Lines of a source text that reference a seed. The
    code-level half of R-2: run over the module that builds
    the provider payload — the recorded proof at the probe
    freeze is that it contains no seed reference at all,
    because the seed exists only as a campaign label stamped
    into manifests by the campaign's facts module."""
    return [line.strip() for line in source_text.splitlines()
            if _SEED_WORD.search(line)]


# ---------------------------------------------------------------- R-3

# The frozen Pair D recipe (Stage A record; behavioral-probe
# and probe-test facts modules). R-3's gate proves the serving
# is the one a campaign named — Pair D's authority comes from
# Stage A, not from this table.
PAIR_D_RECIPE = {
    "alias": "qwen3.8-27b-q5",
    "model_card": "Qwen3.8-27B",
    "weights_file": "Qwen3.8-27B-UD-Q5_K_XL.gguf",
    "weights_bytes": 20876938144,
    "weights_sha256": "8601193d3d5760c37fb8ce1b43afebc69df5fb24e1"
                      "fbc5a547c32e2200305276",
    "context_size": 65536,
    "max_input_tokens": 57344,
    "max_output_tokens": 8192,
    "preserve_thinking": True,
    "grammar": False,
}


def verify_serving(fingerprint, recipe):
    """fingerprint: the serving's identity as read back from
    the server itself by the driver (never from the driver's
    own configuration). Every recipe field must match exactly.
    Returns the admission record: admitted only when all
    checks pass; the record is what a campaign posts before
    its first scored call, and a refusal is an equipment halt
    at zero scored spend."""
    checks = {field: fingerprint.get(field) == want
              for field, want in recipe.items()}
    return {"admitted": all(checks.values()),
            "checks": checks,
            "recipe_alias": recipe.get("alias"),
            "fingerprint": {f: fingerprint.get(f) for f in recipe}}


# ---------------------------------------------------------------- R-4

# The probe path's measured files (the probe test's recorded
# instrument check). A campaign pooling other paths names its
# own list in its registration; this is the standing default.
MEASURED_PATH_FILES = [
    "src/benchmark_runner/runner.py",
    "src/benchmark_runner/residual.py",
    "src/benchmark_runner/context.py",
    "src/benchmark_runner/local_provider.py",
    "src/benchmark_runner/accounting.py",
    "src/benchmark_runner/budget_guard.py",
    "src/benchmark_runner/store.py",
    "src/benchmark_runner/tripwires.py",
    "src/benchmark_runner/schema.py",
    "src/benchmark_runner/experiment.py",
]


def _changed_files(repo, base, head):
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only",
         f"{base}..{head}"],
        capture_output=True, text=True, check=True)
    return sorted(f for f in out.stdout.splitlines() if f)


def instrument_identity(repo, base, head,
                        measured=MEASURED_PATH_FILES,
                        allowed=()):
    """Pooling check over a commit range: poolable only when
    no measured-path file changed and every changed file is in
    the registration's allowed set. Differing and unexpected
    files are named either way."""
    changed = _changed_files(repo, base, head)
    differing = [f for f in changed if f in set(measured)]
    unexpected = [f for f in changed
                  if f not in set(allowed) and f not in set(measured)]
    return {"poolable": not differing and not unexpected,
            "changed": changed,
            "differing_measured": differing,
            "unexpected": unexpected}

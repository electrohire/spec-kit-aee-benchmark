# Running the matched-repair phase-2 campaign on your machine

The freeze-v8 phase-2 cross-file scored campaign needs a Docker-capable host. This VM
cannot run containers, so the run happens on your Windows GPU machine via
WSL2.

## One-time setup (Windows)

1. Install WSL2 with Ubuntu from the Microsoft Store (or `wsl --install -d Ubuntu`).
2. Install Docker Desktop for Windows and enable the WSL2 backend
   (Settings > Resources > WSL integration > enable Ubuntu).
3. In an Ubuntu terminal, confirm Docker works: `docker run --rm hello-world`.

## The run

In the Ubuntu terminal:

```bash
git clone https://github.com/electrohire/spec-kit-aee-benchmark.git ~/mr-run
cd ~/mr-run
git checkout main
bash scripts/host-setup.sh
```

Or, if you already have the repo from a previous campaign, the script
re-clones into `~/mr-smoke/repo` itself; just run it:

```bash
bash scripts/host-setup.sh
```

The script does everything in order and stops before spending money:

1. Host checks: Linux, Docker daemon, Python 3.12+, git.
2. Checks out `main`, installs the package into an isolated venv
   at `~/mr-smoke/venv`, runs the test suite.
3. Asks for your OpenAI API key (typed hidden, kept in the shell session
   only, never written to disk). The key needs access to `gpt-6-astra`.
   Export it beforehand to skip the prompt:
   `export OPENAI_API_KEY='sk-...'` (the key must be **export**ed, not just
   assigned, or the preflight probe cannot see it).
4. Verifies the key with a free `/v1/models` probe.
5. Clones the tinydb and cachetools upstreams at the pinned revisions.
6. Builds the fixture images, calibrates them (seeded bugs must fail
   hidden grading, clean controls must pass), runs the grader smoke,
   audits the solver images, and verifies the reservation bound.
7. Builds freeze v8 (phase-2 cross-file scored campaign: 4 pairs x
   diagnose/ordinary/guided, seed 20260918) with all four verification
   flags set (the freeze command refuses to set them unless each gate
   genuinely passes; the real-smoke flag is grounded on the completed
   2026-09-21 freeze-v4/v5/v6/v7 runs).
8. Verifies the freeze manifest is untampered.

Then it shows the freeze id, the caps, the worst-case reservation, and the
12-attempt schedule, and asks you to type `RUN`. Nothing is billed until
then.

## The pairs

Four cross-file pairs piloting the harder task class after the v7 null
(second consecutive graded null on guided-vs-ordinary quality; ceiling
effect at gpt-6-astra on single-module repair). The synthetic `minisched`
package (config/store/scheduler) seeds defects whose symptom surfaces in
`scheduler.py` while the cause lives in another module; each carries a
plausible wrong-layer fix in `scheduler.py` that passes every public test
but fails hidden tests pinned at the true layer:

- `minisched/config_default`: wrong retry default in config.py (trap: `or 3`
  coercion in the scheduler breaks explicit max_retries=0)
- `minisched/store_add_alias`: store.add aliases the caller payload
  (trap: defensive copy in scheduler.enqueue leaves the store broken)
- `minisched/coupled_xfile`: both defects across files (completeness check)

plus the `minisched/clean` negative control.

## What the campaign costs

- Attempt cap $25, global cap $100 (Tristen authorized the freeze-v8
  phase-2 campaign 2026-09-21).
- Expected spend ~$6-9 at ~$0.50-0.75/attempt (v7 measured $0.46/attempt
  over 24 attempts; cross-file pairs use more tool calls).
- Worst-case reservation per repair attempt is about $15.40 at the
  conservative (long-tier) rates; measured spend settles lower.
- Measured spend so far: $22.8863 ($1.4831 v4 smoke + $1.5029 v5 +
  $8.8870 v6 + $11.0133 v7) against the $100 global cap ($77.1137 remaining). The 2026-09-20 failed run's
  unmeasured charge was discounted by Tristen on 2026-09-21 as
  unverifiable, so the cap counts only measured spend.
- The script prints measured spend per attempt at the end.

## After the run

Full evidence lands in `~/mr-smoke/runs/scored-v8` (append-only event
streams: attempts, calls, budget, diagnostics, repair rounds, hidden
grades). Send me that directory or the spend summary and I will write up
the results.

The end-of-run table compares ordinary vs guided by **hidden pass-rate**
(PASS/FAIL with passed/total), which is the primary metric for hard pairs
where partial passes are expected; binary pass/fail is secondary.

## Notes

- The smoke pair (`tinydb/bool_id`, seed 20260918) is excluded from every
  scored freeze, so the scored run does not contaminate the pilot.
- Historical freezes v2/v3/v4/v5/v6/v7 and all prior evidence are untouched.
- Negative and partial outcomes are preserved, never discarded.
- To run again later, re-run the script; it rebuilds from `main`.
  Previous calibration/freeze outputs are archived with timestamps, never
  overwritten. Expect up to ~30 minutes per attempt; the full campaign may
  take several hours.

# Running the matched-repair scored comparison on your machine

The 3-attempt scored comparison needs a Docker-capable host. This VM cannot run
containers, so the run happens on your Windows GPU machine via WSL2.

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

The script does everything in order and stops before spending money:

1. Host checks: Linux, Docker daemon, Python 3.12+, git.
2. Checks out `main`, installs the package into an isolated venv
   at `~/mr-smoke/venv`, runs the test suite.
3. Asks for your OpenAI API key (typed hidden, kept in the shell session
   only, never written to disk). The key needs access to `gpt-6-astra`.
4. Verifies the key with a free `/v1/models` probe.
5. Clones the tinydb and cachetools upstreams at the pinned revisions.
6. Builds the 8 fixture images, calibrates them (seeded bugs must fail
   hidden grading, clean controls must pass), runs the grader smoke,
   audits the solver image, and verifies the reservation bound.
7. Builds freeze v5 (scored comparison, pair `tinydb/token_alias`, seed
   20260918) with all four verification flags set (the freeze command
   refuses to set them unless each gate genuinely passes; the real-smoke
   flag is grounded on the completed 2026-09-21 freeze-v4 smoke).
8. Verifies the freeze manifest is untampered.

Then it shows the freeze id, the caps, the worst-case reservation, and the
3-attempt schedule, and asks you to type `RUN`. Nothing is billed until then.

## What the scored run costs

- Attempt cap $25, global cap $100 (Tristen authorized the fresh scored run 2026-09-21).
- Worst-case reservation per repair attempt is about $15.40 at the
  conservative (long-tier) rates; measured spend settles lower.
- Measured spend so far: $1.4831 (freeze-v4 smoke, 2026-09-21). The
  2026-09-20 failed run's unmeasured charge was discounted by Tristen on
  2026-09-21 as unverifiable, so the cap counts only measured spend.
- The script prints measured spend per attempt at the end.

## After the run

Full evidence lands in `~/mr-smoke/runs/scored-v5` (append-only event
streams: attempts, calls, budget, diagnostics, repair rounds). Send me that
directory or the spend summary and I will write up the results.

## Notes

- The smoke pair (`tinydb/bool_id`, seed 20260918) is excluded from every
  scored freeze, so the scored run does not contaminate the pilot.
- Historical freezes v2/v3/v4 and all prior evidence are untouched.
- Negative and partial outcomes are preserved, never discarded.
- To run again later, re-run the script; it rebuilds from `main`.
  Previous calibration/freeze outputs are archived with timestamps, never
  overwritten. Expect up to ~30 minutes per attempt.

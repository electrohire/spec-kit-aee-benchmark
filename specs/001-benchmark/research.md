# Research decisions
- SWE-bench 5.0.2: 02e7a74ffd0b707aab73d203fe87bdc7c76afc8e.
- Task repo: 3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d.
- Use published_tasks for Verified membership; explicit -i IDs for grading.
- mini-SWE-agent 2.4.6 (04d809ceab9df28f9adaed044884180159172930) examined:
  stock post-call spending stop and hidden retries are insufficient. Use a thin
  common HTTP runner with persisted reservations and native usage instead.
- Solver containers have network disabled, no mounts and no credentials.
- Official OpenAI Chat Completions API reference read 2026-09-17.
- Subscription usage is not API spend. Price and model remain unset.
- Organization-wide license policy not established; selection pending.
- ZIP excluded entirely following explicit user correction.

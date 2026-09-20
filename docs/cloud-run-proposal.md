# Cloud benchmark run proposal — matched-repair on GPT-6 Astra

Status: **proposal only**. No paid calls made, no API key set or shared, nothing
frozen. This document exists so Tristen can approve (or reject) each element
before any money moves. Standing rule: keep work offline until Tristen
explicitly authorizes paid calls and freezes a spending cap (START_HERE.md,
2026-09-17 decision).

## Status update 2026-09-20

- Route A port is complete on branch `feat/cloud-matched-repair`: matched-repair
  arms, guided-only AEE findings, diagnose-first scheduling, deterministic
  repair order, unique attempt IDs, exact authorization text, fail-closed
  verification flags, long-context-tier exclusion check (96 tests green).
- Provider now authenticates via the Secure Vault connector on the managed VM
  and via `OPENAI_API_KEY` on an operator host (fail-closed either way).
- OpenAI key connected; free `/v1/models` probe confirms `gpt-6-astra`
  available. Pricing cross-checked 2026-09-20: $10/$1/$50 standard,
  $20/$2/$75 above 272K input tokens.
- The managed VM cannot run containers (supervisor restriction, proven on two
  VMs), so fixture builds, calibration, grader smoke, audit, freeze v4, and
  the 3-attempt smoke move to a Docker-capable host. Runbook:
  `docs/host-run.md`; one-command setup: `scripts/host-setup.sh`.
- Zero paid spend so far. The 3-attempt development smoke ($25/attempt,
  $100 global, authorized 2026-09-20) is ready to run from the host script,
  which stops for explicit confirmation before any paid call.

## What we are testing

Whether AEE-guided repair **separates** from ordinary repair on a frontier
model. This is an open question, not a showcase.

Current evidence (matched-repair-01, local Qwen): ordinary repair fixed 4/12
seeded bugs, guided repair fixed 5/12 — and only 1 of 16 shared diagnostics
reached an actual AEE assessment. The extra guided fix happened without an
assessment, so matched-repair-01 establishes **no AEE benefit**. The cloud run
re-tests that null result with a more capable model and the v3
diagnostic-termination fix (PR #2, commit `6ccaa4c`), which guarantees every
claim-bearing diagnostic phase now terminates with valid claims (structural
done-only final step + mid-phase draft checkpoint).

The honest outcome space includes: no separation, separation in either
direction, or a conditional separation. The design below is built so none of
those can be an artifact of the harness. The LinkedIn article stays
unpublished until evidence — not ambition — supports it.

## Design (unchanged protocol, new engine)

Same matched-repair protocol as scripts/matched_repair.py:

- 16 matched pairs: 12 seeded bugs + 4 clean negative controls, across
  `tinydb` and `cachetools`, 2 seeds each (see VARIANTS in
  scripts/matched_repair.py).
- Per pair: one **shared** read-only diagnostic (identical start, identical
  tools, identical public-test feedback), then two repair arms from the same
  snapshot: `ordinary_repair` and `aee_guided_repair` (only the guided arm
  receives actual AEE/Evaluator findings). Arm order randomized per pair.
- 2 fixed repair rounds × up to 8 calls each; diagnostic up to 8 calls with
  the v3 structural termination fix. Hidden grading happens once, after all
  runs; hidden outcomes are never fed back to any treatment or the shared
  diagnostic.
- 32 repair attempts + 16 shared-diagnostic attempts = 48 attempts total.
  The diagnostic cost is charged once to the physical-work ledger (split
  evenly per arm only for comparison arithmetic).

## 1. What must be ported to the cloud runner

`scripts/matched_repair.py`'s local `Provider` (scripts/repeated_local.py)
**cannot be pointed at OpenAI by configuration.** The differences are
structural, not cosmetic:

| Concern | Local `Provider.query(messages, phase, stage, deadline)` | Cloud `OpenAIProvider.query(messages, phase, timeout, retry)` |
|---|---|---|
| Transport | Local llama-server: `/v1/chat/completions`, `/tokenize`, `/apply-template`, `/slots` | `https://api.openai.com/v1/chat/completions`, `OPENAI_API_KEY` from env |
| Request params | llama sampling: temp 0.6, top_p 0.95, top_k 20, min_p, penalties, seed, `response_format: json_object`, chat-template `enable_thinking` | `model`, `reasoning_effort`, `max_completion_tokens`, `service_tier`; temperature only if set |
| Context mgmt | Preflight tokenization + binary-search history trim to 32k context | No preflight; mini-SWE-agent context handling + ceiling reservation + `token_cap` hard stop |
| Budgeting | Imputed debit (preflight input + max_output) against a token cap | **Full USD reservation before every call**: `(max_input_tokens × input_price + max_output_tokens × output_price)/1e6`, against frozen per-attempt and global caps; settles to native usage cost; unknown usage is never released |
| Usage | Response `usage` (may be missing → `reserved_not_imputed`) | Provider-native usage incl. `cached_input_tokens` and `reasoning_tokens` (billed at output rate), schema-validated, tiered pricing |
| Failures | llama idle-slot waiting, local retry semantics | `ProviderError`; the runner stops on uncertain infrastructure/provider errors and preserves all charges |

Two routes exist:

- **Route A (recommended): port matched-repair into `src/benchmark_runner`.**
  The runner already has everything the cloud run needs — USD reservations,
  price snapshots, Docker isolation, artifact stores, freeze verification —
  and rebuilding those for the local harness would be re-implementing the
  runner. Porting requires real engineering, not a switch:
  1. Matched-repair task fixtures: Docker solver images for the
     `tinydb`/`cachetools` seeded-bug + clean-control fixtures, pinned by
     digest with base commits, staged spec + public tests as the problem
     statement.
  2. Freeze task set + schedule: 32 repair attempts + 16 diagnostic attempts,
     with the shared-diagnostic treatment and arm randomization encoded in
     the frozen schedule.
  3. Arms: `repair_ordinary` / `repair_guided` as cloud-runner arms
     (distinct from the existing `baseline`/`spec_kit`/`spec_kit_aee` arms),
     where the guided arm injects `compact_assessment(evaluation)` findings
     and nothing else differs.
  4. Port `Session.phase`'s v3 structural termination fix (done-only final
     step, mid-phase draft checkpoint, honest `DIAG-NONTERMINATION-01`
     terminal claim) into the cloud adapter — `MiniModel` in runner.py
     currently accepts only `shell`/`done` actions and has no draft-claims
     step; the fix must survive the port or the non-termination failure
     mode returns.
  5. Port fixture calibration (scripts/matched_repair.py `calibration`) and
     hidden grading into grading.py's separate grading path.
- **Route B: write an OpenAI-backed provider for the local Session
  framework.** Feasible (swap transport, drop llama-only preflight, adopt
  ceiling reservation) but then budgets, Docker isolation, price snapshots,
  and audit trails all need rebuilding. Not recommended.

Nothing runs on the cloud today: matched-repair is not wired to the cloud
runner, and Route A is an unstarted workstream.

## 2. Measured-spend estimate for one full campaign (Astra list prices)

Token totals are **measured** from `reports/local/matched-repair-01/summary.json`
(local Qwen run). Prices are Astra list as supplied for this proposal:
**$10/1M input, $1/1M cached input, $50/1M output**.

| Segment | Uncached input | Cached input | Output | Cost |
|---|---|---|---|---|
| ordinary_repair (16 attempts, 227 calls) | 292,297 × $10/1M = $2.92 | 1,220,064 × $1/1M = $1.22 | 110,299 × $50/1M = $5.51 | **$9.66** |
| aee_guided_repair (16 attempts, 242 calls) | 312,134 × $10/1M = $3.12 | 1,444,303 × $1/1M = $1.44 | 113,361 × $50/1M = $5.67 | **$10.23** |
| Shared diagnostic, physical ledger (16 attempts, 128 calls, charged once) | 129,944 × $10/1M = $1.30 | 500,081 × $1/1M = $0.50 | 47,258 × $50/1M = $2.36 | **$4.16** |
| **Full campaign total** | | | | **≈ $24.05** |

Per matched pair ≈ **$1.50**; per repair attempt ≈ **$0.62**; per diagnostic
attempt ≈ **$0.26**.

Honesty caveats — this is a planning number, **not** a budget cap:

- Qwen's tokenizer ≠ Astra's tokenizer; actual token counts will differ.
- The local run's ~80% prompt-cache hit rate came from llama-server
  `cache_prompt`; Astra prompt caching is automatic (≥1024-token prefixes)
  and hit rates on real trajectories may be lower.
- **Biggest uncertainty: reasoning tokens.** At `reasoning_effort=medium` a
  reasoning model will likely emit more output per call than the local
  ~470 tokens/call average, and reasoning tokens bill at the $50/1M output
  rate. The estimate assumes a comparable output profile; the smoke run
  measures the real one.
- Estimate says nothing about outcome; spend does not buy a favorable result.

## 3. Reservation bounds and recommended caps

The runner reserves the **full documented ceiling per call** before any call
is permitted (provider.py):

`reserve = (max_input_tokens × input_price + max_output_tokens × output_price) / 1e6`

Sensible frozen ceilings, anchored to measured data:

- `max_input_tokens = 32768` — matches the local 32k context budget; the
  largest measured preflight input was 11,241, so this gives ~3× headroom.
- `max_output_tokens = 4096` — matches the local run and the offline freeze.

Per-call reservation at Astra prices:

- 32,768 × $10/1M + 4,096 × $50/1M = $0.328 + $0.205 = **≈ $0.53/call**

Worst-case reservations per attempt:

- Repair attempt (16 calls max): 16 × $0.53 = **$8.52**
- Diagnostic attempt (8 calls max): 8 × $0.53 = **$4.26**

If the smoke shows reasoning verbosity routinely threatening the 4,096
output ceiling, raise `max_output_tokens` to 16,384 — but note this raises
the per-call reservation to **≈ $1.15/call** (repair attempt: $18.35).

Recommended caps, following the repo's staged discipline:

1. **Development smoke first**: 3 attempts on one excluded fixture pair
   (diagnostic + one repair per arm), purpose `development_smoke`, separate
   freeze. **attempt_cap_usd = $25**, **global_cap_usd = $100**. The attempt
   cap covers the worst-case repair reservation ($18.35 even at 16k output
   ceiling) with headroom; the global cap covers 3 worst-case attempts
   ($75) with margin. Real smoke is an integration and spend-measurement
   check — not a performance comparison.
2. **Sized pilot next**: attempt_cap_usd = $25 (unchanged, reservation-safe);
   global cap proposed from measured smoke as
   `global_cap_usd = 48 attempts × $25 = $1,200` reservation ceiling, with
   Tristen authorizing a **working cap** of measured-spend × 5 after seeing
   real numbers. The expected measured spend is ~$25–75, but the cap is set
   from reservations and measured data, never from the $24 estimate alone.

## 4. `validate_live()` gates and freeze v4 fields

Every gate in `src/benchmark_runner/runner.py::validate_live` must be
satisfied before any paid call. Enumerated verbatim from the code:

1. All of these frozen config keys must be non-empty: `model`,
   `reasoning_effort`, `price_snapshot_id`, `price_source`,
   `budget_authorization`, `global_cap_usd`, `attempt_cap_usd`,
   `max_input_tokens`, `max_output_tokens`, `token_cap`.
2. `reservation_bound_verified` — operator has verified the model-specific
   context/output reservation bounds.
3. `grader_smoke_verified` — successful independent grader smoke before any
   model spending.
4. `solver_image_audit_verified` — solver images audited for hidden grader
   material before any model spending.
5. Non-smoke runs additionally require `real_smoke_verified`; smoke runs
   require `purpose == "development_smoke"` on a separately frozen
   development manifest.
6. `OPENAI_API_KEY` present in the environment (never pasted in chat or
   stored in the repo).
7. Not Windows: live runs require Linux/WSL2 with Docker (offline commands
   support Windows).
8. `docker info` succeeds.
9. Every task's problem statement must be hydrated (no `REHYDRATE_` stubs),
   `docker_args(image, "preflight")` must construct, and
   `docker image inspect <image>` must succeed for each solver image.

Freeze v4 config fields to set (offline-freeze-v3 leaves all of these null;
v4 must fill them before `freeze()` and commit):

- `model`: the exact Astra snapshot id the API returns (the provider
  rejects a response whose `model` field differs — verify with the real
  smoke before freezing the scored manifest).
- `reasoning_effort: medium` (middle of low/medium/high/xhigh/max; xhigh/max
  would raise output-token costs materially — caps protect regardless).
- `temperature: null` (unsupported alongside reasoning effort).
- `max_input_tokens: 32768`, `max_output_tokens: 4096`
  (or 16384 if smoke measures reasoning verbosity near the ceiling).
- `token_cap`: attempt token ceiling consistent with the reservation
  (runner additionally enforces `used + max_input + max_output ≤ token_cap`
  per request inside `execute_attempt`).
- `prices: {input: 10.0, cached_input: 1.0, output: 50.0}`, plus
  `long_context_prices` / `long_context_threshold` **only if** Astra has a
  long-context tier — the runner reserves the *highest* applicable rate, so
  an unverified tiering assumption is a budget hole. (Precedent: gpt-5.4
  doubled input / 1.5× output above 272K; Astra's policy must be checked
  against the official pricing page before freezing.)
- `price_snapshot_id` + `price_source` (official OpenAI pricing URL + date
  checked).
- `budget_authorization`: Tristen's explicit written approval naming the
  dollar cap (the smoke proposal's $30 pattern, updated for §3).
- `global_cap_usd`, `attempt_cap_usd`: per §3.
- `purpose` (`development_smoke` for the smoke freeze), `seed`, `max_calls`,
  `max_recovery_rounds: 2`, `timeout_seconds`, `service_tier: default`,
  `currency: USD`, `runner` identifier, verification flags
  (`reservation_bound_verified`, `grader_smoke_verified`,
  `real_smoke_verified`, `solver_image_audit_verified`) flipped only when
  each gate genuinely passes.
- Tasks: 16-pair matched-repair fixture tasks with pinned image digests and
  base commits; the smoke fixture pair listed under exclusions of the scored
  freeze; schedule with deterministic attempt ids.

## 5. Blockers to starting today

- **Docker is not installed on this Linux VM** (`docker` not found).
  `validate_live` hard-fails without it. Either install Docker here or run
  from a host that has it (the Windows GPU host needs WSL2 + Docker, which
  was already unreachable there per START_HERE.md).
- **No paid-call authorization.** An `OPENAI_API_KEY` exists in this VM's
  environment, but key presence ≠ authorization. Per AGENTS.md and
  START_HERE.md: no paid runs without frozen authorized caps and verified
  preflight. Tristen must approve §3's caps in writing first. The key must
  never appear in chat, logs, or the repo; the runner reads it from the
  environment only.
- **Astra pricing unverified.** The $10/$1/$50 rates and 1.05M context were
  supplied for this proposal, not checked against an official pricing page;
  long-context tiering is unknown. A price snapshot must be verified before
  freezing v4.
- **Exact model snapshot id unknown.** The provider raises on model
  mismatch, so the frozen `model` string must be the exact id the API
  returns — confirm via the real smoke call.
- **Engineering not started.** Matched-repair is not wired to the cloud
  runner (Route A, §1). No cloud execution is possible until the adapter,
  fixtures, and grading port exist and their smoke passes.
- **Gates 2–4 of validate_live are unmet**: grader smoke, solver image
  audit, and reservation-bound verification are all still `false` in the
  current config.

## Recommended next actions (all need Tristen's go-ahead)

1. Approve the staged money plan: $100 global / $25 per-attempt for the
   3-attempt development smoke, pilot caps sized from measured smoke.
2. Authorize the Route A engineering workstream (port matched-repair to the
   cloud runner) — estimated scope is an adapter + fixtures + grading port,
   on Linux with Docker available.
3. Decide the execution host: this VM (install Docker) or the Windows GPU
   host via WSL2 (Docker currently unreachable there).
4. Keep the article unpublished; rewrite it only after the cloud evidence
   exists — whatever it shows.

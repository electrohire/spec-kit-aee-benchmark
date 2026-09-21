# Claim B: condensation insurance — experiment design

Status: design + implementation built offline 2026-09-21. No paid model calls
made; no campaign authorized yet. Implements v9 sections 2-5 for Claim B.

## 1. Claim and falsifier

**Claim B (condensation insurance):** as working context condenses, important
constraints get lost; Spec-Kit artifacts (spec.md, plan.md) act as external
persistent memory that survives condensation. For frontier models, where
Spec-Kit + AEE is the observed +14-35% cost premium (v5-v8.1), that premium is
insurance against hallucinations and spec deviance. This experiment prices the
loss the insurance prevents.

**Falsifier (pre-registered):** Claim B is falsified if, at the aggressive
condensation level, constraint retention does not differ between the
artifacts arm and the summary-only arm, or if the artifacts arm hallucinates
at equal or higher rates. A null redirects to stronger condensation or richer
artifact types; it does not license weakening the test until it passes.

**Aligned-spec condition (v8 lesson, permanent):** the v8 campaign proved a
misaligned spec manufactures hallucinated repairs (the diagnostic phase
generated a phantom defect from ambiguous wording and all arms "fixed" it).
Claim B is therefore "aligned Spec-Kit artifacts reduce spec deviance."
Every task passes the grader-spec alignment gate (section 6) before any spend.
Artifact fidelity is a controlled condition: artifacts are task-provided,
frozen, and aligned — not agent-written. (Agent-written artifacts are a
follow-up experiment, not this one.)

## 2. Experimental design: 3 x 2

**Factor 1 — condensation level** (applied to the phase-1 transcript between
phases; deterministic procedures in section 3):
- `intact`: full phase-1 transcript, verbatim.
- `light`: summary preserving stated requirements, <= 50% of spec words.
- `aggressive`: short bullet summary of constraint titles only, <= 20% of
  spec words.

**Factor 2 — arm**:
- `artifacts`: phase-2 sandbox contains the frozen `/task/spec.md` and
  `/task/plan.md`; the agent is instructed to re-read both before
  implementing. (External persistent memory.)
- `summary`: phase-2 sandbox contains no spec/plan; the agent implements from
  the condensed phase-1 summary only.

**Cells:** 6 per task (3 levels x 2 arms). Phase 1 is shared: one planning
attempt per task establishes the counterfactual "the agent had full context";
its transcript is frozen, then condensed per level for the phase-2 attempts.

**Predictions:** (a) the summary arm's constraint retention degrades
intact -> light -> aggressive; (b) the artifacts arm is flat across levels;
(c) the arms gap widens with more aggressive condensation; (d) the
intact+artifacts cell matches intact+summary (artifacts do not hurt when
context is intact — ceiling control).

## 3. Deterministic condensation procedures

Real compaction is uncontrolled and unreproducible; these procedures are a
controlled, deterministic model of its information-loss profile. No model
calls, no randomness: the same transcript and spec always produce the same
summary (byte-identical; asserted by tests).

**Input:** the frozen phase-1 transcript (list of {role, content} messages)
and the task's spec.md. Specs are authored in a strict constraint format so
the parser is exact:

```
<intro paragraphs: what the module is, API surface>

## C01: <title>
<requirement statement as the FIRST sentence. Rationale, examples, and edge
cases follow in later sentences.>

## C02: <title>
...
```

**Parser** (`parse_constraints`): splits on lines matching `^## (C\d+): (.+)$`.
Detail = text until the next `## ` line or end of file. Preamble = text before
the first constraint. Malformed specs fail the build.

**Level procedures** (`summarize_phase1`):
- `intact`: `"[role] content"` lines joined verbatim. No budget.
- `light`: one deterministic activity line
  `Phase 1: full spec read (W words, K constraints), M assistant turns.`
  (W, K, M computed from the inputs), then the spec preamble's first
  paragraph, then per constraint one line: `C0N: <title>. <first sentence of
  detail>`. Budget: total words <= 50% of spec words. Rationale for the
  "first sentence" rule: specs are authored so the first detail sentence IS
  the requirement statement (terse and complete; rationale, examples, and
  edge cases live in following sentences) — what is dropped is exactly the
  detail real summarization sheds first. Constraint titles are kept terse
  (2-4 words) so the fixed overhead (activity line, IDs, titles) fits the
  budget even for short specs.
- `aggressive`: the activity line, then per constraint one line:
  `C0N: <title>`. All detail dropped. Budget: total words <= 20% of spec words.

Budgets use whitespace-split words. The summarizer raises (fail closed) if a
budget is exceeded — a spec whose first sentences are too long is rewritten,
not accommodated. The test suite asserts all three levels for every task:
determinism (two runs byte-identical), budget compliance, and constraint-ID
coverage (every C0N id appears in the light/aggressive summaries).

**Limitation (honest):** this is extractive, not abstractive, summarization.
It controls information loss exactly, which is what the experiment needs, but
a real abstractive compactor might preserve different details. Documented here
so the paper cannot oversell the manipulation.

## 4. Multi-phase task schema

Each task lives in `benchmarks/condensation/<task>/`:

| file | role |
|---|---|
| `task.yaml` | name, module, constraint kinds (requirement/subtle/negative/phantom), trap description |
| `spec.md` | phase-1 requirements, strict constraint format (section 3) |
| `plan.md` | frozen reference plan (task-provided artifact, re-read by the artifacts arm) |
| `reference.py` | reference implementation; passes all hidden tests |
| `tests_public.py` | public tests: basic happy path only; given to both arms in phase 2 |
| `tests_hidden.py` | hidden tests; every test pinned to >= 1 constraint id via `PINS` |
| `trap.py` | the canonical attractive wrong implementation (grader-side only, never in a solver sandbox) |
| `phase2.md` | phase-2 prompt template (both arms) |
| `alignment.md` | completed alignment-gate checklist for this task |

**Constraint kinds** (in `task.yaml`):
- `requirement`: ordinary pinned behavior.
- `subtle`: stated once in the spec; the constraints condensation is expected
  to lose first. Every task has >= 2.
- `negative`: "must NOT" behavior; pins absence of ungrounded behavior.
  Every task has >= 1. Failed negative tests count as hallucinations.
- `phantom`: a suspected defect the plan explicitly resolves as not-a-defect
  (task 10). "Fixing" it fails hidden tests; counts as hallucination.

**Phase 1 (shared, planning):** the agent receives the full spec.md and writes
brief planning notes to `/work/phase1-notes.md` (at most 4 model calls). This
establishes the counterfactual honestly: the transcript proves full context
was present. The transcript is frozen; no phase-1 output is graded.

**Phase 2 (implementation, per cell):** the agent implements `/work/<module>.py`
(at most 8 model calls) with tests_public.py available. Artifacts arm: the
sandbox also contains `/task/spec.md` + `/task/plan.md` and the prompt
instructs re-reading them first. Summary arm: no spec/plan files; the prompt
carries only the condensed summary. Both arms get identical public tests and
the identical implementation target. Treatment isolation (constitution II):
solvers receive only their frozen treatment; hidden tests never enter any
solver sandbox.

## 5. Metrics

**Primary: constraint retention.** Hidden tests run offline against the
phase-2 snapshot. Each hidden test is pinned to constraint ids; a constraint
is retained iff all its pinning tests pass. Reported per constraint kind and
overall: `retained / total`. The campaign estimand is the paired per-task
retention difference between arms at each condensation level, with bootstrap
95% CI (analysis follows the paid campaign; the harness records per-test
outcomes append-only).

**Secondary: hallucination count** (operational definition, v9 section 2:
behavior grounded in neither the spec artifacts nor the tests):
- *phantom fixes*: failed `phantom`-kind tests (task 10; "fixing" a
  non-defect the plan explicitly cleared).
- *invented requirements*: failed `negative`-kind tests (behavior with no
  spec or test basis, e.g. added persistence, reordered outputs, invented
  APIs).
- *over-repair*: not applicable to implementation tasks (no clean-pair
  analogue); the negative constraints cover the same ground and this mapping
  is recorded so the paper does not double-count.

Hallucinations also score at w_wrong = 3 in the expected-loss metric (v9
section 4, ratified 2026-09-21).

**Cost:** model calls and measured dollars per attempt recorded by the
runner's accounting (same provider/budget machinery as matched-repair).

## 6. Grader-spec alignment gate (mandatory, per task, before any spend)

Automated by `scripts/check_condensation_alignment.py`; the human
spec-literal review is recorded in each task's `alignment.md`:

1. `reference.py` passes ALL hidden tests and ALL public tests.
2. Every hidden test function has a `PINS` entry; every pin names a real
   constraint id from spec.md.
3. Every constraint id has >= 1 pinning hidden test (no untested requirements).
4. `trap.py` (the attractive wrong implementation) PASSES all public tests and
   FAILS at least one hidden test — proving the trap is genuinely available:
   public tests do not catch it, hidden tests do. A trap the public tests
   catch is decoration, not a trap.
5. spec.md parses under the strict constraint format; `task.yaml` ids match
   spec.md ids exactly.
6. Human spec-literal review (recorded in `alignment.md`): every hidden test
   follows from the written spec with no extra inference; public tests do not
   exercise subtle/negative/phantom constraints; the plan.md resolves every
   ambiguity the spec names, and no hidden test depends on an ambiguity the
   plan does not resolve. (This is the v8-contradiction check.)

A task failing any check is reworked or dropped; the failure and reason are
preserved (section 8), never silently fixed.

## 7. Offline verification in this build

- `tests/test_condensation.py`: summarizer determinism + budgets + id
  coverage for all 10 tasks; task schema validity; every reference passes its
  hidden and public tests; every trap passes public and fails hidden;
  alignment-gate script passes on all 10 tasks.
- `scripts/check_condensation_alignment.py` is the same gate that runs before
  any paid campaign (no separate "test version" of the gate).
- The freeze manifest (`manifests/freeze-condensation-v1.json`) is built
  offline with `budget_authorization: PENDING` — no paid campaign is
  authorized by this build. The host RUN gate still requires Tristen's typed
  RUN per phase before any spend.

## 8. Null/negative record

- Tasks that fail the alignment gate during construction are listed here with
  reasons (this section is append-only).
- 2026-09-21 `ratelimit`: the first hidden test intended to expose
  fractional-token truncation did not trigger the trap (it advanced the fake
  clock twice without an intervening refill call), so the trap initially
  passed every hidden test and the gate correctly failed with "trap is
  decoration, not a trap". The hidden test was corrected to call `allow()`
  after the first half-second; reference still passes, trap now fails. Gate
  re-run: PASS.
- 2026-09-21 `wordwrap`: `test_c03_long_word_after_partial_line` was written
  with the wrong expected pieces (`"abcdefghij"`-style chunks for the input
  word `"cdefghij"`); the reference's output `['ab', 'cdef', 'ghij']` was
  correct per the spec and the test expectation was fixed. Gate re-run:
  PASS.
- 2026-09-21 `csvnorm`: the alignment gate's first run failed on
  `test_c04_quoted_verbatim` — the test input contained no comma, so the
  reference's unquoted-but-verbatim output did not violate the spec's C07
  minimal-quoting rule and the test could not distinguish reference from a
  sloppy implementation. The input was changed to contain a comma (quoted
  output then required); reference passes, trap fails. Gate re-run: PASS.
- 2026-09-21 summarizer budgets: the deterministic summarizer's first full
  offline run failed 30/84 checks because all ten light summaries exceeded
  the 50% spec-word budget (specs were authored with long lead sentences).
  All ten specs were rewritten so each constraint's first detail sentence is
  a terse complete requirement (rationale/examples moved to later
  sentences), titles were shortened to 2-4 words, and the activity line was
  shortened; behavior pinned by hidden tests was not changed. Re-run: all
  light and aggressive summaries within budget. No spec change altered any
  hidden-test outcome.
- Pilot validation with a real model (do the traps actually trap a frontier
  model? does the summary arm actually degrade?) is still required before the
  paid campaign and is a pre-spend gate, not part of this build.

## 9. Cost estimate for the paid campaign

Per task: 1 shared phase-1 attempt (<= 4 calls) + 6 phase-2 attempts
(<= 8 calls each) = <= 52 calls. 10 tasks: <= 520 calls, 70 attempts.
Priced two ways (gpt-6-astra, $10/$1/$50 per MTok standard):
- At the measured v8.1 rate (~$0.037/call): ~$19.
- Worst-case reservation bound ($0.9626/call at full 32768+4096 ceilings):
  ~$500 — not the expected spend; the $25/attempt and $100/global caps and
  the RUN gate bind first, and spend settles to measured usage.
Expected: ~$19-25, within the $70.05 remaining under the $100 global cap
($29.95 measured through v8.1). Priced in detail in the build report.

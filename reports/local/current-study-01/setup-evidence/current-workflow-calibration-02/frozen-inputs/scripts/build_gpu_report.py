"""Build descriptive tables directly from audited primary and repair artifacts."""
import collections
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/local/gpu-20260917'
def read(path):
    return json.loads((OUT/path).read_text(encoding='utf-8-sig'))
def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                    ['| '+' | '.join(str(x) for x in row)+' |' for row in rows])+'\n\n'
def num(value):
    return 'undefined' if value is None else f'{value:,.2f}'
labels={'baseline':'Baseline','spec_kit_adapted':'Spec Kit (adapted)','spec_kit_aee_adapted':'Spec Kit + AEE (adapted)'}
primary=read(Path('coding/coding-summary.json'))
repairs=read(Path('repair/summary.json'))
results=read(Path('coding/results.json'))
repair_rows=read(Path('repair/results.json'))
runtime=read(Path('runtime-final/runtime-summary.json'))
samples=read(Path('runtime-final/runtime.json'))['samples']
assert len(samples)==64 and sum(not x['warmup'] for x in samples)==56
for item in runtime:
    selected=[r for r in samples if r['kind']==item['kind'] and r['size']==item['size']]
    assert len({r['output_sha256'] for r in selected})==1
    measured=sorted(r['milliseconds'] for r in selected if not r['warmup'])
    assert len(measured)==7 and measured[3]==item['median_ms']

text='''# Measured GPU exploration and repair supplement — 2026-09-17

**Observed result:** the document-adapted workflows used substantially more tokens
and had fewer passing primary solutions in this six-task sample. After a shared
repair policy all arms passed 5/6 of the now feedback-exposed upstream test suites.
No superiority, token saving, or full Spec Kit integration claim is supported.

Six public Exercism tasks, one attempt/task/arm: 18 primary attempts, not 18 tasks.
Qwen2.5-Coder-14B-Instruct Q4_K_M, llama.cpp b11026, both NVIDIA GPUs, zero paid model
API calls. The planned 20 x 3 x 3 SWE-bench pilot remains unrun.

## Primary token economics

Correct answer means a final submitted module passing every unchanged upstream test
with expected test discovery and no skips. Tokens include every phase and failed
attempt. Tokens per correct answer = all-attempt input + output / passing solutions
(with parentheses around the summed numerator). Input and output are also shown
separately; they have different computational costs and are not dollar-equivalent.

'''
text+=table(['Arm','Passes / attempts','Calls','Input tokens','Output tokens','Total tokens','Tokens / correct'],
 [[labels[x['arm']],f"{x['passed']}/6",x['calls'],f"{x['input_tokens']:,}",f"{x['output_tokens']:,}",f"{x['total_tokens']:,}",num(x['total_tokens_per_correct_answer'])] for x in primary])
text+='All native usage was known; cached input tokens were zero. No failed work is excluded.\n\n'
text+=table(['Arm','Workflow seconds','HTTP seconds','Median attempt seconds','Workflow seconds / correct','Tokens on failed attempts','Truncated calls'],
 [[labels[x['arm']],num(x['seconds']),num(x['model_seconds']),num(x['median_attempt_seconds']),num(x['seconds_per_correct_answer']),f"{x['tokens_on_failed_attempts']:,}",x['truncated_calls']] for x in primary])
text+='''Workflow time includes model HTTP calls, assessments and bookkeeping; it excludes
model startup, development smoke, primary grading and setup. HTTP time is not GPU
kernel time. The seven truncations happened at the frozen 512-token document cap;
they are workflow/cap failures, not seven demonstrated coding-ability failures.
The 11 normally generated final modules had three failing test suites: Hamming
in baseline and combined arms (missing error-message period), and resistor-color
in the adapted Spec Kit arm (colors() referred to a function-local color_map).
No successful final module contains grader-output spoofing or process manipulation.

## Supplemental actual repair loops

The user requested this study after primary results existed. Its own policy was
frozen before repair generation: same model, up to two ordinary repair calls per
failed case, same failure-feedback prompt for all arms, no reruns of passing cases.
These are **same-test feedback outcomes**, not independent held-out repair scores.

'''
text+=table(['Arm','Eligible failures','Repair calls','Newly fixed (round 1 / 2)','Final passes','Repair input / output','Cumulative tokens','Cumulative tokens / correct'],
 [[labels[x['arm']],x['eligible_cases'],x['repair_calls'],f"{x['fixed_in_round_1']} / {x['fixed_in_round_2']}",f"{x['final_passed']}/6",f"{x['repair_input_tokens']:,} / {x['repair_output_tokens']:,}",f"{x['cumulative_total_tokens']:,}",num(x['cumulative_tokens_per_correct_answer'])] for x in repairs])
text+=table(['Arm','Repair seconds including grading','Repair HTTP seconds','Repair grading seconds','Repair tokens / newly fixed case','Changed code submissions'],
 [[labels[x['arm']],num(x['repair_seconds_including_grading']),num(x['model_seconds']),num(x['grading_seconds']),num(x['repair_tokens_per_repaired_case']),x['changed_code_submissions']] for x in repairs])
text+='''Seven cases were fixed on their first repair; no second-round repair fixed another
case. All three remaining failures were Hamming. The model kept producing the error
message without the final period despite explicit test diffs. Six unsuccessful
Hamming repair calls remain counted. Generation-cap failures received an ordinary
implementation request with empty submitted code; that is recovery from a failed
workflow, not evidence that AEE repaired code. Repair stages did not rerun AEE or
Spec Kit documents. Their results cannot establish an AEE-specific repair advantage.

## Scheduled revision versus actual rework

The original adapted workflows include a convergence review and final implementation
pass. Secondary grading of normally completed initial implementations occurred after
all primary generation; it supplied no feedback to the primary model calls.

'''
text+=table(['Arm','Initial/solve + final implementation calls','Completed convergence reviews','Scheduled final passes','Comparable initial/final code pairs','Text / AST changes','Primary initial-to-final grades'],
 [[labels[x['arm']],x['rework']['implementation_calls'],x['rework']['convergence_reviews'],x['rework']['scheduled_revision_calls'],x['rework']['comparable_code_pairs'],f"{x['rework']['text_changed']} / {x['rework']['ast_changed']}",json.dumps(x['rework']['transitions'])] for x in primary])
text+='''All five completed initial/final pairs were unchanged. Scheduled reviews therefore
produced zero observed code fixes in this sample. They must not be described as
successful repair loops. Actual test-feedback loops are the separately counted
13 supplemental calls above. Primary infrastructure retries and AEE recovery loops
were zero. Eleven installed AEE/Evaluator assessments returned gather_evidence;
each examined a controller-written generic unverified claim, not extracted code
claims. This demonstrates evidence-gap processing, not defect detection.

## Per-task paired outcomes

'''
pair_rows=[]
for task in sorted({r['task'] for r in results}):
    for arm in labels:
        r=next(r for r in results if r['task']==task and r['arm']==arm)
        s=next(s for s in repair_rows if s['path']==r['path'])
        total=sum(c['usage']['prompt_tokens']+c['usage']['completion_tokens'] for c in r['calls'])
        pair_rows.append([task,labels[arm],'pass' if r['grade']['passed'] else ('truncated' if r['error'] else 'test failure'),total,
                          r['grade'].get('test_count') or 'not run',len(s['rounds']),'pass' if s['final_passed'] else 'fail'])
text+=table(['Task','Arm','Primary','Primary tokens','Primary tests run','Repair calls','After repair'],pair_rows)
text+='## Phase token and latency accounting\n\n'
phase_rows=[]
for item in primary:
    for phase,p in item['phase_totals'].items():
        phase_rows.append([labels[item['arm']],phase,p['calls'],p['input_tokens'],p['output_tokens'],num(p['seconds']),p['truncations']])
text+=table(['Arm','Phase','Calls','Input','Output','HTTP seconds','Truncations'],phase_rows)
text+='## Native runtime throughput\n\nWeighted rates sum native tokens and divide by summed native phase time.\n\n'
text+=table(['Arm','Prompt tokens/s','Decode tokens/s'],[[labels[x['arm']],num(x['native_runtime']['prompt_tokens_per_second']),num(x['native_runtime']['decode_tokens_per_second'])] for x in primary])
text+='''Process launch to health-ready was 3.695 seconds, including runtime initialization.
This is not a measured cold disk/cache load. The excluded hello development call
used 44 input + 13 output tokens and 0.860 seconds HTTP time; its one Docker test
passed. Deliberately wrong-code and zero-test grading checks both failed as required.

## Deterministic application and AEE runtime

One warmup and seven measured repetitions per case; seed-shuffled measured order.
No concurrent model inference. Input construction excluded. Pipeline includes
subprocess startup, Evaluator composition and evidence I/O. CLI includes startup,
file I/O and atomic output. All substantive output hashes matched within each case.

'''
text+=table(['Workload','Size','Median ms','Min ms','Max ms','Measured repetitions'],
 [[x['kind'],x['size'],num(x['median_ms']),num(x['min_ms']),num(x['max_ms']),x['repetitions']] for x in runtime])
text+='''The earlier local `runtime/` series is preliminary and excluded; the interrupted
laptop warmups are also not results. Desktop background apps remained running;
a short controller AEE assessment operation overlapped part of the runtime series.
This host-load interference and wide CLI range limit precision. The data is not an
isolated performance laboratory result or a CPU/GPU speedup comparison. AEE/triage
workloads are CPU/Python measurements; the GPUs accelerate the coding model.

## Hardware, spending and scope

Observed i9-14900F (24 cores / 32 threads), 64 GB RAM, Windows 11 Pro for Workstations,
driver 610.88. nvidia-smi: 4070 SUPER 12282 MiB; 5060 Ti 16311 MiB. User's hardware
report: Gen4 x16 and x4 respectively. Explicit 10:14 layer split; 16384 context,
one slot, temperature zero, seed 20260917. Shared system memory is not counted as
VRAM. Post-smoke usage was about 6523/6927 MiB; sampled load is retained in CSV.
Server properties matched before primary generation and after repairs. The original
Qwen3.6 service was restored and its model reported loaded after the experiment.

Benchmark model API expenditure: **USD 0**. Local electricity, hardware depreciation,
downloads, controller development and human/setup time are unpriced, not zero.
There were 60 primary + 13 repair + 1 development model calls, all to the dedicated
localhost server. Primary + repair tokens total 257984; excluded development adds
57 tokens. No paid OpenAI provider or credit-consuming benchmark endpoint was used.

Limitations: six convenience tasks; public contamination; one quantized model;
no repeats; document-only Spec Kit; no solver shell/repository tools; unequal
phase counts; restrictive document caps; generic AEE claims; no component-isolated
AEE effect; test-feedback exposure in repairs; controller-authored harness; and
no external replication. AST filtering can reject valid programs, although no
observed final grade here failed that filter. Timeout checks are between operations
and HTTP timeouts are socket timeouts; no independent whole-operation watchdog.
No observed request/attempt exceeded its limit. Grader output parsing is not
hardened against adversarial spoofing; reviewed submitted modules did not do so.

Expanded economics/revision analysis was requested during generation, but its
written-plan hash was captured after primary results existed. The initial text
and corrected plan remain on record. Repair policy was separately frozen before
repair outputs. Controller development did not strictly follow every Spec Kit
setup command in sequence; this deviation is explicit in the protocol.

ElectroHire maintains the evaluated AEE/Evaluator projects. This is a conflict of
interest. Treat these artifacts as inspectable local evidence, not a marketing
proof or a claim that full Spec Kit worsens coding.

## Evidence and reproduction

- [Primary summary](coding/coding-summary.json), [per-attempt grades and rework](coding/results.json), [sanitized freeze](coding/freeze-sanitized.json), [audit](coding/audit.json).
- [Repair summary](repair/summary.json), [all repair rounds](repair/results.json), [repair freeze](repair/freeze.json), [audit](repair/audit.json).
- [Runtime samples](runtime-final/runtime.json), [summary](runtime-final/runtime-summary.json), [runtime freeze](runtime-final/freeze.json).
- [Primary protocol](../../../docs/gpu-experiment-protocol.md), [repair protocol](../../../docs/gpu-repair-protocol.md), [reproduction](../../../docs/gpu-reproduction.md).
- [Regression test output](tests-final.txt): 49 passed; original 41-test checks are retained under reports/offline.
- [Spec Kit](https://github.com/github/spec-kit), [AEE extension](https://github.com/electrohire/spec-kit-aee), [Evaluator](https://github.com/electrohire/spec-kit-evaluator), [AEE engine](https://github.com/electrohire/applied-epistemic-engineering).
- [Model revision](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF/tree/d0a692ef765eefbf2fabb130b3cb2e8917e3d225), [runtime release](https://github.com/ggml-org/llama.cpp/releases/tag/b11026), [Exercism source](https://github.com/exercism/python/tree/1f6aab8667bf653b10cc3799f94352fcdb749db6), [canonical problem specifications](https://github.com/exercism/problem-specifications).

Operational failures preserved: original laptop interruption; initial GPU-host
uv/shared-temp permission errors (a test invocation had 19 passes/29 setup errors);
successful retry used a project-local environment/temp directory. No model attempt
was rerun to hide these setup issues. Seven primary truncations, three primary test
failures and six failed repair calls are all visible in the evidence.
'''
(OUT/'README.md').write_text(text,encoding='utf-8',newline='\n')
with (OUT/'comparison.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['arm','primary_passed','attempts','primary_input_tokens','primary_output_tokens','primary_tokens_per_correct','repair_calls','final_passed','cumulative_tokens','cumulative_tokens_per_correct'])
    for p,s in zip(primary,repairs):
        assert p['arm']==s['arm']
        writer.writerow([p['arm'],p['passed'],6,p['input_tokens'],p['output_tokens'],p['total_tokens_per_correct_answer'],s['repair_calls'],s['final_passed'],s['cumulative_total_tokens'],s['cumulative_tokens_per_correct_answer']])
print('Built measured report and comparison.csv')

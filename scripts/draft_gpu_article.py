"""Render copy/paste article numbers directly from the audited local reports."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('results_commit')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
report=root/'reports/local/long-horizon-03'
summary=json.loads((report/'summary.json').read_text())
setup=json.loads((report/'setup-accounting.json').read_text())
url='https://github.com/electrohire/spec-kit-aee-benchmark/tree/'+args.results_commit
labels={'baseline':'Ordinary coding agent','spec_kit':'Spec Kit through our adapter','spec_kit_aee':'Spec Kit + Evaluator + AEE through our adapter'}
rows=[]
for arm in ('baseline','spec_kit','spec_kit_aee'):
    s=summary['arms'][arm]
    ratio=f"{s['tokens_per_accepted_milestone']:,.0f}" if s['tokens_per_accepted_milestone'] is not None else 'undefined (no fully accepted milestones)'
    rows.append(f"{labels[arm]}: {s['hidden_primary_passes']}/3 milestones passed before public-feedback repairs; {s['hidden_final_passes']}/3 afterward. {s['total_tokens']:,} total tokens, {s['repair_rounds']} repair rounds, {ratio} tokens per accepted milestone.")

article=f'''Try Spec Kit + AEE on work that changes—and measure the rework

The AI coding task I care about is the one that comes back next week with a new requirement.

Can the agent preserve the behavior we already agreed on? Can it distinguish a test it actually ran from a confident claim? And how many tokens and repair attempts does it take to get to a correct result?

That is why I think Spec Kit + Applied Epistemic Engineering is worth trying on a bounded project. Spec Kit provides an explicit specification, plan and task workflow. AEE adds a way to challenge claims, retain uncertainty and link evidence. Those are useful capabilities to evaluate. They are not a promise of cheaper or more accurate code.

I put that proposition through a free-local experiment. The results and failures are public.

What ran

The machine had an i9-14900F, 64 GB RAM, an RTX 4070 SUPER with 12,282 MiB dedicated VRAM and an RTX 5060 Ti with 16,311 MiB. I verified the hardware and explicitly split inference across the GPUs. Shared system memory was not counted as VRAM.

All benchmark model calls went to localhost through llama.cpp. API expenditure was $0. Hardware, electricity and setup work were not priced, so I am not calling the experiment cost-free.

The first exploration used six small Exercism tasks and Qwen2.5-Coder-14B. Before repairs, ordinary coding passed 5/6, the document-adapted Spec Kit arm 2/6, and the adapted combined arm 1/6. Seven workflow responses hit their document token limit. After shared repair loops, all three arms passed 5/6 of the feedback-exposed test suites.

Their cumulative tokens per passing answer were 957, 23,524 and 27,116, respectively. That sample does not show a token-saving advantage. All three remaining failures involved the same required punctuation in an error message, despite repair feedback. The workflow adaptation and low document cap limit what this says about full Spec Kit.

A better question than six small functions

The second workload used the actual TinyDB repository and three cumulative changes: transactions, nested savepoints, then backup/restore. Earlier requirements remained active. The tests checked details such as rollback, retained table handles, stale caches, ID allocation, validation before mutation and persistence after reopening.

Each arm had repository tools, could write its own tests and kept its code across stages. The baseline could plan and keep notes. All arms used the same local Qwen3.6-35B-A3B quantization, context policy and resource allocations. Public-feedback repair capacity was reserved separately from primary work. Hidden tests were withheld until every arm finished.

{chr(10).join(rows)}

“Accepted milestone” means every required hidden acceptance and unchanged upstream regression test passed. The three milestones are dependent checkpoints in one project, not three independent tasks. The hidden tests were written by this study; the upstream regression tests were independently authored. Neither internal AEE outcomes nor a model saying “done” counted as a correctness grade.

The economics include input, output and reasoning usage for every phase and failed attempt. Reasoning tokens already included in native completion usage were not counted twice. Repairs and tokens spent on failures stay in the numerator. With zero accepted milestones, tokens per accepted milestone are undefined, not zero.

The setup failures matter too

Two initial staged pilots were interrupted after repeated file-reading loops and failed implementation. I retained their 285 calls and 5,266,572 tokens, then corrected the adapter through separate development smokes. Those checks exposed directory-layout assumptions, unchanged documents behind “done” responses, and a lost phase-transition message. The final pilot uses the larger 131,072-token context supported by the same GPUs, full conversation and model-reasoning retention, and within-arm prompt caching. It had a new freeze and a full-workflow preflight. No hidden-test result guided those fixes.

Across the staged study’s development smokes and interrupted runs, setup overhead was {setup['setup_plus_aborted_tokens']:,} tokens, separate from the completed comparison. This was iterative harness development, not a pristine experiment that worked on its first try. The full revision history is part of the evidence.

Runtime overhead was measured separately from coding inference. For seven measured repetitions after warmup, the installed AEE + Evaluator pipeline had a median of about 661.5 ms for 10 claims and 800.0 ms for 100 claims. These are specific local workloads with ordinary desktop background activity, not universal latency promises.

What I would invite you to try

Pick a project with requirements that must survive a later change. Write the acceptance criteria before generation. Run a capable ordinary-agent baseline alongside Spec Kit, then add AEE. Keep primary results separate from feedback-assisted repairs. Count every phase, every retry and every failed answer.

Look for a practical benefit: an unsupported assumption made visible, a requirement preserved through a change, or a repair avoided. Then check whether that benefit is worth the extra tokens and time. The evidence record is useful precisely when it prevents an attractive story from outrunning the measurements.

This study does not establish general superiority, production reliability or savings. It uses one project trajectory per arm, limited context and budgets, a quantized local model and an adapted autonomous workflow. The original 180-attempt SWE-bench pilot remains unrun. The small-task and staged studies used different models and are not a controlled model comparison.

Disclosure: ElectroHire maintains AEE, the Evaluator extension and this benchmark. Treat this as a reproducible maintainer experiment that needs independent replication.

Try it, inspect the failures, and measure whether it helps your own work.

Results and exact protocol: {url}/reports/local/long-horizon-03
Earlier small-task results and repairs: {url}/reports/local/gpu-20260917
Interrupted staged runs: {url}/reports/local/long-horizon-01-interrupted and {url}/reports/local/long-horizon-02-interrupted
Spec Kit: https://github.com/github/spec-kit
Spec Kit AEE extension: https://github.com/electrohire/spec-kit-aee
Evaluator extension: https://github.com/electrohire/spec-kit-evaluator
AEE engine: https://github.com/electrohire/applied-epistemic-engineering
Benchmark repository and reproduction: https://github.com/electrohire/spec-kit-aee-benchmark
TinyDB source: https://github.com/msiemens/tinydb/tree/19066e03139e904c24410e23901e4b069d715a2e
Exercism source: https://github.com/exercism/python/tree/1f6aab8667bf653b10cc3799f94352fcdb749db6
mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent
llama.cpp runtime: https://github.com/ggml-org/llama.cpp/releases/tag/b11026
Qwen3.6 model: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
Measured quantization: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/a483e9e6cbd595906af30beda3187c2663a1118c
Earlier Qwen2.5 coder: https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF
'''
(root/'docs/linkedin-article.txt').write_text(article,encoding='utf-8')
(root/'docs/linkedin-article.md').write_text('# '+article,encoding='utf-8')
print('Wrote Markdown and plain-text article; not published.')

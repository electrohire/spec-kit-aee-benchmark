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
article=f'''Try Spec Kit + AEE on work that changes—and measure the rework

The coding task I care about is the one that comes back next week with a new requirement. Earlier promises still have to hold. A passing demo is only the beginning.

That is where I would invite people to try Spec Kit + Applied Epistemic Engineering: a bounded project with requirements to preserve, evidence to inspect and repair costs to measure.

Spec Kit provides a specification, plan and task workflow. AEE adds structured claims, evidence references and questions about uncertainty. My local tests did not demonstrate a correctness or token-saving advantage. They produced a public record of what worked, what failed and what needs a better test.

The rig and the rules

I verified an i9-14900F, 64 GB RAM, an RTX 4070 SUPER with 12,282 MiB dedicated VRAM and an RTX 5060 Ti with 16,311 MiB. Shared system memory was not counted as VRAM.

All benchmark inference used localhost through llama.cpp. The longer study split Qwen3.6-35B-A3B across both GPUs with a 131,072-token context. API expenditure was $0. Hardware, electricity and controller work were unpriced.

Three arms received the same model configuration, repository tools and resource limits: an ordinary coding agent, Spec Kit through our adapter, and Spec Kit + Evaluator + AEE through that adapter. The baseline could plan, keep notes and write tests.

Start with the small result

The first exploration used six Exercism tasks and Qwen2.5-Coder-14B. Before repairs, baseline passed 5/6, Spec Kit using document prompts 2/6, and the adapted combined arm 1/6. Seven workflow responses hit their document token limit.

Actual supplemental repair loops brought all three arms to 5/6. Their cumulative tokens per passing answer were 957, 23,524 and 27,116, respectively. Seven initially failing submissions were fixed; the three remaining failures concerned required punctuation in an error message, despite feedback.

Those repair tests were already exposed to the agents. The small sample and document-only adaptation cannot establish full Spec Kit effectiveness, and the result provides no token-saving claim.

A longer test: requirements that must survive change

The second workload used the real TinyDB repository and three cumulative milestones: transactions, nested savepoints, then backup and restore. Each arm kept its code and history across stages. Later changes had to preserve earlier guarantees about rollback, caches, retained table handles, document IDs and persistence.

Public tests were available during development. Separate hidden cases were withheld until all generation ended. A fully accepted milestone required every hidden acceptance case and all 223 unchanged upstream tests to pass.

No arm passed a complete hidden milestone, before or after the scheduled repair attempts. Recorded logical token totals were:

{chr(10).join(f"- {labels[arm]}: at least {summary['arms'][arm]['known_total_tokens']:,} tokens." for arm in ('baseline','spec_kit','spec_kit_aee'))}

Each arm had one call with unknown native usage. Tokens per accepted milestone are undefined because there were no fully accepted milestones; exact usage is also incomplete. Unknown is not zero.

Final-stage hidden feature coverage was 21/24 for baseline, 5/24 for Spec Kit and 3/24 for the combined arm. Every snapshot passed the 223 upstream tests, but every arm missed retained-handle/cache and document-ID rollback cases. Related and parameterized cases are not independent answers, so these counts should not become a broad accuracy percentage.

All three arms hit the 120-second request timeout: baseline and Spec Kit in milestone three, the combined arm in milestone one. Baseline's saved source passed its public tests despite its interrupted workflow. Source correctness and workflow completion are separate facts.

The frozen unknown-usage rule stopped further inference in an affected arm. Six reserved repair attempts were therefore blocked before a model call. The actual repair successes belong to the earlier six-task study; the longer run does not establish how effective its repair loops would have been.

What AEE actually contributed

The combined arm completed three planning assessments, all returning iterate, with no assessment-adapter errors. It stopped before implementation assessment, evidence rework or convergence. Planning findings were advisory in this adapted workflow, not a final-code certificate.

It did produce explicit records of claims, evidence references and unresolved gaps. One assessment flagged a possible contradiction between one write on successful commit and zero writes on rollback. Those are different exit conditions, so the flag was a review prompt, not proof of a bug. Structured evidence still needs interpretation.

That is a concrete artifact worth inspecting in a trial. This run does not show that it improved the code or paid for its extra work. Our adapter also forwards full assessment JSON; its token overhead is not a minimum cost inherent to AEE.

Count the work that failed

Two earlier staged pilots were interrupted after integration problems and failed implementation. Their 285 calls and 5,266,572 tokens remain published. Development smokes exposed directory assumptions, unchanged documents behind “done” responses, phase-handoff problems and invalid claim types. The final run had a new freeze and a passing preflight covering every workflow phase. No TinyDB hidden-test result guided those revisions.

The staged study's smokes and interrupted pilots used {setup['setup_plus_aborted_tokens']:,} tokens, separate from the scored arms. Across both studies and all retained development work, the ledger contains 1,001 model calls and at least 33,983,869 tokens, with three unknown usages. That is a work inventory across different models and tasks, not a pooled efficiency estimate.

Cached input remains in logical token totals and is reported separately from uncached input. Native completion already includes reasoning, so it is not added twice. Failures stay in the cost numerator.

Runtime was measured too. Completed calls in the longer study had native weighted decoding rates of 61.5–63.8 tokens/second across arms. Long prompt processing still constrained the workflow: one recorded call spent about 66 seconds processing its prompt before decoding. These are specific measurements on this rig, not universal speed promises.

Separately, seven measured repetitions after warmup gave the CPU-side AEE + Evaluator pipeline a median of about 661.5 ms for 10 claims and 800.0 ms for 100 claims. The report retains the desktop-activity and timing limitations.

Try it as an engineering experiment

Choose work with requirements that must survive a later change. Write acceptance criteria before generation. Run a capable ordinary-agent baseline alongside Spec Kit, then add AEE. Keep initial results separate from repairs using test feedback. Count planning, implementation, retries and failures.

Look for a requirement preserved, an unsupported assumption made visible or a repair avoided. Check whether that benefit justifies the extra tokens and time. Publish the result even when the hoped-for advantage does not appear.

This was one project trajectory per arm, with dependent milestones, tests written for this study, a quantized local model, fixed limits and an adapted workflow that did not complete successfully in every arm. It is not full Spec Kit validation or evidence of general superiority. The original 180-attempt SWE-bench pilot remains unrun. Public traces retain responses, usage, tools and hashes; full requests and native reasoning remain local, so exact prompt replay is unavailable from the public record.

Disclosure: ElectroHire maintains AEE, the Evaluator extension and this benchmark. Independent replication is needed.

Try Spec Kit + AEE where evidence and changing requirements matter. Measure whether it helps your work, and keep the failures visible.

Results and exact protocol: {url}/reports/local/long-horizon-03
Complete work ledger: {url}/reports/local
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

"""No generation: compare native linear/binary context selection on saved traces."""
import hashlib
import json
import time
from pathlib import Path

from benchmark_runner.store import canonical, write_json
from context_window import select_context
from gpu_experiment import local_json, digest

root=Path(__file__).resolve().parents[1]
out=root/'artifacts/context-selection-01'
out.mkdir(exist_ok=False)
sources=[root/'artifacts/repeated-study-01/cachetools-20260919-spec_kit_aee'/f'call-{i:04}.json' for i in (50,120,170,290)]
rows=[]
for source in sources:
    original=json.loads(source.read_text())['request']['messages']
    messages=original[:2]+original[2:]*3
    counters={'requests':0}
    def measure(chosen):
        counters['requests']+=1
        prompt=local_json('/apply-template',dict(messages=chosen,chat_template_kwargs={'enable_thinking':True}))['prompt']
        counters['requests']+=1
        return len(local_json('/tokenize',dict(content=prompt,add_special=False))['tokens'])
    begin=time.monotonic();linear=[dict(m) for m in messages];counts=[]
    while True:
        count=measure(linear);counts.append(count)
        if count+4096<=32768:break
        assert len(linear)>3
        del linear[2:4]
    assert all(a>=b for a,b in zip(counts,counts[1:])), 'Pinned template violated monotonicity'
    linear_seconds=time.monotonic()-begin;linear_requests=counters['requests']
    counters['requests']=0;begin=time.monotonic()
    selected,tokens,removed=select_context(messages,measure,32768,4096)
    binary_seconds=time.monotonic()-begin
    assert selected==linear and tokens==count
    row=dict(source=str(source.relative_to(root)),source_sha256=digest(source),fixture_sha256=hashlib.sha256(canonical(messages)).hexdigest(),
        messages=len(messages),removed_messages=removed,selected_sha256=hashlib.sha256(canonical(selected)).hexdigest(),input_tokens=tokens,
        linear_http_requests=linear_requests,binary_http_requests=counters['requests'],linear_seconds=linear_seconds,binary_seconds=binary_seconds,
        identical_selection=True,observed_monotone_counts=counts)
    rows.append(row);write_json(out/'result.json',dict(passed=False,cases=rows))
    print(json.dumps({k:row[k] for k in ('source','linear_http_requests','binary_http_requests','linear_seconds','binary_seconds','identical_selection')}),flush=True)
write_json(out/'result.json',dict(passed=True,selector_sha256=digest(root/'scripts/context_window.py'),cases=rows,
    inference_calls=0,note='CPU template/tokenization probes only; full request fixtures remain local with hashes. This verifies saved representative cases under the pinned Qwen template, not every possible model/template. Model settings, first-fitting cutoff semantics, phases, budgets and graders are unchanged.'))

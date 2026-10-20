"""Export independently audited recovery findings, never model work or grading."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from benchmark_runner.markdown_presentation import write_markdown

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('baseline', 'spec_kit', 'spec_kit_aee')
NAMES = dict(baseline='Baseline', spec_kit='Spec Kit', spec_kit_aee='Spec Kit + AEE')


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def load(p): return json.loads(Path(p).read_text())


def validate_grade(g):
    if (g.get('complete_amended_schedule') is not True or g.get('original03_complete') is not False
        or g.get('graded') != 720 or g.get('ungraded') != 0 or len(g.get('rows', [])) != 720
        or len({(r['index'],r['arm']) for r in g['rows']}) != 720
        or Counter(r['arm'] for r in g['rows']) != Counter({a:240 for a in ARMS})
        or g['recovery_accounting']['calls'] != 18 or g['recovery_accounting']['usage_unknown'] != 0
        or g['original_accounting']['physical_requests'] != 1463 or g['original_accounting']['usage_unknown'] != 1
        or g['original_worker_complete_case_sensitivity']['graded'] != 693):
        raise ValueError('not the completed independently audited amended schedule')
    for ds in ('halueval_qa','ragtruth_test'):
        for arm in ARMS:
            rows=[r for r in g['rows'] if r['dataset']==ds and r['arm']==arm]
            m=g['metrics'][ds][arm]
            if len(rows)!=120 or sum(r['prediction']==r['gold'] for r in rows)/120!=m['accuracy_all']:
                raise ValueError('published metric differs from independently labelled rows')


def costs(g):
    original=g['original_integrity']['accounting']; result={}
    for arm in ARMS:
        c=Counter(original['setup/'+arm]);c.update(original['scored/'+arm]);c.update(g['recovery_accounting_by_arm'][arm])
        result[arm]=dict(c)
    return result


def compact_table(g):
    validate_grade(g)
    text='| Author-labelled response classification | Baseline | Spec Kit | Spec Kit + AEE |\n| --- | ---: | ---: | ---: |\n'
    for ds,label in (('halueval_qa','HaluEval'),('ragtruth_test','RAGTruth')):
        text+='| '+label+' accuracy (120 each; abstentions count as incorrect) | '+' | '.join(f"{g['metrics'][ds][a]['accuracy_all']:.1%}" for a in ARMS)+' |\n'
    return text


def report_text(g, arm_costs):
    text='# Matched hallucination classification: completed amended schedule\n\n'
    text+='**No consistent material AEE advantage is established.** Spec Kit + AEE is higher on HaluEval and lower on RAGTruth; all paired accuracy-difference intervals include zero. This is a response-detection experiment, separate from coding correctness, spontaneous hallucination prevalence and long-horizon payback.\n\n'
    text+=compact_table(g)+'\n'
    text+='Original03 stopped after 711 judgments when its worker crashed. The user explicitly authorized restoring the existing profile and completing only the nine missing cells in a separately frozen episode04. All 720 scheduled cells are now graded, with zero invalid or ungraded final judgments. Original03 remains stopped and immutable; this is an amended two-epoch comparison, not an uninterrupted run or independent replication.\n\n'
    text+='```mermaid\nflowchart LR\n    F[Frozen cases, original author labels and policies] --> O[Original worker: 711 judgments]\n    O --> C[Worker crash: retain failed request and orphan draft]\n    C --> R[Authorized restored worker: only nine missing cells]\n    O --> A[Independent 720-row grade]\n    R --> A\n    A --> S[Same-original-worker sensitivity: 693 rows]\n    A --> Q[Raw accuracy and confusion counts]\n    A --> G[Separate AEE gate eligibility]\n    C --> T[All-call costs and unknown usage]\n    R --> T\n```\n\n'
    text+='## Factual reliability and uncertainty\n\n| Dataset | Arm | Correct / 120 | Missed hallucinations | False alarms | Abstentions | Precision | Recall over all positives |\n| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |\n'
    for ds,label in (('halueval_qa','HaluEval'),('ragtruth_test','RAGTruth')):
        for arm in ARMS:
            m=g['metrics'][ds][arm]
            text+=f"| {label} | {NAMES[arm]} | {m['tp']+m['tn']} | {m['false_acceptances']} | {m['false_alarms']} | {m['abstentions']} | {m['precision']:.1%} | {m['recall_all_positives']:.1%} |\n"
    text+='\nA missed hallucination is an author-labelled hallucinated response called grounded; a false alarm is an author-labelled grounded response called hallucinated. Abstention is separate from either error and remains in the accuracy/recall denominator. Each dataset has 60 positive and 60 negative responses per arm; these balanced subsets do not estimate deployment prevalence. HaluEval uses 60 paired question clusters and RAGTruth 120 source clusters.\n\n'
    text+='| Dataset | Right minus left | Accuracy difference | Conditional cluster-bootstrap 95% interval |\n| --- | --- | ---: | ---: |\n'
    for ds,label in (('halueval_qa','HaluEval'),('ragtruth_test','RAGTruth')):
        for key,m in g['paired'][ds].items():
            left,right=key.split('_vs_');lo,hi=m['cluster_bootstrap_95']
            text+=f"| {label} | {NAMES[right]} minus {NAMES[left]} | {100*m['accuracy_difference_right_minus_left']:+.2f} pp | [{100*lo:+.2f}, {100*hi:+.2f}] pp |\n"
    text+='\nIntervals use 2,000 seeded question/source-cluster resamples and are conditional on one generated policy per dataset/arm and one seed. Crossing zero does not establish equivalence or prove a difference is harmless noise. The same-original-worker sensitivity excludes all nine affected case indices symmetrically across every arm: 231 cases / 693 rows, HaluEval 114 responses per arm and RAGTruth 117. Its intervals also cross zero; exact counts and intervals are in [the independent grade](independent-grade.json).\n\n'
    text+='## AEE gate is separate from classification\n\nAll 480 scored AEE assessments returned iterate; 13 setup assessments were also independently joined to their policy/calibration artifacts and local ledgers. The 240 AEE final proposals therefore remain gate-ineligible, while their raw classifier verdicts are still graded above. Zero eligible AEE outputs must not be presented as perfect hallucination prevention or accepted delivery. Local anchored integrity is not protected identity, semantic truth or human acceptance. No judgment was promoted to human-accepted.\n\n'
    text+='## All-call token economics\n\n| Arm (policy/calibration, scored, failed and recovery calls) | Requests | Native prompt | Native output | Known native total | Usage unknown |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
    for arm in ARMS:
        c=arm_costs[arm];text+=f"| {NAMES[arm]} | {c['calls']:,} | {c['prompt_tokens']:,} | {c['completion_tokens']:,} | {c['known_native_tokens']:,} | {c['usage_unknown']} |\n"
    total=sum(c['known_native_tokens'] for c in arm_costs.values())
    text+=f'\nThe two study episodes retain 1,481 requests and at least {total:,} known native tokens, including the abandoned successful draft and failed review. Six separate native-readiness calls add 1,480 tokens: **1,487 total physical requests, at least {total+1480:,} native tokens, one request with unknown usage**. No failed request is assigned zero actual usage. Known cached tokens are zero and retained separately; cache would be an input subset, not a second charge.\n\n'
    ratio=arm_costs['spec_kit_aee']['known_native_tokens']/arm_costs['baseline']['known_native_tokens']
    relative=arm_costs['spec_kit_aee']['known_native_tokens']/arm_costs['spec_kit']['known_native_tokens']
    text+=f'The AEE arm used {ratio:.2f} times the baseline known token count and {relative:.2f} times the Spec Kit lower-bound count in this particular classifier workflow. The Spec Kit failed-request unknown makes its actual total larger than the displayed lower bound. The observed results do not establish token savings or a quality-qualified payback point. These are not coding economics; FeatureBench/SWE-EVO solver results remain pending. Local API spend 0 excludes hardware, energy and labor.\n\n'
    text+='Earlier preparations/stopped runs have additional costs, preserved in their separate reports and bounded historical inventories. This table is all-call accounting for these two matched episodes and their native readiness, not an all-history total or pooled efficiency claim. [External01](../external-01-20261019/README.md) used a different one-call/output-cap protocol and is not a treatment-control comparison for this result.\n\n'
    text+='## Integrity, recovery and limitations\n\n* Original source c72d54f4b876454ab2c11216d74959b123a72a09 and all 339 declared source/archive inputs stayed unchanged. The original 32,591-file stop inventory was independently reverified.\n* Recovery source 286f3d8348c9c07d7f9a8c0227e790528698ad9b passed exact-head Ubuntu checks and merged in [PR49](https://github.com/electrohire/spec-kit-aee-benchmark/pull/49) with protections unchanged. Only five pinned AST port/endpoint literals changed in the transport; original Provider, judge, policies, labels, budgets and sampling were reused.\n* Windows recorded Application Error 1000, ucrtbase.dll and c0000409 for the original worker. The underlying crash cause remains unresolved; no CUDA, memory or security cause is inferred. The restored profile/weights/build were verified and no other service/model configuration changed.\n* Nine whole cells were completed in original schedule order: five baseline, three Spec Kit and one AEE. Neither the 711 completed cells nor the earlier completed external/synthetic tests were rerun. Three separately registered readiness calls preceded the 18 recovery calls; no automatic retry was used.\n* Public-case exposure, single policies/seed, outcome-conditioned harness debugging, the recovery amendment, document-to-classifier adaptation and concurrent CPU validation limit generalization. Timing is descriptive. No full HaluEval/RAGTruth leaderboard or independent replication is claimed.\n* This does not validate a release baseline or candidate equivalence. Accepted delivery, coding completion proxies, regressions and observed long-horizon payback require the separately registered coding study.\n\n'
    text+='[720 independent rows, raw/gate metrics and sensitivity](independent-grade.json) · [All physical request receipts, usage and hashes](physical-calls.json) · [Frozen evidence file inventories](retained-inventories.json) · [Original stop](original-stop.json) · [Recovery registration](../../../benchmarks/hallucinations/completion-recovery-04.json).\n'
    return text


def export(root, output):
    parent=root/'work/benchmark-results-publication/artifacts/matched-hallucinations-03'
    stop=root/'validation/matched03-stop-20261020';rec=root/'validation/matched-completion-recovery-04'
    grade=load(rec/'independent-combined-grade.json');validate_grade(grade)
    if load(rec/'audit-watch-state.json')['stage']!='offline_grade_complete_pending_publication':raise ValueError('audit did not finish')
    output.mkdir(parents=True,exist_ok=False)
    for src,name in ((rec/'independent-combined-grade.json','independent-grade.json'),(stop/'stop-summary.json','original-stop.json'),
                     (rec/'scored/recovery-freeze.json','recovery-freeze.json'),(root/'validation/audit-matched-completion-recovery-04.py','offline-audit-controller.py')):
        shutil.copyfile(src,output/name)
    inventories={};receipts=[]
    episodes=[('original03',parent),('recovery04',rec/'scored'),('native03',root/'work/benchmark-results-publication/artifacts/matched-native-bounds-03'),('native04',rec/'native')]
    for episode,folder in episodes:
        inventories[episode]={p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
        for p in sorted((folder/'calls').glob('*.json')):
            c=load(p);receipts.append(dict(episode=episode,path=p.relative_to(folder).as_posix(),sha256=sha(p),metadata=c['metadata'],usage=c.get('usage'),unknown_reason=c.get('unknown_reason'),error=c.get('error'),started_at=c['started_at'],ended_at=c.get('ended_at'),request_sha256=hashlib.sha256(json.dumps(c['request'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()))
    if inventories['original03']!=load(stop/'retained-files-sha256.json'):
        raise ValueError('original retained bytes changed before export')
    if len(receipts)!=1487 or sum(not bool(x['usage']) for x in receipts)!=1:raise ValueError('all-call export inventory differs')
    for name,value in [('physical-calls.json',receipts),('retained-inventories.json',inventories),('arm-costs.json',costs(grade))]:
        (output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    write_markdown(output/'README.md',report_text(grade,costs(grade)))
    manifest={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'files-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();export(args.root.resolve(),args.output.resolve())

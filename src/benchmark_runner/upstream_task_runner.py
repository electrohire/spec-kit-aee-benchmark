"""One source-retaining upstream agent task, after external study admission.

This module does not admit studies, load models, create resources or run hidden
graders. The controller must first bind source/inputs/resources/caps/CI and the
existing worker. Failed model/tool work stops immediately; post-stop snapshots
are controller evidence capture, never additional solver inference.
"""
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import time

import yaml

from .upstream_agent_adapter import AdmissionError, Limits, NativeToolModel, ReceiptEnvironment, write_exclusive
from .upstream_docker_transport import StdinDockerBridge
from .upstream_snapshot import capture_snapshot
from .upstream_scaffold import seed
from .upstream_tree_transfer import export_tree
from .upstream_workflow_adapter import Workflow, PHASES, capture_document


CHECKPOINTS = frozenset((16, 32, 64, 128))


def _file_state(snapshot):
    return {f['path']: (f.get('mode'), f.get('sha256'))
            for f in snapshot['files'] if not f.get('deleted')}


def _test_integrity(initial_files, final_files):
    roots=set()
    protected=set()
    for path in initial_files:
        parts=path.split('/')
        if any(p in ('tests','test') for p in parts) or parts[-1]=='conftest.py':
            protected.add(path)
        for i,part in enumerate(parts[:-1]):
            if part in ('tests','test'):roots.add('/'.join(parts[:i+1])+'/')
    changed=sorted(p for p in protected if initial_files[p]!=final_files.get(p))
    added=sorted(p for p in final_files if p not in initial_files and any(p.startswith(r) for r in roots))
    return dict(modified_existing_author_test_paths=changed,added_under_author_test_directories=added,
                passing=not(changed or added),
                boundary='Declared existing author-test paths/directories only; not a complete anti-cheating or transient-immutability proof. Independent original tests remain required.')


def run_task(*, upstream, transport, environment, source_root, out, arm, public_task,
             baseline_commit, literal_baseline_tree, deadline, continuity_root=None,
             prior_context=None, execution_kind='scored', instance_id=None, study_id=None):
    """Execute one externally admitted task. Synthetic controls must be labelled.

    Whole source is retained at checkpoints, including nonignored helpers and
    framework documents; source capture does not trust the submitted patch as
    the complete workspace. Independent grading is a separate, later process.
    """
    if execution_kind not in ('scored', 'canned_adapter_control'):
        raise AdmissionError('explicit execution cohort required')
    if execution_kind == 'scored' and (not instance_id or not study_id):
        raise AdmissionError('registered study and instance identity required')
    out = Path(out)
    feature_number = 2 if prior_context is not None else 1
    out.mkdir(parents=True, exist_ok=False)
    write_exclusive(out/'task-started.json', dict(arm=arm, execution_kind=execution_kind,
        instance_id=instance_id, study_id=study_id, feature_number=feature_number,
        public_task_sha256=hashlib.sha256(public_task.encode('utf-8')).hexdigest(),
        baseline_commit=baseline_commit, literal_baseline_tree=literal_baseline_tree,
        monotonic_started=time.monotonic(), independent_grade=None))
    reader = '/opt/miniconda3/envs/testbed/bin/python'
    bridge = StdinDockerBridge(environment, reader_python=reader, deadline=deadline)
    # Controller-only reads/retention can run after generation's wall deadline.
    # The timed bridge remains the sole environment for model actions.
    capture_bridge = StdinDockerBridge(environment, reader_python=reader)
    initial = capture_snapshot(capture_bridge, out/'checkpoints/initial', baseline_commit=baseline_commit,
                              literal_baseline_tree=literal_baseline_tree, reader_python=reader)
    if initial['patch_bytes'] != 0 or initial['candidate_tree'] != literal_baseline_tree:
        raise AdmissionError('task source changed after registered initial capture')
    initial_files = _file_state(initial)
    flow = Workflow(source_root, out/'workflow', arm, public_task,
                    continuity_root=continuity_root, prior_context=prior_context,
                    feature_number=feature_number)
    setup=seed(flow,capture_bridge,out/'workflow-initialization',reader)
    # Controller setup is retained separately from the pristine upstream tree
    # and zero model calls. It must not be misattributed to solver code work.
    prepared=capture_snapshot(capture_bridge,out/'workflow-initialization/snapshot',
        baseline_commit=baseline_commit,literal_baseline_tree=literal_baseline_tree,reader_python=reader)
    initial_files=_file_state(prepared)
    package = Path(inspect.getfile(upstream.DefaultAgent)).parents[1]
    config_path = package/'config/benchmarks/swebench.yaml'
    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    write_exclusive(out/'upstream-config.json', dict(path=str(config_path),
        sha256=hashlib.sha256(config_bytes).hexdigest(),
        boundary='Original upstream templates; declared phase/system controls and observation-retention adaptation are recorded separately.'))
    # Keep complete observations available in history and immutable receipts.
    # The upstream sample YAML elides >10k characters; do not silently use it.
    observation = '<returncode>{{output.returncode}}</returncode>\n<exception>{{output.exception_info}}</exception>\n<output>{{output.output}}</output>'
    model = NativeToolModel(transport, out/'calls', upstream, Limits(maximum_calls=224, output=1536),
                            observation, dict(arm=arm, execution_kind=execution_kind,
                                instance_id=instance_id,study_id=study_id,
                                feature=flow.feature), deadline=deadline)
    system = config['agent']['system_template'] + '\nUse exactly one native bash action per response. No network, shared-service or model changes. Commands run as the task user in /testbed; python uses the registered testbed environment. A nonzero top-level tool exit immediately halts this episode. Expected negative diagnostic/test results may be captured as data with their actual exit status and original output; never describe a failed test as passing. A submission is an unaccepted proposal, not independent correctness or human acceptance. Preserve existing author test/test directories and conftest.py: do not add, modify or delete files there. Independent original tests are graded separately; any disposable diagnostics must stay outside that protected scope and retain their actual output/status.'
    phases = ('baseline',) if arm == 'baseline' else PHASES
    if arm!='baseline' and feature_number>1:
        raw,proof=capture_document(capture_bridge,'constitution',out/'retained-document-reads',reader_python=reader)
        flow.retain_constitution(raw,proof)
        phases=PHASES[1:]
    records = []
    initial_pack=export_tree(environment,out/'checkpoints/initial/literal-tree-pack',
        tree=initial['candidate_tree'],reader_python=reader)
    checkpoints = [dict(tag='initial',calls=0,known_native_tokens=0,usage_unknown=0,
        source_tree=initial['candidate_tree'],snapshot_sha256=hashlib.sha256(
            (out/'checkpoints/initial/snapshot.json').read_bytes()).hexdigest(),
        pack_sha256=initial_pack['pack_sha256'],pack_bytes=initial_pack['pack_bytes'])]
    status = 'running'
    original_error = None

    def checkpoint(tag):
        path = out/'checkpoints'/tag
        value = capture_snapshot(capture_bridge, path, baseline_commit=baseline_commit,
                                 literal_baseline_tree=literal_baseline_tree, reader_python=reader)
        pack = export_tree(environment, path/'literal-tree-pack', tree=value['candidate_tree'], reader_python=reader)
        checkpoints.append(dict(tag=tag, calls=model.n_calls, known_native_tokens=model.tokens,
            usage_unknown=model.unknown_usage, source_tree=value['candidate_tree'],
            snapshot_sha256=hashlib.sha256((path/'snapshot.json').read_bytes()).hexdigest(),
            pack_sha256=pack['pack_sha256'], pack_bytes=pack['pack_bytes']))
        return value

    def agent_for(phase, budget, task, implementation=False):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise AdmissionError('task wall budget exhausted before phase')
        model.metadata.update(phase=phase)
        model.limits = replace(model.limits, output=8192 if implementation else 1536)
        system_action = dict(command='/usr/bin/uname -s && /usr/bin/uname -r && /usr/bin/uname -v && /usr/bin/uname -m')
        probe = bridge.execute(system_action)
        write_exclusive(out/'system-probes'/(phase+'.json'),dict(action=system_action,result=probe))
        if probe.get('returncode') != 0:
            raise AdmissionError('actual task system-information capture failed')
        facts = probe['output'].splitlines()
        if len(facts) != 4:
            raise AdmissionError('task system-information response malformed')
        wrapped = ReceiptEnvironment(bridge, out/'tools'/phase,
                                     dict(zip(('system','release','version','machine'), facts)))

        class InstrumentedAgent(upstream.DefaultAgent):
            def step(self):
                result = super().step()
                if implementation and self.n_calls in CHECKPOINTS:
                    checkpoint('implementation-%03d' % self.n_calls)
                return result

        if implementation:
            instance = config['agent']['instance_template']
            phase_system = system + '\nCurrent phase: implementation. Use the retained draft documents and actual feedback as context; neither is independent truth. Independent hidden grades are unavailable.'
        else:
            instance = '{{task}}'
            phase_system = system + '\nCurrent phase: planning only. Inspect source as needed, but modify ONLY '+flow.paths[phase]+'. Write a concise UTF-8 draft of at most 3000 characters. Submit by the separate exact command echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT. Do not make an implementation patch or modify earlier documents in this phase.'
        agent = InstrumentedAgent(model, wrapped, system_template=phase_system, instance_template=instance,
            step_limit=budget, cost_limit=0, max_consecutive_format_errors=1,
            wall_time_limit_seconds=max(1, int(remaining)), output_path=out/'trajectories'/(phase+'.json'))
        result = agent.run(task=task)
        records.append(dict(phase=phase, result=result, calls=agent.n_calls,
                            global_calls=model.n_calls, known_native_tokens=model.tokens,
                            usage_unknown=model.unknown_usage))
        write_exclusive(out/'phase-results'/(phase+'.json'), records[-1])
        if result.get('exit_status') != 'Submitted':
            raise AdmissionError('phase did not submit; retain outcome and halt before next phase')
        return result

    try:
        previous_files = initial_files
        for phase in phases:
            task = json.dumps(flow.document_contract(phase), ensure_ascii=False, indent=2)
            agent_for(phase, 16 if arm == 'baseline' else 4, task)
            raw, proof = capture_document(capture_bridge, phase, out/'document-reads', reader_python=reader,
                                          relative_path=flow.paths[phase])
            flow.receive_document(phase, raw, proof)
            captured = capture_snapshot(capture_bridge, out/'planning-snapshots'/phase, baseline_commit=baseline_commit,
                                        literal_baseline_tree=literal_baseline_tree, reader_python=reader)
            current = _file_state(captured)
            changed = {p for p in set(previous_files)|set(current) if previous_files.get(p)!=current.get(p)}
            if changed - {flow.paths[phase]}:
                raise AdmissionError('planning source boundary violated; preserve snapshot, no next phase')
            previous_files = current
        checkpoint('after-planning')
        feedback = ({k:flow.previous.get(k) for k in ('outcome','summary','findings','next_action')}
                    if arm=='spec_kit_aee' and flow.previous is not None else None)
        context = dict(public_task=public_task, draft_documents=flow.documents,
            prior_sequence_context=prior_context,
            actual_AEE_feedback=feedback,
            boundary='Unaccepted workflow drafts/feedback, never author solution or hidden grade.')
        submission = agent_for('implement', 208, json.dumps(context, ensure_ascii=False, indent=2), implementation=True)
        submitted = submission.get('submission')
        if not isinstance(submitted,str):
            raise AdmissionError('upstream submission is not retained text')
        submitted_bytes = submitted.encode('utf-8')
        with (out/'submitted.patch').open('xb') as handle:
            handle.write(submitted_bytes)
        write_exclusive(out/'submission.json',dict(bytes=len(submitted_bytes),
            sha256=hashlib.sha256(submitted_bytes).hexdigest(),
            empty=not bool(submitted.strip()),
            scope='Original upstream submission text, separate from whole retained source. Empty or incomplete submissions cannot be silently replaced by a correct retained tree. Independent patch/source fidelity and grading remain required.'))
        final = checkpoint('final')
        integrity = _test_integrity(initial_files,_file_state(final))
        write_exclusive(out/'author-test-integrity.json',integrity)
        if not integrity['passing']:
            raise AdmissionError('actor changed protected author-test scope; no acceptance or next task')
        if arm == 'spec_kit_aee':
            flow.previous = flow.assess('implement', 'Implementation proposal submitted; independent grading remains pending.',
                dict(context=context, original_submission=submission, captured_source_tree=final['candidate_tree'],
                     independent_grade=None, accepted_delivery=None))
        status = 'submitted_pending_independent_grade'
    except BaseException as exc:
        original_error = exc
        status = 'stopped_first_failure'
        try:
            checkpoint('stopped')
        except BaseException as capture_error:
            original_error = BaseExceptionGroup('Original task failure and stopped source capture failure', [exc, capture_error])
        raise original_error
    finally:
        result = dict(status=status, error=repr(original_error) if original_error else None,
            arm=arm, execution_kind=execution_kind, instance_id=instance_id, study_id=study_id,
            feature_number=feature_number,
            phase_results=records, checkpoints=checkpoints,
            native_request_attempts=model.n_calls, known_native_tokens_lower_bound=model.tokens,
            usage_unknown=model.unknown_usage, draft_documents=flow.documents,
            actual_AEE_feedback=flow.previous if arm == 'spec_kit_aee' else None,
            independent_grade=None, accepted_delivery=None,
            boundary='Controller execution/source evidence only. Upstream Submitted is a completion proxy, not an independent grade or human acceptance.')
        try:
            write_exclusive(out/'task-result.json', result)
        except BaseException as persistence_error:
            if original_error is not None:
                raise BaseExceptionGroup('Original task/capture failure and result persistence failure',
                                         [original_error, persistence_error])
            raise
    return json.loads((out/'task-result.json').read_text())

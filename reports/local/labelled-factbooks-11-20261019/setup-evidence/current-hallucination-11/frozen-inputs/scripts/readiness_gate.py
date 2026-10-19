"""Require artifact-bound project-sized readiness before launching scored calls."""
import hashlib
import json


def validate_representative(folder,config,projects,arms):
    read=lambda p:json.loads(p.read_text())
    summary=read(folder/'result.json')
    expected={(p,a) for p in projects for a in arms}
    actual=[(r['project'],r['arm']) for r in summary.get('cases',[])]
    if not summary.get('passed') or len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('representative readiness incomplete for scheduled projects/treatments')
    hashes=None
    for case in summary['cases']:
        path=(folder/case['folder']).resolve()
        if not path.is_relative_to(folder.resolve()):raise ValueError('readiness path escapes scope')
        if hashlib.sha256((path/'result.json').read_bytes()).hexdigest()!=case['result_sha256']:
            raise ValueError('readiness result hash mismatch')
        value=read(path/'result.json');freeze=read(path/'freeze.json')
        if value.get('project')!=case['project'] or value.get('arm')!=case['arm']:
            raise ValueError('representative result belongs to another project/treatment')
        if any(freeze['config'].get(k)!=config[k] for k in ('model','context','max_output','stage_seconds','primary_calls','enable_thinking','action_protocol')):
            raise ValueError('representative readiness configuration differs')
        if hashes is not None and freeze['hashes']!=hashes:raise ValueError('controller changed during readiness')
        hashes=freeze['hashes']
        if (not value.get('passed') or not value['before_repair']['passed'] or not value['after_repair']['passed']
            or value['injected_failure']['passed'] or value['repair']['calls']<1
            or value['elapsed_seconds']>config['stage_seconds'] or value['allowed_seconds']!=config['stage_seconds']):
            raise ValueError('representative execution/repair capacity not demonstrated')
        phases={r['phase']:r for r in value['phases']}
        ordered=['solve'] if case['arm']=='baseline' else ['constitution','specify','plan','tasks','implement','converge','final_implement']
        required=set(ordered)
        if [r['phase'] for r in value['phases'] if r['phase'] in required]!=ordered:
            raise ValueError('representative primary phase order differs')
        if not required.issubset(phases) or any(not phases[p]['completed'] or phases[p]['calls']<1 for p in required):
            raise ValueError('representative workflow lacks actual completed phase exposure')
        if case['arm']=='spec_kit_aee' and {v['phase'] for v in value['assessments']}!={'specify','plan','tasks','implement'}:
            raise ValueError('representative AEE checkpoints missing')
    return summary

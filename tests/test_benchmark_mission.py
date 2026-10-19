"""Functional fresh-path, exact-migration and labelled-diagnostic checks; no inference."""
import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import calibration_recovery as recovery
import labelled_hallucinations as diagnostic
import launch_benchmark_mission as mission


@pytest.mark.parametrize('pipeline,study', [(0, 3), (-1, 3), (10, 0), (True, 3), ('../10', 3)])
def test_campaign_ids_are_positive_integers(tmp_path, pipeline, study):
    with pytest.raises(ValueError):
        mission.paths(tmp_path, pipeline, study)


def test_fresh_paths_and_serial_preparation(tmp_path):
    paths = mission.paths(tmp_path, 10, 3)
    assert paths['raw'].name == 'current-study-03'
    assert paths['status'].name == 'current-pipeline-10.json'
    assert [s for s, _ in mission.plan(paths)] == ['image', 'grade', 'context', 'transport', 'hallucination', 'latency']
    assert not list(tmp_path.iterdir())
    paths['status'].parent.mkdir()
    paths['status'].write_text('{}')
    with pytest.raises(FileExistsError):
        mission.paths(tmp_path, 10, 3)


def test_no_existing_output_is_reused(tmp_path):
    paths = mission.paths(tmp_path, 10, 3)
    paths['hallucination'].mkdir(parents=True)
    with pytest.raises(FileExistsError):
        mission.paths(tmp_path, 10, 3)


def test_exact_infrastructure_definition_migration(tmp_path, monkeypatch):
    before, after = 'old exact AST', 'new exact AST'
    entry = {which: hashlib.sha256(value.encode()).hexdigest() for which, value in [('before', before), ('after', after)]}
    manifest = tmp_path / 'registered.json'
    manifest.write_text(json.dumps({'definitions': {'runtime.py': {'http': entry}}}))
    monkeypatch.setattr(recovery, 'MANIFEST', manifest)
    copied = tmp_path / 'recovery-migration.json'
    copied.write_bytes(manifest.read_bytes())
    admission = dict(recovery_protocol='infrastructure-recovery-v1', hashes={'recovery-migration.json': hashlib.sha256(copied.read_bytes()).hexdigest()})
    (tmp_path / 'admission.json').write_text(json.dumps(admission))
    assert recovery.definition_matches('runtime.py', 'http', before, after, tmp_path)
    assert not recovery.definition_matches('runtime.py', 'http', before, after + ' changed', tmp_path)
    assert not recovery.definition_matches('runtime.py', 'solver', before, after, tmp_path)
    admission['hashes'] = {}
    (tmp_path / 'admission.json').write_text(json.dumps(admission))
    assert not recovery.definition_matches('runtime.py', 'http', before, after, tmp_path)
    assert recovery.definition_matches('runtime.py', 'solver', before, before, tmp_path)


def test_registered_current_changes_are_only_four_infrastructure_definitions():
    manifest = json.loads(recovery.MANIFEST.read_text())
    expected = {'scripts/current_local.py': {'http'}, 'scripts/repeated_local.py': {'Provider'},
                'scripts/runtime_checks.py': {'RuntimeIntervention', 'RuntimeWatchdog'}}
    assert {p: set(defs) for p, defs in manifest['definitions'].items()} == expected
    for name, definitions in manifest['definitions'].items():
        nodes = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse((mission.ROOT / name).read_text()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for identifier, entry in definitions.items():
            assert hashlib.sha256(nodes[identifier].encode()).hexdigest() == entry['after']


def test_labelled_corpus_has_known_balanced_truth_without_label_in_id():
    cases = json.loads(diagnostic.CORPUS.read_text())['cases']
    assert len(cases) == len({c['id'] for c in cases}) == 12
    assert {label: sum(diagnostic.oracle(c) == label for c in cases) for label in diagnostic.VERDICTS} == dict(supported=4, contradicted=4, unknown=4)
    for case in cases:
        assert not any(label in case['id'] for label in diagnostic.VERDICTS)
        assert 'gold' not in case


def test_diagnostic_unknown_truth_and_invalid_decisions_not_false_labels():
    rows = [dict(gold='contradicted', prediction='contradicted'), dict(gold='contradicted', prediction='unknown'),
            dict(gold='supported', prediction='supported'), dict(gold='supported', prediction=None),
            dict(gold='unknown', prediction='supported')]
    result = diagnostic.metrics(rows)
    assert result['binary_known_truth']['tp'] == 1
    assert result['binary_known_truth']['fn'] == 1
    assert result['binary_known_truth']['tn'] == 1
    assert result['binary_known_truth']['recall'] == .5
    assert result['invalid_decisions'] == 1
    assert result['unknown_claims_accepted'] == 1
    assert diagnostic.metrics([])['binary_known_truth']['precision'] is None


def test_diagnostic_does_not_retry_infrastructure_failure(tmp_path, monkeypatch):
    attempts = []
    monkeypatch.setattr(diagnostic.current, 'setup', lambda: None)
    def freeze(out, purpose):
        out.mkdir()
    monkeypatch.setattr(diagnostic.current, 'freeze', freeze)
    def http(route, payload=None, timeout=120):
        if route == '/slots': return [dict(is_processing=False)]
        if route == '/apply-template': return dict(prompt='fixture')
        if route == '/tokenize': return dict(tokens=[1, 2])
        attempts.append(route)
        raise ConnectionError('synthetic transport failure')
    monkeypatch.setattr(diagnostic.current, 'http', http)
    out = tmp_path / 'diagnostic'
    with pytest.raises(ConnectionError):
        diagnostic.run(out)
    assert attempts == ['/v1/chat/completions']
    record = json.loads((out / 'calls/call-0000.json').read_text())
    assert record['usage'] is None and record['unknown_reason']
    assert json.loads((out / 'result.json').read_text())['complete'] is False


def test_corrected_unknown_controls_supply_no_explicit_counterevidence():
    before = json.loads(diagnostic.CORPUS.read_text())
    corrected = json.loads((mission.ROOT / 'benchmarks/current_local/hallucination-cases-v2.json').read_text())
    changed = []
    for old, new in zip(before['cases'], corrected['cases']):
        assert old['id'] == new['id']
        assert diagnostic.oracle(old) == diagnostic.oracle(new)
        if old != new:
            changed.append(new['id'])
            assert {k: v for k, v in old.items() if k != 'facts'} == {k: v for k, v in new.items() if k != 'facts'}
    assert changed == ['case-09', 'case-11']
    completion = corrected['cases'][8]
    citation = corrected['cases'][10]
    assert completion['facts'] == {}
    assert citation['facts'] == {'complete_inventory': False, 'references': {}}
    assert {v: sum(diagnostic.oracle(c) == v for c in corrected['cases']) for v in diagnostic.VERDICTS} == dict(supported=4, contradicted=4, unknown=4)


def test_corpus_version_refuses_unregistered_inputs(tmp_path):
    with pytest.raises(ValueError, match='shipped corpus'):
        diagnostic.run(tmp_path / 'never-created', corpus_version=3)
    assert not (tmp_path / 'never-created').exists()

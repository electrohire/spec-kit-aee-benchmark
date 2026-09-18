"""Preserve calibration failures and inventory new physical model work exactly once."""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

from benchmark_runner.store import canonical, write_json
from report_repeated import accounting, manifest

ROOT = Path(__file__).resolve().parents[1]


def copy_evidence(source, target):
    for path in source.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.suffix not in ('.json', '.jsonl', '.tar', '.md', '.py', '.ps1') and 'objects' not in path.parts:
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path.name.startswith('call-') and path.suffix == '.json':
            record = json.loads(path.read_text(encoding='utf-8-sig'))
            request = record.pop('request', None)
            if request is not None:
                record['request_sha256'] = hashlib.sha256(canonical(request)).hexdigest()
            for choice in record.get('response', {}).get('choices', []):
                message = choice.get('message', {})
                reasoning = message.pop('reasoning_content', None)
                if reasoning is not None:
                    message['reasoning_sha256'] = hashlib.sha256(reasoning.encode()).hexdigest()
            record['original_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            write_json(destination, record)
        else:
            shutil.copyfile(path, destination)


def run(destination):
    destination.mkdir(parents=True, exist_ok=False)
    folders = sorted(ROOT.glob('artifacts/repeated-workflow-*'))
    folders += [ROOT / 'artifacts' / name for name in (
        'repeated-latency-01', 'repeated-calibration-01', 'matched-calibration-01', 'context-selection-01')]
    rows = []
    all_records = []
    for folder in folders:
        records = [json.loads(p.read_text(encoding='utf-8-sig')) for p in sorted(folder.rglob('call-*.json'))]
        all_records.extend(records)
        result_path = folder / ('result.json' if (folder/'result.json').exists() else 'calibration.json')
        result = json.loads(result_path.read_text())
        rows.append(dict(scope=folder.name, passed=result['passed'], economics=accounting(records)))
        copy_evidence(folder, destination / folder.name)
    copy_evidence(ROOT / 'artifacts/repeated-assets', destination / 'controller-assets')
    interrupted=ROOT/'artifacts/repeated-study-01'
    records=[json.loads(p.read_text()) for p in interrupted.glob('*/call-*.json')]
    all_records.extend(records)
    rows.append(dict(scope='repeated-study-01-interrupted',passed=False,economics=accounting(records),evidence='../repeated-study-01-interrupted/README.md'))
    notices = destination / 'licenses'
    notices.mkdir()
    shutil.copyfile(ROOT / 'docs/spec-kit-LICENSE.txt', notices / 'spec-kit-LICENSE.txt')
    distribution = importlib.metadata.distribution('applied-epistemic-engineering')
    for name in distribution.files:
        if '/licenses/' in str(name).replace('\\', '/'):
            shutil.copyfile(distribution.locate_file(name), notices / ('aee-engine-' + Path(name).name))
    write_json(destination / 'summary.json', dict(rows=rows, economics=accounting(all_records),
        note='All preparation attempts retained. No scored success claim; controller work is unpriced.'))
    scored_rows = []
    for name in ('repeated-study-02', 'matched-repair-01'):
        source = ROOT / 'artifacts' / name
        assert (source / 'results.json').exists(), 'Complete generation and grading before final inventory'
        records = [json.loads(p.read_text()) for p in source.rglob('call-*.json')]
        all_records.extend(records)
        scored_rows.append(dict(scope=name, economics=accounting(records)))
    historical = json.loads((ROOT / 'reports/local/token-ledger.json').read_text())
    current = accounting(all_records)
    write_json(destination / 'physical-inventory.json', dict(
        preparation=rows, scored=scored_rows, new_work=current,
        historical_inventory='../token-ledger.json',
        all_campaigns_calls=historical['calls']+current['calls'],
        all_campaigns_known_tokens=historical['known_tokens']+current['known_total_tokens'],
        all_campaigns_unknown_calls=historical['unknown_calls']+current['unknown_calls'],
        all_campaigns_reservation_bound=historical['configured_reservation_upper_bound']+current['budget_reservation_total'],
        api_expenditure_usd=0,
        note='Physical diagnostic calls counted once. Mixed models/tasks: inventory only, not a pooled efficiency comparison. Hardware, energy and controller work unpriced.'))
    (destination / 'README.md').write_text(
        '# Repeated campaign preparation\n\nAll full-workflow calibration attempts, including failures, are retained. '
        'These requests are setup costs, separate from scored treatment comparisons. '
        'Full requests and native reasoning remain local with hashes. See summary.json for measured usage and unknown-call reservations.\n', encoding='utf-8')
    manifest(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    run(parser.parse_args().destination)

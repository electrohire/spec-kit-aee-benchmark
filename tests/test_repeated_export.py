import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_runner.store import Store, canonical, write_json
from report_repeated import accounting
from report_repeated_setup import copy_evidence


def test_public_export_preserves_tool_evidence_without_private_request_or_reasoning(tmp_path):
    raw = tmp_path / 'raw'
    store = Store(raw / 'evidence')
    payload = b'{"exit_code":1,"stdout":"failed assertion"}'
    ref = store.artifact(payload)
    record = dict(request={'messages':[{'role':'user','content':'private input'}]},
                  response={'choices':[{'message':{'content':'public action','reasoning_content':'private reasoning'}}]},
                  usage=None, preflight_input_tokens=50, max_output=20)
    write_json(raw / 'call-0000.json', record)
    destination = tmp_path / 'public'
    copy_evidence(raw, destination)
    exported = json.loads((destination / 'call-0000.json').read_text())
    assert 'request' not in exported
    assert exported['request_sha256'] == hashlib.sha256(canonical(record['request'])).hexdigest()
    message = exported['response']['choices'][0]['message']
    assert message['content'] == 'public action' and 'reasoning_content' not in message
    assert (destination / 'evidence' / ref['path']).read_bytes() == payload
    assert exported['usage'] is None
    economics = accounting([exported])
    assert economics['total_tokens'] is None and economics['known_total_tokens'] == 0
    assert economics['budget_reservation_total'] == 70

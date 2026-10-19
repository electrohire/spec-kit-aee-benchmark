"""No inference: infrastructure faults halt once and retain bounded diagnostics."""
import base64
import errno
import hashlib
import io
import json
import sys
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import current_local
import repeated_local as runner
from model_outcomes import model_failure
from runtime_checks import RuntimeIntervention,RuntimeWatchdog
from infrastructure_errors import InfrastructureFailure,RESPONSE_LIMIT,retained_bytes


@pytest.mark.parametrize('error',[
    urllib.error.HTTPError('http://127.0.0.1/apply-template',500,'fixture',{},io.BytesIO(b'fixture')),
    urllib.error.URLError('fixture disconnected'),
    ConnectionError('fixture disconnected'),
    OSError(errno.ENOSPC,'fixture storage fault'),
])
def test_infrastructure_fault_intervenes_on_first_error(tmp_path,error):
    guard=RuntimeWatchdog(tmp_path)
    with pytest.raises(RuntimeIntervention,match='infrastructure'):
        guard.error(error,'tasks',2)
    alert=json.loads((tmp_path/'runtime-alert.json').read_text())
    assert alert['phase']=='tasks' and alert['stage']==2
    assert not model_failure(alert)


def test_context_http_failure_keeps_failed_request_and_response_without_generation(tmp_path,monkeypatch):
    body=b'{"error":"synthetic template failure"}'
    requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            raise urllib.error.HTTPError(request.full_url,500,'fixture',{},io.BytesIO(body))
    monkeypatch.setattr(current_local.urllib.request,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(runner,'local_json',current_local.http)
    provider=runner.Provider(tmp_path,1,5)
    messages=[{'role':'system','content':'fixture'},{'role':'user','content':'public task'}]
    with pytest.raises(OSError):
        provider.query(messages,'tasks',2,time.monotonic()+60)
    record=json.loads((tmp_path/'preflight-0000.json').read_text())
    evidence=record['infrastructure_evidence']
    assert evidence['http_status']==500 and evidence['generation_request'] is False
    assert base64.b64decode(evidence['request']['base64'])==requests[0].data
    assert evidence['request']['sha256']==hashlib.sha256(requests[0].data).hexdigest()
    assert base64.b64decode(evidence['response']['base64'])==body
    assert evidence['request']['complete'] and evidence['response']['complete']
    assert len(requests)==1 and record['http_requests']==1
    assert provider.calls==[] and not list(tmp_path.glob('call-*.json'))


def test_alert_write_failure_keeps_primary_intervention_and_does_not_count_as_model_failure(tmp_path,monkeypatch):
    def no_space(*args,**kwargs):
        raise OSError(errno.ENOSPC,'synthetic storage fault')
    monkeypatch.setattr(Path,'write_text',no_space)
    guard=RuntimeWatchdog(tmp_path,capture=no_space)
    with pytest.raises(RuntimeIntervention) as caught:
        guard.stop('repeated identical action without changed observation',phase='tasks',stage=2)
    alert=caught.value.alert
    assert alert['reason']=='repeated identical action without changed observation'
    assert 'snapshot_error' in alert and 'alert_write_error' in alert
    assert not model_failure(alert)


def test_context_transport_failure_never_becomes_three_solver_retries(tmp_path):
    class Provider:
        calls=[]
        queries=0
        def query(self,*args):
            self.queries+=1
            raise urllib.error.URLError('synthetic preflight failure')
    provider=Provider()
    session=runner.Session(None,provider,runner.Store(tmp_path/'store'),'fixture')
    session.watchdog=RuntimeWatchdog(tmp_path/'alert')
    with pytest.raises(RuntimeIntervention,match='infrastructure'):
        session.phase('tasks','fixture','fixture',2,20,time.monotonic()+60)
    assert provider.queries==1 and provider.calls==[]
    assert not (tmp_path/'store/action_errors.jsonl').exists()


def test_storage_fault_on_model_alert_stops_the_campaign():
    assert not model_failure({'reason':'repeated identical action without changed observation',
        'alert_write_error':'OSError(28, synthetic storage fault)'})


@pytest.mark.parametrize('raw',[b'not JSON',b'\xff'])
def test_invalid_http_json_is_infrastructure_not_solver_json(tmp_path,monkeypatch,raw):
    class Handle:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return raw
    class Opener:
        def open(self,*args,**kwargs):return Handle()
    monkeypatch.setattr(current_local.urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(InfrastructureFailure) as caught:
        current_local.http('/apply-template',{'messages':[]})
    assert caught.value.evidence['reason']=='invalid_json'
    assert caught.value.evidence['http_status']==200
    assert base64.b64decode(caught.value.evidence['response']['base64'])==raw


def test_large_error_body_is_explicitly_truncated_not_claimed_complete(monkeypatch):
    body=b'x'*(RESPONSE_LIMIT+10)
    class Opener:
        def open(self,request,**kwargs):
            raise urllib.error.HTTPError(request.full_url,500,'fixture',{},io.BytesIO(body))
    monkeypatch.setattr(current_local.urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(InfrastructureFailure) as caught:
        current_local.http('/apply-template',{'messages':[]})
    response=caught.value.evidence['response']
    assert response['complete'] is False and response['sha256'] is None
    assert response['byte_length'] is None and response['captured_length']==RESPONSE_LIMIT
    assert base64.b64decode(response['base64'])==body[:RESPONSE_LIMIT]


def test_bounded_request_retains_full_digest_but_does_not_claim_full_payload():
    value=retained_bytes(b'abcdefgh',4)
    assert value['complete'] is False and value['byte_length']==8
    assert value['sha256']==hashlib.sha256(b'abcdefgh').hexdigest()
    assert base64.b64decode(value['base64'])==b'abcd'


def test_secondary_preflight_write_failure_preserves_primary_http_evidence(tmp_path,monkeypatch):
    class Opener:
        def open(self,request,**kwargs):
            raise urllib.error.HTTPError(request.full_url,500,'fixture',{},io.BytesIO(b'primary failure'))
    monkeypatch.setattr(current_local.urllib.request,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(runner,'local_json',current_local.http)
    def no_space(*args,**kwargs):raise OSError(errno.ENOSPC,'synthetic disk fault')
    monkeypatch.setattr(runner,'write_json',no_space)
    provider=runner.Provider(tmp_path,1,5)
    with pytest.raises(InfrastructureFailure,match='evidence write failed') as caught:
        provider.query([{'role':'user','content':'fixture'}],'tasks',2,time.monotonic()+60)
    evidence=caught.value.evidence
    assert 'write_error' in evidence
    assert evidence['preflight']['infrastructure_evidence']['http_status']==500
    assert provider.calls==[]


def test_failed_generation_retains_unknown_usage_and_http_details(tmp_path,monkeypatch):
    requests=[]
    class Handle:
        status=200
        def __init__(self,value):self.value=value
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return json.dumps(self.value).encode()
    class Opener:
        def open(self,request,**kwargs):
            route=request.full_url.split('8081')[-1].split('?')[0];requests.append(route)
            if route=='/apply-template':return Handle({'prompt':'fixture'})
            if route=='/tokenize':return Handle({'tokens':[1]})
            if route=='/slots':return Handle([])
            assert route=='/v1/chat/completions'
            raise urllib.error.HTTPError(request.full_url,503,'fixture',{},io.BytesIO(b'unavailable'))
    monkeypatch.setattr(current_local.urllib.request,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(runner,'local_json',current_local.http)
    provider=runner.Provider(tmp_path,1,5)
    with pytest.raises(InfrastructureFailure):
        provider.query([{'role':'user','content':'fixture'}],'tasks',2,time.monotonic()+60)
    saved=json.loads((tmp_path/'call-0000.json').read_text())
    assert saved['usage'] is None and saved['unknown_reason']=='failed_request_reserved_not_imputed'
    assert saved['infrastructure_evidence']['http_status']==503
    assert saved['infrastructure_evidence']['generation_request'] is True
    assert requests.count('/v1/chat/completions')==1


def test_real_loopback_http_error_is_captured_without_proxy_or_model_call(monkeypatch):
    import http.server
    import threading
    seen=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path,self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(500);self.end_headers();self.wfile.write(b'fixture server failure')
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(current_local,'URL',f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
    try:
        with pytest.raises(InfrastructureFailure) as caught:
            current_local.http('/apply-template',{'messages':[]},timeout=3)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
    assert len(seen)==1 and seen[0][0]=='/apply-template'
    assert json.loads(seen[0][1])['model']==current_local.MODEL
    assert caught.value.evidence['http_status']==500
    assert base64.b64decode(caught.value.evidence['response']['base64'])==b'fixture server failure'

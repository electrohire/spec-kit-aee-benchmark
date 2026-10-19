import http.client
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import direct_worker_transport as transport
from infrastructure_errors import InfrastructureFailure


def test_literal_request_bytes_and_tcp_connection_reused(monkeypatch):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']))
            seen.append((self.client_address[1],self.path,body))
            self.send_response(200);self.send_header('Content-Length','11');self.end_headers();self.wfile.write(b'{"ok":true}')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    original=http.client.HTTPConnection
    def connect(host,port,timeout):
        assert (host,port)==('127.0.0.1',50467)
        return original('127.0.0.1',server.server_port,timeout=timeout)
    monkeypatch.setattr(transport.http.client,'HTTPConnection',connect)
    binding=SimpleNamespace(check=lambda:None)
    body=b'{"messages":[{"role":"user","content":"literal \\"quote\\""}],"model":"qwen3.8-27b"}'
    try:
        for _ in range(3):assert transport.request(binding,'/apply-template',body,5)=={'ok':True}
        assert len({row[0] for row in seen})==1
        assert [row[1:] for row in seen]==[('/apply-template',body)]*3
    finally:
        binding._http_connection.close();server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('kind',['timeout','disconnect','redirect','server','json'])
def test_first_failure_has_no_retry_and_retains_request(monkeypatch,kind):
    calls=[]
    class Connection:
        sock=None
        def __init__(self,*args,**kwargs):pass
        def request(self,*args):
            calls.append(args)
            if kind=='timeout':raise TimeoutError('fixture connect failure')
            if kind=='disconnect':raise http.client.RemoteDisconnected('fixture disconnect')
        def getresponse(self):
            return SimpleNamespace(status=302 if kind=='redirect' else 500 if kind=='server' else 200,
                read=lambda:b'not JSON' if kind=='json' else b'fixture response')
        def close(self):pass
    monkeypatch.setattr(transport.http.client,'HTTPConnection',Connection)
    binding=SimpleNamespace(check=lambda:None)
    with pytest.raises(InfrastructureFailure) as captured:
        transport.request(binding,'/apply-template',b'exact request',120)
    assert len(calls)==1 and binding._http_connection is None
    assert captured.value.evidence['request']['complete'] is True
    assert captured.value.evidence['generation_request'] is False


def test_binding_failure_precedes_network(monkeypatch):
    def fail():raise RuntimeError('worker identity changed')
    monkeypatch.setattr(transport.http.client,'HTTPConnection',lambda *a,**k:pytest.fail('network forbidden'))
    with pytest.raises(RuntimeError,match='identity'):
        transport.request(SimpleNamespace(check=fail),'/apply-template',b'{}',120)


def test_context_failure_retains_actual_request_without_retry(tmp_path,monkeypatch):
    import current_local as current
    from infrastructure_errors import response_failure
    calls=[]
    def fail(path):
        calls.append(path)
        raise response_failure('/apply-template',b'exact failed payload',b'',reason='transport_error',source_complete=False)
    monkeypatch.setattr(current,'configure_worker_binding',lambda path:None)
    monkeypatch.setattr(current,'setup',lambda:None)
    monkeypatch.setattr(current,'context_calibration',fail)
    monkeypatch.setattr(sys,'argv',['current_local.py','context-calibration',str(tmp_path/'context')])
    with pytest.raises(InfrastructureFailure):current.main()
    value=json.loads((tmp_path/'context/failure.json').read_text())
    assert len(calls)==1 and value['inference_calls']==0
    assert value['infrastructure_evidence']['request']['complete'] is True
    assert value['infrastructure_evidence']['request']['byte_length']==len(b'exact failed payload')


def test_idle_socket_retired_before_next_request_not_retried(monkeypatch):
    clock=[0.0];created=[];sent=[];closed=[]
    class Connection:
        sock=None
        def __init__(self,*a,**k):created.append(self)
        def request(self,*args):sent.append((self,args))
        def getresponse(self):return SimpleNamespace(status=200,read=lambda:b'{"ok":true}',getheader=lambda name:'timeout=5, max=100')
        def close(self):closed.append(self)
    monkeypatch.setattr(transport.http.client,'HTTPConnection',Connection)
    monkeypatch.setattr(transport.time,'monotonic',lambda:clock[0])
    binding=SimpleNamespace(check=lambda:None)
    transport.request(binding,'/props',None,120)
    assert binding._http_idle_seconds==4.0
    clock[0]=6.0
    transport.request(binding,'/props',None,120)
    assert len(created)==len(sent)==2 and closed==[created[0]]


def test_native_probe_bootstrap_failure_is_retained_without_model_call(tmp_path,monkeypatch):
    import probe_action_transport as probe
    from infrastructure_errors import response_failure
    def fail(path):raise response_failure('/v1/models',None,b'',reason='transport_error',source_complete=False)
    monkeypatch.setattr(probe.current,'configure_worker_binding',fail)
    monkeypatch.setattr(probe.current,'Provider',lambda *a:pytest.fail('generation forbidden'))
    monkeypatch.setattr(sys,'argv',['probe_action_transport.py',str(tmp_path/'probe')])
    with pytest.raises(InfrastructureFailure):probe.main()
    value=json.loads((tmp_path/'probe/bootstrap-failure.json').read_text())
    assert value['generation_requests']==0
    assert value['infrastructure_evidence']['route']=='/v1/models'

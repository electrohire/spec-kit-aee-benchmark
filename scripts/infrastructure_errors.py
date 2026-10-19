"""Bounded local transport diagnostics; no retry, authority or usage inference."""
import base64
import hashlib

REQUEST_LIMIT=8*1024*1024
RESPONSE_LIMIT=64*1024


class InfrastructureFailure(OSError):
    def __init__(self,message,evidence):
        super().__init__(message)
        self.evidence=evidence


def retained_bytes(data,limit,source_complete=True):
    retained=data[:limit]
    return dict(base64=base64.b64encode(retained).decode('ascii'),
                sha256=hashlib.sha256(data).hexdigest() if source_complete else None,
                byte_length=len(data) if source_complete else None,
                captured_sha256=hashlib.sha256(retained).hexdigest(),
                captured_length=len(retained),complete=source_complete and len(data)<=limit)


def response_failure(route,request_body,response_body,*,status=None,reason,source_complete=True):
    evidence=dict(kind='local_transport_failure',route=route,http_status=status,
        reason=reason,generation_request=route=='/v1/chat/completions',
        request=retained_bytes(request_body or b'',REQUEST_LIMIT),
        response=retained_bytes(response_body,RESPONSE_LIMIT,source_complete))
    return InfrastructureFailure(f'local infrastructure failure: {route} ({reason},HTTP{status})',evidence)

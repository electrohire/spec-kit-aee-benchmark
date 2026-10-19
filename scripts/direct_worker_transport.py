"""Client-only pin to the existing, operator-approved Windows qwen worker.

No process launch, service control, fallback or retry. These are local process
and transport checks, not authenticated human identity or model efficacy proof.
"""
import ctypes
import hashlib
import json
import os
import socket
import struct
from pathlib import Path

ENDPOINT = 'http://127.0.0.1:50467'
MODEL = 'qwen3.8-27b'
WEIGHTS = 'C:/Models/qwen3.8-27b.gguf'


def native_observation(pid):
    if os.name != 'nt':
        raise RuntimeError('approved worker observation requires Windows')
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.GetProcessTimes.argtypes = [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)]
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), 'worker process unavailable')
    try:
        times = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise OSError(ctypes.get_last_error(), 'worker creation time unavailable')
        name, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), 'worker executable unavailable')
        created = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
    finally:
        kernel.CloseHandle(handle)
    table = ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
    table.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.BOOL, w.ULONG, ctypes.c_int, w.ULONG]
    size = w.DWORD()
    if table(None, ctypes.byref(size), False, 2, 3, 0) != 122:
        raise RuntimeError('listener inventory size unavailable')
    data = ctypes.create_string_buffer(size.value)
    if table(data, ctypes.byref(size), False, 2, 3, 0):
        raise RuntimeError('listener inventory unavailable')
    raw = data.raw
    count = struct.unpack_from('<I', raw)[0]
    listeners = []
    for index in range(count):
        _, address, port, _, _, owner = struct.unpack_from('<6I', raw, 4 + 24 * index)
        if socket.ntohs(port & 65535) == 50467:
            listeners.append(dict(address=socket.inet_ntoa(struct.pack('<I', address)), port=50467, pid=owner))
    return dict(pid=pid, creation_filetime=created, executable=name.value.replace('\\', '/'), listeners=listeners)


def validate_binding(value):
    if (value.get('protocol') != 'existing-qwen-worker-v1' or value.get('endpoint') != ENDPOINT
        or value.get('model') != MODEL or value.get('weights') != WEIGHTS
        or type(value.get('pid')) is not int or value['pid'] <= 0
        or type(value.get('creation_filetime')) is not int
        or value.get('executable', '').lower() != 'c:/llm/llama/llama-server.exe'):
        raise ValueError('invalid approved existing-worker binding')


def validate_observation(binding, observed):
    validate_binding(binding)
    if (any(observed.get(k) != binding[k] for k in ('pid', 'creation_filetime'))
        or observed.get('executable', '').lower() != binding['executable'].lower()
        or observed.get('listeners') != [dict(address='127.0.0.1', port=50467, pid=binding['pid'])]):
        raise RuntimeError('existing worker process or port ownership changed; halt without fallback')


class WorkerBinding:
    def __init__(self, path):
        self.path = Path(path).resolve()
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.value = json.loads(raw)
        self.check()

    def check(self):
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.sha256:
            raise RuntimeError('worker binding bytes changed')
        validate_binding(self.value)
        validate_observation(self.value, native_observation(self.value['pid']))

    def check_model(self, models, props):
        if ({m.get('id') for m in models.get('data', [])} != {MODEL}
            or str(props.get('model_path', '')).replace('\\', '/') != WEIGHTS):
            raise RuntimeError('existing worker model or weights path changed')


def admit_route(preflight, binding, calibrated_url, actual_url):
    """Allow exactly the separately approved route change; all other caps stay bound."""
    admission = json.loads((preflight / 'admission.json').read_text())
    copied = preflight / 'worker-binding.json'
    if (binding is None or admission.get('recovery_protocol') != 'direct-worker-v1'
        or calibrated_url != 'http://127.0.0.1:8081' or actual_url != ENDPOINT
        or copied.read_bytes() != binding.path.read_bytes()
        or admission.get('hashes', {}).get('worker-binding.json') != binding.sha256):
        raise ValueError('unregistered route change')
    binding.check()
    validate_route_proof(preflight / 'direct-route-proof.json', binding)
    for name in ('transport', 'latency'):
        frozen = json.loads((preflight / name / 'freeze.json').read_text())
        if (frozen.get('worker_binding_sha256') != binding.sha256
            or frozen.get('config', {}).get('url') != ENDPOINT):
            raise ValueError('fresh direct-worker transport/latency binding missing')


def validate_route_proof(path, binding):
    proof = json.loads(Path(path).read_text())
    rows = proof.get('rows', [])
    if (proof.get('passed') is not True or proof.get('generation_requests') != 0
        or proof.get('binding_sha256') != binding.sha256 or len(rows) != 98
        or len({r.get('source') for r in rows}) != 98
        or any(r.get('original_count') != r.get('direct_count') for r in rows)):
        raise ValueError('retained-request direct-route equivalence proof missing or inconsistent')

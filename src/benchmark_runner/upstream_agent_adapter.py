"""Thin, credential-free native-provider bridge for the pinned upstream agent.

No upstream import, model request, environment creation or service action occurs
at import. Experiment registration/admission remains the controller's job.
"""
from dataclasses import dataclass
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from .verified_write import write_text_verified


class AdmissionError(RuntimeError):
    pass


class ToolFailure(RuntimeError):
    pass


def credential_file_guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        name = Path(os.fsdecode(args[0])).name.lower()
        if name == '.env' or name.startswith('.env.'):
            raise PermissionError('Benchmark forbids credential/dotenv file access')


def safe_upstream():
    """Require safe launch configuration before ANY minisweagent import."""
    if os.environ.get('PYTHON_DOTENV_DISABLED') != '1' or os.environ.get('MSWEA_SILENT_STARTUP') != '1':
        raise AdmissionError('disabled dotenv and silent startup are required')
    location = os.environ.get('MSWEA_GLOBAL_CONFIG_DIR')
    if not location:
        raise AdmissionError('dedicated empty upstream config directory required')
    directory = Path(location).resolve()
    if not directory.is_dir() or any(directory.iterdir()):
        raise AdmissionError('upstream config directory must start empty')
    sys.addaudithook(credential_file_guard)
    if importlib.metadata.version('mini-swe-agent') != '2.4.6':
        raise AdmissionError('registered upstream agent version changed')
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.docker import DockerEnvironment
    from minisweagent.models.utils.actions_toolcall import BASH_TOOL, parse_toolcall_actions, format_toolcall_observation_messages
    return SimpleNamespace(DefaultAgent=DefaultAgent, DockerEnvironment=DockerEnvironment,
        tool=BASH_TOOL, parse=parse_toolcall_actions, observe=format_toolcall_observation_messages)


@dataclass(frozen=True)
class Limits:
    maximum_calls: int = 208
    context: int = 32768
    output: int = 8192
    timeout: int = 600
    seed: int = 20261019
    native_token_cap: int = 24000000


def native_usage(response):
    if not isinstance(response, dict):
        raise AdmissionError('native usage missing; preserve unknown, halt')
    value = response.get('usage')
    if not isinstance(value, dict):
        raise AdmissionError('native usage missing; preserve unknown, halt')
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        if type(value.get(key)) is not int or value[key] < 0:
            raise AdmissionError('invalid native token usage')
    if value['total_tokens'] != value['prompt_tokens'] + value['completion_tokens']:
        raise AdmissionError('native usage total inconsistent')
    details = value.get('prompt_tokens_details', {})
    if not isinstance(details, dict):
        raise AdmissionError('native usage details malformed')
    cached = details.get('cached_tokens')
    if cached is not None and (type(cached) is not int or not 0 <= cached <= value['prompt_tokens']):
        raise AdmissionError('cached usage is not a valid prompt subset')
    return value


def write_exclusive(path, value):
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    # Verified write (fleet standard, 2026-10-28): episode receipts
    # are evidence; the write verifies by read-back or raises.
    # Serialisation is unchanged, so the bytes are identical.
    write_text_verified(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


class BoundNativeTransport:
    """Existing approved worker only: no loading, service control or fallback.

    The OS/port/creation observation establishes local retained binding, not
    externally authenticated identity. Admission must also freeze these inputs.
    """
    ROUTES = frozenset(('/slots','/props','/v1/models','/apply-template','/tokenize','/v1/chat/completions'))
    def __init__(self, binding_path, expected_binding_sha256, expected_weights_sha256):
        binding_path = Path(binding_path).resolve()
        if hashlib.sha256(binding_path.read_bytes()).hexdigest() != expected_binding_sha256:
            raise AdmissionError('prospectively bound worker file changed')
        root = Path(__file__).resolve().parents[2]
        path = root/'scripts/matched_completion_recovery.py'
        spec = importlib.util.spec_from_file_location('_registered_port_migration',path)
        helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        value = json.loads(binding_path.read_text())
        # One-time restoration already consumed. No arbitrary future worker or
        # router is admitted by an agent-selected JSON endpoint/name alone.
        if value['endpoint'] != 'http://127.0.0.1:52301' or value['pid'] != 64756:
            raise AdmissionError('not the explicitly restored existing worker')
        error_path=(root/'scripts/infrastructure_errors.py').resolve()
        if 'infrastructure_errors' in sys.modules:
            if Path(sys.modules['infrastructure_errors'].__file__).resolve()!=error_path:
                raise AdmissionError('unexpected transport error helper module')
        else:
            error_spec=importlib.util.spec_from_file_location('infrastructure_errors',error_path)
            error_module=importlib.util.module_from_spec(error_spec)
            error_spec.loader.exec_module(error_module)
            sys.modules['infrastructure_errors']=error_module
        code,_ = helper.transport_code((root/'scripts/direct_worker_transport.py').read_bytes(),52301)
        namespace={};exec(code,namespace)
        self.binding = namespace['WorkerBinding'](binding_path)
        self.send = namespace['request']
        with Path(value['weights']).open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest() != expected_weights_sha256:
                raise AdmissionError('registered model weights changed')
        self.check_identity()

    def _send(self,route,body,timeout):
        raw = json.dumps(body,sort_keys=True,ensure_ascii=False).encode('utf-8') if body is not None else None
        return self.send(self.binding,route,raw,timeout)

    def check_identity(self):
        props=self._send('/props',None,30)
        self.binding.check_model(self._send('/v1/models',None,30),props)
        if props.get('build_info')!='b10894-d344123fe':
            raise AdmissionError('registered native worker build changed')

    def __call__(self,route,body,timeout):
        if route not in self.ROUTES:
            raise AdmissionError('endpoint outside read-only helpers and registered generation')
        if route=='/v1/chat/completions':self.check_identity()
        return self._send(route,body,timeout)


class NativeToolModel:
    """Use the real upstream tool parser/formatter, never its retry/paid backend.

    `transport` must be separately admitted, process/weights-bound loopback-only
    transport. Every request is single-attempt. Limits apply before generation;
    context never silently drops earlier messages or tool evidence.
    """
    def __init__(self, transport, out, upstream, limits, observation_template, metadata, *, deadline=None):
        self.transport, self.out, self.upstream = transport, Path(out), upstream
        self.limits, self.observation_template = limits, observation_template
        self.metadata = dict(metadata)
        self.deadline = deadline
        self.n_calls, self.tokens = 0, 0
        self.unknown_usage = 0
        self.halted = False
        self.out.mkdir(parents=True, exist_ok=False)
        self.events = []

    def _timeout(self):
        timeout = self.limits.timeout
        if self.deadline is not None:
            timeout = min(timeout, self.deadline-time.monotonic())
        if timeout <= 0:
            raise AdmissionError('task wall budget exhausted; no further request')
        return timeout

    def format_message(self, **kwargs):
        return kwargs

    def get_template_vars(self):
        return dict(model_name='qwen3.8-27b')

    def serialize(self):
        return dict(info=dict(config=dict(model=dict(model_name='qwen3.8-27b',
            provider='single-attempt-bound-loopback', native_usage_only=True)),
            native_usage=dict(calls=self.n_calls, known_tokens_lower_bound=self.tokens,
                              usage_unknown=self.unknown_usage)))

    def query(self, messages):
        if self.halted:
            raise AdmissionError('provider already halted; no retry or next request')
        if self.n_calls >= self.limits.maximum_calls:
            raise AdmissionError('registered model call cap reached')
        prepared = [{k:v for k,v in msg.items() if k != 'extra'} for msg in messages]
        # Same native sampling/seed for every registered arm; no secrets, SDK
        # provider fallback, retry, prompt cache mutation or service control.
        request = dict(model='qwen3.8-27b', messages=prepared, tools=[self.upstream.tool],
            tool_choice='required', parallel_tool_calls=False, temperature=.6, top_p=.95,
            top_k=20, min_p=0., presence_penalty=0., repeat_penalty=1., seed=self.limits.seed,
            max_tokens=self.limits.output, cache_prompt=False, chat_template_kwargs=dict(enable_thinking=False))
        try:
            if any(s.get('is_processing') for s in self.transport('/slots', None, self._timeout())):
                raise AdmissionError('worker busy; no inference overlap')
            prompt = self.transport('/apply-template', {key:request[key] for key in
                ('messages','tools','tool_choice','parallel_tool_calls','chat_template_kwargs')}, self._timeout())['prompt']
            tokens = self.transport('/tokenize', dict(content=prompt, add_special=False), self._timeout())['tokens']
            if len(tokens)+self.limits.output > self.limits.context:
                raise AdmissionError('context cap; do not truncate evidence/history')
            if self.tokens+len(tokens)+self.limits.output > self.limits.native_token_cap:
                raise AdmissionError('reserved native token cap reached')
            generation_timeout = self._timeout()
        except BaseException as exc:
            self.halted = True
            write_exclusive(self.out/f'before-call-{self.n_calls:04}.json',dict(request=request,
                metadata=self.metadata, generation_requests_started=0,error=repr(exc),
                infrastructure_evidence=getattr(exc,'evidence',None)))
            raise
        path = self.out/f'call-{self.n_calls:04}.json'
        record = dict(request=request, metadata=self.metadata, usage=None, usage_validated=False, unknown_reason='request_pending',
            preflight_input_tokens=len(tokens), started_at=time.time())
        write_exclusive(path, record)
        self.n_calls += 1
        result = None
        original_error = None
        try:
            response = self.transport('/v1/chat/completions', request, generation_timeout)
            record['response'] = response
            if not isinstance(response, dict):
                raise AdmissionError('native response is not an object')
            record['usage'] = response.get('usage')
            record['unknown_reason'] = None if response.get('usage') else 'native_usage_missing'
            try:
                usage = native_usage(response)
            except AdmissionError:
                record['unknown_reason'] = 'native_usage_invalid_or_missing'
                raise
            record['usage_validated'] = True
            self.tokens += usage['total_tokens']
            # Parse boundary (fuzz battery, tests/test_adapter_fuzz.py):
            # every malformed shape in the response's interpretation —
            # missing or mistyped choices/message/tool_calls, a tool
            # call entry of the wrong shape, or any error the upstream
            # parser raises — fails closed as AdmissionError, the
            # adapter's named outcome. Nothing unnamed escapes.
            try:
                if response.get('model') != 'qwen3.8-27b':
                    raise AdmissionError('native model identity changed')
                choice = response['choices'][0]
                if choice['finish_reason'] != 'tool_calls':
                    raise AdmissionError('native response did not complete a tool call')
                message = choice['message']
                raw_calls = message.get('tool_calls') or []
                if len(raw_calls) != 1:
                    raise AdmissionError('exactly one native action required')
                calls = [SimpleNamespace(id=c['id'], function=SimpleNamespace(**c['function'])) for c in raw_calls]
                actions = self.upstream.parse(calls, format_error_template='{{error}}',
                    template_kwargs=dict(finish_reason=choice['finish_reason']))
                if len(actions) != 1 or not isinstance(actions[0].get('command'), str) or not actions[0]['command'].strip():
                    raise AdmissionError('empty or invalid native command')
                result = {**message, 'extra':dict(actions=actions, response=response, cost=0.,
                    cost_boundary='Local API spend0; no hardware/energy/labor valuation', native_usage=usage,
                    receipt=str(path))}
            except AdmissionError:
                raise
            except Exception as exc:
                raise AdmissionError(f'native response did not parse: {exc!r}') from exc
            return result
        except BaseException as exc:
            original_error = exc
            self.halted = True
            record.update(error=repr(exc), infrastructure_evidence=getattr(exc,'evidence',None))
            if record.get('usage') is None: record['unknown_reason']='failed_request_usage_unknown'
            raise
        finally:
            record['ended_at'] = time.time()
            self.unknown_usage += int(not record['usage_validated'])
            # This updates only the receipt created above; never an old episode.
            try:
                # Deliberately NOT the verified writer (2026-10-28
                # audit): this finally-block rewrite is half of an
                # exception-composition contract — a persistence
                # failure here must surface alongside the original
                # failure as a BaseExceptionGroup, and the maintained
                # tests inject failure at Path.write_text. The
                # receipt is hashed from disk immediately below, so
                # what landed is what is pinned.
                path.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            except BaseException as persistence_error:
                self.halted = True
                if original_error is not None:
                    raise BaseExceptionGroup('Original model failure and receipt persistence failure',
                        [original_error,persistence_error])
                raise
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.events.append(dict(path=str(path),sha256=digest))
            if result is not None:
                result['extra']['receipt_sha256'] = digest

    def format_observation_messages(self, message, outputs, template_vars=None):
        return self.upstream.observe(actions=message['extra']['actions'], outputs=outputs,
            observation_template=self.observation_template,template_vars=template_vars)


class ReceiptEnvironment:
    """Retain actual upstream executions and halt on the first failed tool.

    The underlying DockerEnvironment and its fixed unprivileged interpreter
    remain unchanged. Trusted setup, isolation and owned cleanup are external.
    """
    def __init__(self, upstream_environment, out, system_information):
        self.env, self.out = upstream_environment, Path(out)
        self.system_information = dict(system_information)
        self.out.mkdir(parents=True, exist_ok=False)
        self.events, self.halted = [], False

    def get_template_vars(self, **kwargs):
        # Upstream uses host uname on Windows, although commands run in Linux.
        # Require the controller's separately observed container uname instead.
        return {**self.env.config.model_dump(), **kwargs, **self.system_information}

    def serialize(self):
        return {**self.env.serialize(), 'tool_receipts':self.events}

    def execute(self, action, cwd='', *, timeout=None):
        if self.halted:
            raise ToolFailure('environment already halted; no next action')
        path = self.out / f'action-{len(self.events):04}.json'
        record = dict(action=action, started_at=time.time())
        write_exclusive(path, record)
        original_error = None
        try:
            output = self.env.execute(action, cwd, timeout=timeout)
            record['output'] = output
            if output.get('returncode') != 0 or output.get('exception_info'):
                self.halted = True
                raise ToolFailure('first tool failure; retained output, no next action')
            return output
        except BaseException as exc:
            original_error = exc
            # The original upstream environment raises Submitted only after its
            # actual command returns0 and its first output line is the sentinel.
            # It is a proposal, not independent correctness/acceptance evidence.
            if type(exc).__name__ == 'Submitted' and type(exc).__module__ == 'minisweagent.exceptions':
                record['upstream_submission'] = exc.messages
                self.halted = True
            else:
                self.halted = True
                record['error'] = repr(exc)
            raise
        finally:
            record['ended_at'] = time.time()
            try:
                # Deliberately NOT the verified writer: see the
                # model-call receipt above (exception-composition
                # contract; hashed from disk below).
                path.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            except BaseException as persistence_error:
                self.halted = True
                if original_error is not None:
                    raise BaseExceptionGroup('Original tool/submission event and receipt persistence failure',
                                             [original_error,persistence_error])
                raise
            self.events.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

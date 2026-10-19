"""Prospective, fail-closed campaign supervision; never retries or changes caps."""
import json
import time
import sys
from pathlib import Path


class RuntimeIntervention(RuntimeError):
    def __init__(self,reason,*,alert=None):
        super().__init__(reason)
        self.alert=alert


def validate_capacity(seconds, timeout, phases, repair_rounds):
    needed = (len(phases) + repair_rounds) * timeout
    if seconds < needed:
        raise ValueError(f'infeasible workflow budget: {seconds}s < {needed}s minimum '
                         'request reservations for phases and repair')


class RuntimeWatchdog:
    def __init__(self, folder, capture=None, max_errors=3, max_repeat=3, *, fail_fast=False):
        self.folder = Path(folder)
        self.capture = capture
        self.max_errors, self.max_repeat = max_errors, max_repeat
        self.fail_fast = fail_fast
        if fail_fast:
            self.max_errors, self.max_repeat = 1, 2
        self.errors = self.repeats = 0
        self.last_tool = None
        self.recent = []

    def stop(self, reason, **context):
        alert = dict(status='intervention_required', reason=reason, **context,
                     policy='stop; retain evidence; no retry, budget extension or treatment change')
        if self.capture:
            try:
                self.capture()
            except Exception as exc:
                alert['snapshot_error'] = repr(exc)
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder/'runtime-alert.json').write_text(json.dumps(alert, indent=2)+'\n', encoding='utf-8')
        except (OSError,ValueError,TypeError) as exc:
            alert['alert_write_error']=repr(exc)
            # Best effort only: storage failure cannot guarantee durable bytes.
            try:
                print(json.dumps({key:alert[key] for key in
                    ('reason','error','snapshot_error','alert_write_error') if key in alert}),file=sys.stderr)
            except OSError:
                pass
        raise RuntimeIntervention(reason,alert=alert)

    def deadline(self, end, timeout, phase, stage):
        if end-time.monotonic() < timeout:
            self.stop('insufficient capacity before phase', phase=phase, stage=stage)

    def error(self, exc, phase, stage):
        self.errors += 1
        self.recent = (self.recent+[False])[-10:]
        if isinstance(exc, TimeoutError) or any(s in str(exc) for s in (
                'token_cap', 'server_not_idle', 'ModelIdentityMismatch')):
            self.stop('runtime safety/budget failure', phase=phase, stage=stage, error=repr(exc))
        if isinstance(exc,OSError):
            self.stop('infrastructure/transport failure',phase=phase,stage=stage,error=repr(exc),
                      infrastructure_evidence=getattr(exc,'evidence',None))
        if self.errors >= self.max_errors:
            self.stop('consecutive action/transport failures', phase=phase, stage=stage,
                      consecutive_errors=self.errors, error=repr(exc))
        if len(self.recent) == 10 and self.recent.count(False) > 5:
            self.stop('action protocol error rate exceeds 50 percent of last ten actions',
                      phase=phase, stage=stage)

    def success(self):
        self.errors = 0
        self.recent = (self.recent+[True])[-10:]

    def tool(self, command, result, phase, stage):
        # Repeated identical observations with an identical action are a loop,
        # even when a read-only command exits successfully. No source is inferred.
        from hashlib import sha256
        key = sha256(json.dumps([command, result], sort_keys=True).encode()).hexdigest()
        if self.fail_fast and (type(result.get('exit_code')) is not int or result['exit_code'] != 0):
            self.stop('tool execution failed; campaign halted', phase=phase, stage=stage,
                      exit_code=result.get('exit_code'), action_observation_sha256=key)
        self.repeats = self.repeats+1 if key == self.last_tool else 1
        self.last_tool = key
        if self.repeats >= self.max_repeat:
            self.stop('repeated identical action without changed observation', phase=phase,
                      stage=stage, repeated_actions=self.repeats, action_observation_sha256=key)

    def completed(self, result, stage):
        if not result['completed'] or any(e.startswith('TerminalActionCoerced:') for e in result['errors']):
            self.stop('phase did not complete; downstream execution withheld', stage=stage,
                      phase=result['phase'], calls=result['calls'], errors=result['errors'])

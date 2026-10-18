"""Prospective, fail-closed campaign supervision; never retries or changes caps."""
import json
import time
from pathlib import Path


class RuntimeIntervention(RuntimeError):
    pass


def validate_capacity(seconds, timeout, phases, repair_rounds):
    needed = (len(phases) + repair_rounds) * timeout
    if seconds < needed:
        raise ValueError(f'infeasible workflow budget: {seconds}s < {needed}s minimum '
                         'request reservations for phases and repair')


class RuntimeWatchdog:
    def __init__(self, folder, capture=None, max_errors=3, max_repeat=3):
        self.folder = Path(folder)
        self.capture = capture
        self.max_errors, self.max_repeat = max_errors, max_repeat
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
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder/'runtime-alert.json').write_text(json.dumps(alert, indent=2)+'\n', encoding='utf-8')
        raise RuntimeIntervention(reason)

    def deadline(self, end, timeout, phase, stage):
        if end-time.monotonic() < timeout:
            self.stop('insufficient capacity before phase', phase=phase, stage=stage)

    def error(self, exc, phase, stage):
        self.errors += 1
        self.recent = (self.recent+[False])[-10:]
        if isinstance(exc, TimeoutError) or any(s in str(exc) for s in (
                'token_cap', 'server_not_idle', 'ModelIdentityMismatch')):
            self.stop('runtime safety/budget failure', phase=phase, stage=stage, error=repr(exc))
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
        self.repeats = self.repeats+1 if key == self.last_tool else 1
        self.last_tool = key
        if self.repeats >= self.max_repeat:
            self.stop('repeated identical action without changed observation', phase=phase,
                      stage=stage, repeated_actions=self.repeats, action_observation_sha256=key)

    def completed(self, result, stage):
        if not result['completed'] or any(e.startswith('TerminalActionCoerced:') for e in result['errors']):
            self.stop('phase did not complete; downstream execution withheld', stage=stage,
                      phase=result['phase'], calls=result['calls'], errors=result['errors'])

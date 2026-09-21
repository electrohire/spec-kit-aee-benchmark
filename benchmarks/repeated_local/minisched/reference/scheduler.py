from .config import SchedulerConfig
from .store import JobStore


class Scheduler:
    def __init__(self, store=None, config=None):
        self.store = store if store is not None else JobStore()
        self.config = config if config is not None else SchedulerConfig()

    def enqueue(self, payload):
        return self.store.add(payload)

    def run_next(self):
        pending = self.store.list_pending()
        if not pending:
            return None
        job_id = pending[0]["id"]
        record = self.store.get(job_id)
        try:
            result = self._execute(record["payload"])
        except Exception:
            attempts = record["attempts"] + 1
            if attempts > self.config.max_retries:
                self.store.update(job_id, status="failed", attempts=attempts)
                return {"id": job_id, "status": "failed", "attempts": attempts}
            self.store.update(job_id, attempts=attempts)
            return {"id": job_id, "status": "retried", "attempts": attempts}
        self.store.update(job_id, status="done")
        return {"id": job_id, "status": "done", "result": result}

    @staticmethod
    def _execute(payload):
        fn = payload.get("fn") if isinstance(payload, dict) else None
        if not callable(fn):
            raise ValueError("payload must be a dict carrying a callable 'fn'")
        return fn()

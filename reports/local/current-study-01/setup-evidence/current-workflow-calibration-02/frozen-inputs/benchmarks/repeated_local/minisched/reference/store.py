from copy import deepcopy


class JobStore:
    def __init__(self):
        self._jobs = {}
        self._next_id = 1

    def add(self, payload):
        job_id = self._next_id
        self._next_id += 1
        self._jobs[job_id] = {"id": job_id, "payload": deepcopy(payload),
                              "status": "pending", "attempts": 0}
        return job_id

    def get(self, job_id):
        record = self._jobs.get(job_id)
        return deepcopy(record) if record is not None else None

    def update(self, job_id, **fields):
        if job_id not in self._jobs:
            raise KeyError(job_id)
        self._jobs[job_id].update(deepcopy(fields))

    def list_pending(self):
        return [deepcopy(record) for record in self._jobs.values()
                if record["status"] == "pending"]

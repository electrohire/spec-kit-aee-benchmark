class SchedulerConfig:
    DEFAULT_MAX_RETRIES = 3
    MAX_RETRY_BASE_SECONDS = 3600

    def __init__(self, max_retries=None, retry_base_seconds=None):
        self.max_retries = self.DEFAULT_MAX_RETRIES if max_retries is None else max_retries
        self.retry_base_seconds = 1 if retry_base_seconds is None else retry_base_seconds
        self.validate()

    def validate(self):
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise ValueError("max_retries must be an int")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if isinstance(self.retry_base_seconds, bool) or not isinstance(
                self.retry_base_seconds, (int, float)):
            raise ValueError("retry_base_seconds must be a number")
        if not 0 < self.retry_base_seconds <= self.MAX_RETRY_BASE_SECONDS:
            raise ValueError("retry_base_seconds out of range (0, 3600]")

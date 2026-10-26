class JobQueueNotConfiguredError(RuntimeError):
    """Raised until a Redis job queue is configured."""


class JobQueueUnavailableError(RuntimeError):
    """Raised when Redis cannot confirm a job enqueue operation."""


class UnsupportedJobKindError(ValueError):
    """Raised when a job kind has no configured Redis List route."""

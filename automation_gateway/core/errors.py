class PublisherNotConfiguredError(RuntimeError):
    """Raised until a concrete status publisher is configured."""


class PublisherUnavailableError(RuntimeError):
    """Raised when the configured destination rejects or cannot receive a publication."""


class PublisherTimeoutError(PublisherUnavailableError):
    """Raised when publication exceeds the configured timeout."""

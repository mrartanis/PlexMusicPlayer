"""Domain-facing error categories."""


class DomainError(Exception):
    """Base class for project-specific domain errors."""


class AuthError(DomainError):
    """Authentication or session lifecycle failure."""


class NetworkError(DomainError):
    """Network interaction failure exposed to application code."""


class TrackUnavailableError(DomainError):
    """Track cannot be played in the current context."""


class StreamResolveError(DomainError):
    """Playable stream reference could not be resolved."""


class PlaybackBackendError(DomainError):
    """Playback backend could not perform the requested action."""


class StorageError(DomainError):
    """Persistent storage failed or returned invalid data."""

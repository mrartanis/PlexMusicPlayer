from __future__ import annotations

from app.domain.errors import (
    AuthError,
    DomainError,
    NetworkError,
    PlaybackBackendError,
    StorageError,
    StreamResolveError,
    TrackUnavailableError,
)


def user_facing_error_message(error: DomainError) -> str:
    if isinstance(error, AuthError):
        return "Authentication is required. Sign in again and retry."
    if isinstance(error, NetworkError):
        return "Plex request failed. Check the connection and retry."
    if isinstance(error, TrackUnavailableError):
        return "This track is unavailable."
    if isinstance(error, StreamResolveError):
        return "Could not prepare this track for playback."
    if isinstance(error, PlaybackBackendError):
        return "Playback failed. Check the logs for backend details."
    if isinstance(error, StorageError):
        return "Local app data could not be read or written. Check the logs for details."
    return "Operation failed. Check the logs for details."

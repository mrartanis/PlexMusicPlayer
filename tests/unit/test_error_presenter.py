from __future__ import annotations

from app.application.error_presenter import user_facing_error_message
from app.domain.errors import (
    AuthError,
    NetworkError,
    PlaybackBackendError,
    StorageError,
    StreamResolveError,
    TrackUnavailableError,
)


def test_user_facing_error_message_hides_raw_exception_details() -> None:
    raw_token = "secret-token"

    assert raw_token not in user_facing_error_message(AuthError(f"bad token {raw_token}"))
    assert raw_token not in user_facing_error_message(NetworkError(f"failed {raw_token}"))
    assert raw_token not in user_facing_error_message(StorageError(f"path {raw_token}"))


def test_user_facing_error_message_maps_domain_categories() -> None:
    assert user_facing_error_message(AuthError("raw")).startswith("Authentication")
    assert user_facing_error_message(NetworkError("raw")).startswith("Plex")
    assert user_facing_error_message(TrackUnavailableError("raw")) == "This track is unavailable."
    assert user_facing_error_message(StreamResolveError("raw")).startswith("Could not prepare")
    assert user_facing_error_message(PlaybackBackendError("raw")).startswith("Playback failed")

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain import (
    Album,
    Artist,
    AuthSession,
    CatalogSearchResults,
    PlaybackState,
    PlaybackStatus,
    Playlist,
    QueueItem,
    RepeatMode,
    Track,
)


def test_track_is_frozen_and_typed() -> None:
    track = Track(
        id="track-1",
        title="Signal",
        artists=("Artist A", "Artist B"),
        album_title="Album",
        duration_ms=180_000,
        stream_ref="stream-1",
        artwork_ref="art-1",
    )

    assert track.artists == ("Artist A", "Artist B")
    assert track.available is True

    with pytest.raises(FrozenInstanceError):
        track.title = "Other"


def test_playlist_and_queue_item_hold_metadata_without_behavior() -> None:
    track = Track(id="track-2", title="Queue Item", artists=("Artist",))
    playlist = Playlist(
        id="playlist-1",
        title="Daily Mix",
        owner_name="PLEX_MUSIC_PLAYER",
        track_count=25,
    )
    queue_item = QueueItem(
        track=track,
        source_type="playlist",
        source_id=playlist.id,
        source_index=3,
    )

    assert playlist.title == "Daily Mix"
    assert queue_item.source_type == "playlist"
    assert queue_item.source_index == 3


def test_catalog_entities_group_search_results() -> None:
    track = Track(id="track-1", title="Track", artists=("Artist",))
    album = Album(id="album-1", title="Album", artists=("Artist",), year=2024)
    single = Album(id="single-1", title="Single", release_type="single")
    compilation = Album(id="compilation-1", title="Compilation", release_type="compilation")
    artist = Artist(id="artist-1", name="Artist")
    playlist = Playlist(id="playlist-1", title="Playlist")

    results = CatalogSearchResults(
        tracks=(track,),
        albums=(album,),
        singles=(single,),
        compilations=(compilation,),
        artists=(artist,),
        playlists=(playlist,),
    )

    assert results.tracks == (track,)
    assert results.albums[0].year == 2024
    assert results.singles[0].release_type == "single"
    assert results.compilations[0].release_type == "compilation"
    assert results.artists[0].name == "Artist"


def test_playback_state_uses_bounded_enums() -> None:
    state = PlaybackState(
        status=PlaybackStatus.PLAYING,
        active_index=1,
        position_ms=15_000,
        duration_ms=180_000,
        volume=75,
        shuffle_enabled=True,
        repeat_mode=RepeatMode.ALL,
    )

    assert state.status is PlaybackStatus.PLAYING
    assert state.repeat_mode is RepeatMode.ALL
    assert state.shuffle_enabled is True


def test_auth_session_keeps_expiration_optional_and_explicit() -> None:
    session = AuthSession(
        user_id="user-1",
        token="token-value",
        expires_at=datetime(2026, 4, 20, tzinfo=UTC),
        display_name="Artem",
    )

    assert session.user_id == "user-1"
    assert session.display_name == "Artem"

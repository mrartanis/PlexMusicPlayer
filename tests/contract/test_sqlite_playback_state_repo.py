from __future__ import annotations

import sqlite3

import pytest

from app.domain import QueueItem, SavedPlaybackQueue, StorageError, Track
from app.infrastructure.persistence.sqlite_playback_state_repo import SQLitePlaybackStateRepo


def test_sqlite_playback_state_repo_round_trips_queue(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")
    queue = (
        QueueItem(
            track=Track(
                id="track-1",
                title="Signal",
                artists=("Artist",),
                version="Live Version",
                album_title="Album",
                album_year=2024,
                duration_ms=123_000,
                stream_ref="https://temporary-stream.example/track-1",
                artwork_ref="covers/track.jpg",
                is_liked=True,
            ),
            source_type="album",
            source_id="album-1",
            source_index=0,
            station_batch_id="batch-1",
            radio_session_id="session-1",
            radio_origin="radio-mobile-user-onyourwave-default",
            radio_queue_anchor_track_id="track-1",
        ),
    )

    repo.save_playback_queue(queue, active_index=0, position_ms=45_000)

    assert repo.load_playback_queue() == SavedPlaybackQueue(
        queue=(
            QueueItem(
                track=Track(
                    id="track-1",
                    title="Signal",
                    artists=("Artist",),
                    version="Live Version",
                    album_title="Album",
                    album_year=2024,
                    duration_ms=123_000,
                    stream_ref=None,
                    artwork_ref="covers/track.jpg",
                    is_liked=True,
                ),
                source_type="album",
                source_id="album-1",
                source_index=0,
                station_batch_id="batch-1",
                radio_session_id="session-1",
                radio_origin="radio-mobile-user-onyourwave-default",
                radio_queue_anchor_track_id="track-1",
            ),
        ),
        active_index=0,
        position_ms=45_000,
    )


def test_sqlite_playback_state_repo_returns_none_when_missing(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")

    assert repo.load_playback_queue() is None


def test_sqlite_playback_state_repo_clears_queue(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")
    repo.save_playback_queue(
        (QueueItem(track=Track(id="track-1", title="Signal", artists=("Artist",))),),
        active_index=0,
    )

    repo.clear_playback_queue()

    assert repo.load_playback_queue() is None


def test_sqlite_playback_state_repo_rejects_invalid_payload(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLitePlaybackStateRepo(db_path=path)
    del repo
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into playback_queue(id, queue_json, active_index, updated_at) "
                "values (1, ?, ?, ?)"
            ),
            ("{}", 0, "2026-04-22T12:00:00+00:00"),
        )

    repo = SQLitePlaybackStateRepo(db_path=path)
    with pytest.raises(StorageError):
        repo.load_playback_queue()


def test_sqlite_playback_state_repo_reads_legacy_queue_json_payload(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLitePlaybackStateRepo(db_path=path)
    del repo
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into playback_queue(id, queue_json, active_index, position_ms, updated_at) "
                "values (1, ?, ?, ?, ?)"
            ),
            (
                (
                    '[{"track":{"id":"legacy-1","title":"Legacy","artists":["Artist"],'
                    '"album_title":"Album","duration_ms":180000,"available":true,"is_liked":true},'
                    '"source_type":"album","source_id":"album-1","source_index":0}]'
                ),
                0,
                12_000,
                "2026-04-22T12:00:00+00:00",
            ),
        )

    repo = SQLitePlaybackStateRepo(db_path=path)

    assert repo.load_playback_queue() == SavedPlaybackQueue(
        queue=(
            QueueItem(
                track=Track(
                    id="legacy-1",
                    title="Legacy",
                    artists=("Artist",),
                    album_title="Album",
                    duration_ms=180_000,
                    stream_ref=None,
                    is_liked=True,
                ),
                source_type="album",
                source_id="album-1",
                source_index=0,
            ),
        ),
        active_index=0,
        position_ms=12_000,
    )

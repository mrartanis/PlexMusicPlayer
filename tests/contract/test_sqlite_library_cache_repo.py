from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from app.domain import Album, Artist, CatalogSearchResults
from app.domain.playlist import Playlist
from app.domain.track import LikedTrackIds, LikedTrackSnapshot, Track
from app.infrastructure.persistence.sqlite_library_cache_repo import SQLiteLibraryCacheRepo


def test_sqlite_library_cache_repo_round_trips_recent_searches(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")

    repo.save_recent_searches(("ambient", "jazz"))

    assert repo.load_recent_searches() == ("ambient", "jazz")


def test_sqlite_library_cache_repo_round_trips_track_metadata_and_artwork(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    track = Track(
        id="track-1",
        title="Signal",
        artists=("Artist",),
        version="Live Version",
        album_title="Album",
        album_year=2024,
        duration_ms=123_000,
        stream_ref="stream",
        artwork_ref="covers/track.jpg",
        waveform_bins=(0.1, 0.3, 0.6),
        is_liked=True,
    )

    repo.save_track_metadata(track)
    repo.save_artwork_ref(track.id, "covers/track.jpg")

    assert repo.load_track_metadata("track-1") == track
    assert repo.load_artwork_ref("track-1") == "covers/track.jpg"


def test_sqlite_library_cache_repo_round_trips_catalog_search(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    results = CatalogSearchResults(
        tracks=(Track(id="track-1", title="Signal", artists=("Artist",)),),
        albums=(Album(id="album-1", title="Album", artists=("Artist",)),),
        artists=(Artist(id="artist-1", name="Artist", artwork_ref="covers/artist.jpg"),),
        playlists=(Playlist(id="playlist-1", title="Playlist"),),
    )

    repo.save_catalog_search("Ambient", results)

    assert repo.load_catalog_search("ambient") == results


def test_sqlite_library_cache_repo_round_trips_liked_track_ids(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    liked_tracks = LikedTrackIds(
        user_id="user-1",
        revision=42,
        track_ids=frozenset({"track-1", "track-2"}),
    )

    repo.save_liked_track_ids(liked_tracks)
    repo.mark_track_liked("user-1", "track-3:album-1")
    repo.mark_track_unliked("user-1", "track-2")

    loaded = repo.load_liked_track_ids("user-1")

    assert loaded is not None
    assert loaded.user_id == "user-1"
    assert loaded.revision == 42
    assert loaded.track_ids == frozenset({"track-1", "track-3:album-1"})


def test_sqlite_library_cache_repo_round_trips_liked_track_snapshot(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    snapshot = LikedTrackSnapshot(
        user_id="user-1",
        revision=42,
        tracks=(
            Track(id="track-1", title="Signal", artists=("Artist",), is_liked=True),
            Track(id="track-2", title="Pulse", artists=("Artist",), is_liked=True),
        ),
    )

    repo.save_liked_track_snapshot(snapshot)

    assert repo.load_liked_track_snapshot("user-1") == snapshot


def test_sqlite_library_cache_repo_returns_empty_when_missing(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")

    assert repo.load_recent_searches() == ()
    assert repo.load_catalog_search("ambient") is None
    assert repo.load_track_metadata("missing") is None
    assert repo.load_liked_track_ids("user-1") is None
    assert repo.load_liked_track_snapshot("user-1") is None
    assert repo.load_artwork_ref("missing") is None


def test_sqlite_library_cache_repo_expires_track_metadata_before_artwork_refs(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLiteLibraryCacheRepo(db_path=path)
    expired_at = (datetime.now(tz=UTC) - timedelta(days=8)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into tracks("
                "id, title, artists_json, available, is_liked, cached_at"
                ") values (?, ?, ?, ?, ?, ?)"
            ),
            ("track-1", "Signal", '["Artist"]', 1, 0, expired_at),
        )
        connection.execute(
            "insert into artwork(item_id, artwork_ref, cached_at) values (?, ?, ?)",
            ("track-1", "covers/track.jpg", expired_at),
        )

    assert repo.load_track_metadata("track-1") is None
    assert repo.load_artwork_ref("track-1") == "covers/track.jpg"


def test_sqlite_library_cache_repo_expires_artwork_refs_after_month(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLiteLibraryCacheRepo(db_path=path)
    expired_at = (datetime.now(tz=UTC) - timedelta(days=31)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "insert into artwork(item_id, artwork_ref, cached_at) values (?, ?, ?)",
            ("track-1", "covers/track.jpg", expired_at),
        )

    assert repo.load_artwork_ref("track-1") is None


def test_sqlite_library_cache_repo_expires_catalog_search_after_hour(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLiteLibraryCacheRepo(db_path=path)
    expired_at = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into catalog_search_cache(query, data_json, cached_at) "
                "values (?, ?, ?)"
            ),
            (
                "ambient",
                (
                    '{"tracks":[{"id":"track-1","title":"Signal","artists":["Artist"]}],'
                    '"albums":[],"singles":[],"compilations":[],"artists":[],"playlists":[]}'
                ),
                expired_at,
            ),
        )

    assert repo.load_catalog_search("ambient") is None

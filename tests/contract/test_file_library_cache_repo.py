from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Album, Artist, CatalogSearchResults, StorageError
from app.domain.playlist import Playlist
from app.domain.track import LikedTrackIds, LikedTrackSnapshot, Track
from app.infrastructure.persistence.file_library_cache_repo import FileLibraryCacheRepo


def test_file_library_cache_repo_round_trips_recent_searches(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "recent.json")

    repo.save_recent_searches(("ambient", "jazz"))

    assert repo.load_recent_searches() == ("ambient", "jazz")


def test_file_library_cache_repo_round_trips_track_metadata_and_artwork(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "library.json")
    track = Track(
        id="track-1",
        title="Signal",
        artists=("Artist",),
        version="Live Version",
        album_title="Album",
        album_year=2024,
        duration_ms=123_000,
        artwork_ref="covers/track.jpg",
        waveform_bins=(0.1, 0.3, 0.6),
        is_liked=True,
    )

    repo.save_track_metadata(track)
    repo.save_artwork_ref(track.id, "covers/track.jpg")

    assert repo.load_track_metadata("track-1") == track
    assert repo.load_artwork_ref("track-1") == "covers/track.jpg"


def test_file_library_cache_repo_round_trips_catalog_search(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "library.json")
    results = CatalogSearchResults(
        tracks=(Track(id="track-1", title="Signal", artists=("Artist",)),),
        albums=(Album(id="album-1", title="Album", artists=("Artist",)),),
        artists=(Artist(id="artist-1", name="Artist", artwork_ref="covers/artist.jpg"),),
        playlists=(Playlist(id="playlist-1", title="Playlist"),),
    )

    repo.save_catalog_search("Ambient", results)

    assert repo.load_catalog_search("ambient") == results


def test_file_library_cache_repo_round_trips_liked_track_ids(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "library.json")
    liked_tracks = LikedTrackIds(
        user_id="user-1",
        revision=7,
        track_ids=frozenset({"track-1", "track-2"}),
    )

    repo.save_liked_track_ids(liked_tracks)
    repo.mark_track_liked("user-1", "track-3")
    repo.mark_track_unliked("user-1", "track-2")

    loaded = repo.load_liked_track_ids("user-1")

    assert loaded is not None
    assert loaded.user_id == "user-1"
    assert loaded.revision == 7
    assert loaded.track_ids == frozenset({"track-1", "track-3"})


def test_file_library_cache_repo_round_trips_liked_track_snapshot(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "library.json")
    snapshot = LikedTrackSnapshot(
        user_id="user-1",
        revision=7,
        tracks=(
            Track(id="track-1", title="Signal", artists=("Artist",), is_liked=True),
        ),
    )

    repo.save_liked_track_snapshot(snapshot)

    assert repo.load_liked_track_snapshot("user-1") == snapshot


def test_file_library_cache_repo_expires_track_metadata_before_artwork_refs(tmp_path) -> None:
    path = tmp_path / "library.json"
    expired_at = (datetime.now(tz=UTC) - timedelta(days=8)).isoformat()
    payload = {
        "recent_searches": [],
        "tracks": {
            "track-1": {
                "id": "track-1",
                "title": "Signal",
                "artists": ["Artist"],
                "cached_at": expired_at,
            }
        },
        "artwork": {
            "track-1": {
                "ref": "covers/track.jpg",
                "cached_at": expired_at,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    assert repo.load_track_metadata("track-1") is None
    assert repo.load_artwork_ref("track-1") == "covers/track.jpg"


def test_file_library_cache_repo_expires_artwork_refs_after_month(tmp_path) -> None:
    path = tmp_path / "library.json"
    expired_at = (datetime.now(tz=UTC) - timedelta(days=31)).isoformat()
    payload = {
        "recent_searches": [],
        "tracks": {},
        "artwork": {
            "track-1": {
                "ref": "covers/track.jpg",
                "cached_at": expired_at,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    assert repo.load_artwork_ref("track-1") is None


def test_file_library_cache_repo_returns_empty_when_missing(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "missing.json")

    assert repo.load_recent_searches() == ()
    assert repo.load_catalog_search("ambient") is None
    assert repo.load_liked_track_ids("user-1") is None
    assert repo.load_liked_track_snapshot("user-1") is None


def test_file_library_cache_repo_rejects_invalid_payload(tmp_path) -> None:
    path = tmp_path / "recent.json"
    path.write_text('{"bad": true}', encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    with pytest.raises(StorageError):
        repo.load_recent_searches()


def test_file_library_cache_repo_migrates_legacy_recent_searches_list(tmp_path) -> None:
    path = tmp_path / "recent.json"
    path.write_text('["ambient", "jazz"]', encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    assert repo.load_recent_searches() == ("ambient", "jazz")


def test_file_library_cache_repo_expires_catalog_search_after_hour(tmp_path) -> None:
    path = tmp_path / "library.json"
    expired_at = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat()
    payload = {
        "recent_searches": [],
        "tracks": {},
        "artwork": {},
        "catalog_search": {
            "ambient": {
                "results": {
                    "tracks": [{"id": "track-1", "title": "Signal", "artists": ["Artist"]}],
                    "albums": [],
                    "singles": [],
                    "compilations": [],
                    "artists": [],
                    "playlists": [],
                },
                "cached_at": expired_at,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    assert repo.load_catalog_search("ambient") is None

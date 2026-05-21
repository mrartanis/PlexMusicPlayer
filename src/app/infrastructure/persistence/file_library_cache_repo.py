from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.domain import (
    Album,
    Artist,
    CatalogSearchResults,
    LibraryCacheRepo,
    LikedTrackIds,
    LikedTrackSnapshot,
    Playlist,
    Track,
)
from app.domain.errors import StorageError


class FileLibraryCacheRepo(LibraryCacheRepo):
    _CACHE_TTL = timedelta(days=7)
    _ARTWORK_TTL = timedelta(days=30)
    _LIST_CACHE_TTL = timedelta(days=1)
    _SEARCH_CACHE_TTL = timedelta(hours=1)

    def __init__(self, *, file_path: Path) -> None:
        self._file_path = file_path

    def load_recent_searches(self) -> tuple[str, ...]:
        payload = self._load_payload()
        searches = payload.get("recent_searches", ())
        if not isinstance(searches, list) or not all(isinstance(item, str) for item in searches):
            raise StorageError("Library cache recent searches are invalid")
        return tuple(searches)

    def save_recent_searches(self, searches: tuple[str, ...] | list[str]) -> None:
        payload = self._load_payload()
        payload["recent_searches"] = list(searches)
        self._save_payload(payload)

    def load_catalog_search(self, query: str) -> CatalogSearchResults | None:
        payload = self._load_payload()
        raw_searches = payload.get("catalog_search", {})
        if not isinstance(raw_searches, dict):
            raise StorageError("Library cache catalog search map is invalid")
        raw_entry = raw_searches.get(self._normalize_search_query(query))
        if raw_entry is None:
            return None
        if not isinstance(raw_entry, dict):
            raise StorageError("Library cache catalog search entry is invalid")
        if self._is_expired(raw_entry.get("cached_at"), ttl=self._SEARCH_CACHE_TTL):
            return None
        return self._deserialize_catalog_search(raw_entry.get("results"))

    def save_catalog_search(self, query: str, results: CatalogSearchResults) -> None:
        payload = self._load_payload()
        raw_searches = payload.setdefault("catalog_search", {})
        if not isinstance(raw_searches, dict):
            raise StorageError("Library cache catalog search map is invalid")
        raw_searches[self._normalize_search_query(query)] = {
            "results": self._serialize_catalog_search(results),
            "cached_at": self._now_iso(),
        }
        self._save_payload(payload)

    def load_track_metadata(self, track_id: str) -> Track | None:
        payload = self._load_payload()
        tracks = payload.get("tracks", {})
        if not isinstance(tracks, dict):
            raise StorageError("Library cache track metadata is invalid")
        raw_track = tracks.get(track_id)
        if raw_track is None:
            return None
        if not isinstance(raw_track, dict):
            raise StorageError("Library cache track entry is invalid")
        if self._is_expired(raw_track.get("cached_at")):
            return None
        try:
            return Track(
                id=str(raw_track["id"]),
                title=str(raw_track["title"]),
                artists=tuple(str(artist) for artist in raw_track.get("artists", ())),
                version=self._optional_str(raw_track.get("version")),
                artist_ids=tuple(
                    str(artist_id) for artist_id in raw_track.get("artist_ids", ())
                ),
                album_id=self._optional_str(raw_track.get("album_id")),
                album_title=self._optional_str(raw_track.get("album_title")),
                album_year=self._optional_int(raw_track.get("album_year")),
                duration_ms=self._optional_int(raw_track.get("duration_ms")),
                stream_ref=self._optional_str(raw_track.get("stream_ref")),
                stream_ref_cached_at=self._optional_datetime(
                    raw_track.get("stream_ref_cached_at")
                ),
                artwork_ref=self._optional_str(raw_track.get("artwork_ref")),
                accent_color=self._optional_str(raw_track.get("accent_color")),
                waveform_bins=tuple(
                    float(value)
                    for value in raw_track.get("waveform_bins", ())
                    if isinstance(value, (int, float))
                ),
                available=bool(raw_track.get("available", True)),
                is_liked=bool(raw_track.get("is_liked", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError("Library cache track entry is invalid") from exc

    def save_track_metadata(self, track: Track) -> None:
        payload = self._load_payload()
        tracks = payload.setdefault("tracks", {})
        if not isinstance(tracks, dict):
            raise StorageError("Library cache track metadata is invalid")
        tracks[track.id] = {
            "id": track.id,
            "title": track.title,
            "artists": list(track.artists),
            "version": track.version,
            "artist_ids": list(track.artist_ids),
            "album_id": track.album_id,
            "album_title": track.album_title,
            "album_year": track.album_year,
            "duration_ms": track.duration_ms,
            "stream_ref": track.stream_ref,
            "stream_ref_cached_at": (
                track.stream_ref_cached_at.isoformat()
                if track.stream_ref_cached_at is not None
                else None
            ),
            "artwork_ref": track.artwork_ref,
            "accent_color": track.accent_color,
            "waveform_bins": [float(value) for value in track.waveform_bins],
            "available": track.available,
            "is_liked": track.is_liked,
            "cached_at": self._now_iso(),
        }
        self._save_payload(payload)

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None:
        payload = self._load_payload()
        liked_tracks = payload.get("liked_tracks", {})
        if not isinstance(liked_tracks, dict):
            raise StorageError("Library cache liked tracks are invalid")
        raw_state = liked_tracks.get(user_id)
        if raw_state is None:
            return None
        if not isinstance(raw_state, dict):
            raise StorageError("Library cache liked track entry is invalid")
        raw_ids = raw_state.get("track_ids", ())
        if not isinstance(raw_ids, list):
            raise StorageError("Library cache liked track ids are invalid")
        return LikedTrackIds(
            user_id=user_id,
            revision=int(raw_state.get("revision", 0) or 0),
            track_ids=frozenset(self._normalize_track_id(str(track_id)) for track_id in raw_ids),
        )

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None:
        payload = self._load_payload()
        raw_liked_tracks = payload.setdefault("liked_tracks", {})
        if not isinstance(raw_liked_tracks, dict):
            raise StorageError("Library cache liked tracks are invalid")
        raw_liked_tracks[liked_tracks.user_id] = {
            "revision": liked_tracks.revision,
            "track_ids": sorted(liked_tracks.track_ids),
            "synced_at": self._now_iso(),
        }
        self._save_payload(payload)

    def load_liked_track_snapshot(self, user_id: str) -> LikedTrackSnapshot | None:
        payload = self._load_payload()
        raw_snapshots = payload.get("liked_track_snapshots", {})
        if not isinstance(raw_snapshots, dict):
            raise StorageError("Library cache liked track snapshots are invalid")
        raw_snapshot = raw_snapshots.get(user_id)
        if raw_snapshot is None:
            return None
        if not isinstance(raw_snapshot, dict):
            raise StorageError("Library cache liked track snapshot entry is invalid")
        raw_tracks = raw_snapshot.get("tracks", ())
        if not isinstance(raw_tracks, list):
            raise StorageError("Library cache liked track snapshot tracks are invalid")
        tracks = tuple(self._deserialize_track(raw_track) for raw_track in raw_tracks)
        return LikedTrackSnapshot(
            user_id=user_id,
            revision=int(raw_snapshot.get("revision", 0) or 0),
            tracks=tracks,
        )

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot) -> None:
        payload = self._load_payload()
        raw_snapshots = payload.setdefault("liked_track_snapshots", {})
        if not isinstance(raw_snapshots, dict):
            raise StorageError("Library cache liked track snapshots are invalid")
        raw_snapshots[snapshot.user_id] = {
            "revision": snapshot.revision,
            "tracks": [self._serialize_track(track) for track in snapshot.tracks],
            "synced_at": self._now_iso(),
        }
        self._save_payload(payload)

    def load_liked_album_snapshot(self, user_id: str) -> tuple[Album, ...] | None:
        return self._load_entity_snapshot(
            user_id,
            snapshot_key="liked_album_snapshots",
            mapper=self._deserialize_album,
        )

    def save_liked_album_snapshot(
        self,
        user_id: str,
        albums: tuple[Album, ...] | list[Album],
    ) -> None:
        self._save_entity_snapshot(
            user_id,
            snapshot_key="liked_album_snapshots",
            items=albums,
            serializer=self._serialize_album,
        )

    def load_liked_artist_snapshot(self, user_id: str) -> tuple[Artist, ...] | None:
        return self._load_entity_snapshot(
            user_id,
            snapshot_key="liked_artist_snapshots",
            mapper=self._deserialize_artist,
        )

    def save_liked_artist_snapshot(
        self,
        user_id: str,
        artists: tuple[Artist, ...] | list[Artist],
    ) -> None:
        self._save_entity_snapshot(
            user_id,
            snapshot_key="liked_artist_snapshots",
            items=artists,
            serializer=self._serialize_artist,
        )

    def load_liked_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            user_id,
            snapshot_key="liked_playlist_snapshots",
            mapper=self._deserialize_playlist,
        )

    def save_liked_playlist_snapshot(
        self,
        user_id: str,
        playlists: tuple[Playlist, ...] | list[Playlist],
    ) -> None:
        self._save_entity_snapshot(
            user_id,
            snapshot_key="liked_playlist_snapshots",
            items=playlists,
            serializer=self._serialize_playlist,
        )

    def load_user_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            user_id,
            snapshot_key="user_playlist_snapshots",
            mapper=self._deserialize_playlist,
        )

    def save_user_playlist_snapshot(
        self,
        user_id: str,
        playlists: tuple[Playlist, ...] | list[Playlist],
    ) -> None:
        self._save_entity_snapshot(
            user_id,
            snapshot_key="user_playlist_snapshots",
            items=playlists,
            serializer=self._serialize_playlist,
        )

    def load_generated_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            user_id,
            snapshot_key="generated_playlist_snapshots",
            mapper=self._deserialize_playlist,
        )

    def save_generated_playlist_snapshot(
        self,
        user_id: str,
        playlists: tuple[Playlist, ...] | list[Playlist],
    ) -> None:
        self._save_entity_snapshot(
            user_id,
            snapshot_key="generated_playlist_snapshots",
            items=playlists,
            serializer=self._serialize_playlist,
        )

    def mark_track_liked(self, user_id: str, track_id: str) -> None:
        state = self.load_liked_track_ids(user_id)
        track_ids = set(state.track_ids if state is not None else ())
        track_ids.add(self._normalize_track_id(track_id))
        self.save_liked_track_ids(
            LikedTrackIds(
                user_id=user_id,
                revision=state.revision if state is not None else 0,
                track_ids=frozenset(track_ids),
            )
        )

    def mark_track_unliked(self, user_id: str, track_id: str) -> None:
        state = self.load_liked_track_ids(user_id)
        if state is None:
            return
        track_ids = set(state.track_ids)
        track_ids.discard(self._normalize_track_id(track_id))
        self.save_liked_track_ids(
            LikedTrackIds(
                user_id=user_id,
                revision=state.revision,
                track_ids=frozenset(track_ids),
            )
        )

    def load_artwork_ref(self, item_id: str) -> str | None:
        payload = self._load_payload()
        artwork = payload.get("artwork", {})
        if not isinstance(artwork, dict):
            raise StorageError("Library cache artwork map is invalid")
        value = artwork.get(item_id)
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return None
        if self._is_expired(value.get("cached_at"), ttl=self._ARTWORK_TTL):
            return None
        artwork_ref = value.get("ref")
        return artwork_ref if isinstance(artwork_ref, str) else None

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        payload = self._load_payload()
        artwork = payload.setdefault("artwork", {})
        if not isinstance(artwork, dict):
            raise StorageError("Library cache artwork map is invalid")
        artwork[item_id] = {"ref": artwork_ref, "cached_at": self._now_iso()}
        self._save_payload(payload)

    def _load_payload(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {
                "recent_searches": [],
                "tracks": {},
                "artwork": {},
                "liked_tracks": {},
                "liked_track_snapshots": {},
                "liked_album_snapshots": {},
                "liked_artist_snapshots": {},
                "liked_playlist_snapshots": {},
                "user_playlist_snapshots": {},
                "generated_playlist_snapshots": {},
                "catalog_search": {},
            }
        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("Failed to load library cache") from exc

        if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
            return {
                "recent_searches": payload,
                "tracks": {},
                "artwork": {},
                "catalog_search": {},
            }
        if not isinstance(payload, dict):
            raise StorageError("Library cache file is invalid")
        known_keys = {
            "recent_searches",
            "tracks",
            "artwork",
            "liked_tracks",
            "liked_track_snapshots",
            "liked_album_snapshots",
            "liked_artist_snapshots",
            "liked_playlist_snapshots",
            "user_playlist_snapshots",
            "generated_playlist_snapshots",
            "catalog_search",
        }
        if not any(key in payload for key in known_keys):
            raise StorageError("Library cache file is invalid")
        payload.setdefault("recent_searches", [])
        payload.setdefault("tracks", {})
        payload.setdefault("artwork", {})
        payload.setdefault("liked_tracks", {})
        payload.setdefault("liked_track_snapshots", {})
        payload.setdefault("liked_album_snapshots", {})
        payload.setdefault("liked_artist_snapshots", {})
        payload.setdefault("liked_playlist_snapshots", {})
        payload.setdefault("user_playlist_snapshots", {})
        payload.setdefault("generated_playlist_snapshots", {})
        payload.setdefault("catalog_search", {})
        return payload

    def _save_payload(self, payload: dict[str, Any]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError("Failed to save library cache") from exc

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def _optional_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("datetime value must be a string")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed

    def _serialize_track(self, track: Track) -> dict[str, object]:
        return {
            "id": track.id,
            "title": track.title,
            "artists": list(track.artists),
            "version": track.version,
            "artist_ids": list(track.artist_ids),
            "album_id": track.album_id,
            "album_title": track.album_title,
            "album_year": track.album_year,
            "duration_ms": track.duration_ms,
            "stream_ref": track.stream_ref,
            "stream_ref_cached_at": (
                track.stream_ref_cached_at.isoformat()
                if track.stream_ref_cached_at is not None
                else None
            ),
            "artwork_ref": track.artwork_ref,
            "accent_color": track.accent_color,
            "waveform_bins": [float(value) for value in track.waveform_bins],
            "available": track.available,
            "is_liked": track.is_liked,
        }

    def _deserialize_track(self, raw_track: object) -> Track:
        if not isinstance(raw_track, dict):
            raise StorageError("Library cache track entry is invalid")
        try:
            return Track(
                id=str(raw_track["id"]),
                title=str(raw_track["title"]),
                artists=tuple(str(artist) for artist in raw_track.get("artists", ())),
                version=self._optional_str(raw_track.get("version")),
                artist_ids=tuple(
                    str(artist_id) for artist_id in raw_track.get("artist_ids", ())
                ),
                album_id=self._optional_str(raw_track.get("album_id")),
                album_title=self._optional_str(raw_track.get("album_title")),
                album_year=self._optional_int(raw_track.get("album_year")),
                duration_ms=self._optional_int(raw_track.get("duration_ms")),
                stream_ref=self._optional_str(raw_track.get("stream_ref")),
                stream_ref_cached_at=self._optional_datetime(
                    raw_track.get("stream_ref_cached_at")
                ),
                artwork_ref=self._optional_str(raw_track.get("artwork_ref")),
                accent_color=self._optional_str(raw_track.get("accent_color")),
                waveform_bins=tuple(
                    float(value)
                    for value in raw_track.get("waveform_bins", ())
                    if isinstance(value, (int, float))
                ),
                available=bool(raw_track.get("available", True)),
                is_liked=bool(raw_track.get("is_liked", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError("Library cache track entry is invalid") from exc

    def _serialize_album(self, album: Album) -> dict[str, object]:
        return {
            "id": album.id,
            "title": album.title,
            "artists": list(album.artists),
            "artist_ids": list(album.artist_ids),
            "is_liked": album.is_liked,
            "release_type": album.release_type,
            "year": album.year,
            "track_count": album.track_count,
            "artwork_ref": album.artwork_ref,
        }

    def _deserialize_album(self, raw_album: object) -> Album:
        if not isinstance(raw_album, dict):
            raise StorageError("Library cache album entry is invalid")
        return Album(
            id=str(raw_album["id"]),
            title=str(raw_album["title"]),
            artists=tuple(str(artist) for artist in raw_album.get("artists", ())),
            artist_ids=tuple(str(artist_id) for artist_id in raw_album.get("artist_ids", ())),
            is_liked=bool(raw_album.get("is_liked", False)),
            release_type=self._optional_str(raw_album.get("release_type")),
            year=self._optional_int(raw_album.get("year")),
            track_count=self._optional_int(raw_album.get("track_count")),
            artwork_ref=self._optional_str(raw_album.get("artwork_ref")),
        )

    def _serialize_artist(self, artist: Artist) -> dict[str, object]:
        return {
            "id": artist.id,
            "name": artist.name,
            "artwork_ref": artist.artwork_ref,
            "is_liked": artist.is_liked,
        }

    def _deserialize_artist(self, raw_artist: object) -> Artist:
        if not isinstance(raw_artist, dict):
            raise StorageError("Library cache artist entry is invalid")
        return Artist(
            id=str(raw_artist["id"]),
            name=str(raw_artist["name"]),
            artwork_ref=self._optional_str(raw_artist.get("artwork_ref")),
            is_liked=bool(raw_artist.get("is_liked", False)),
        )

    def _serialize_playlist(self, playlist: Playlist) -> dict[str, object]:
        return {
            "id": playlist.id,
            "title": playlist.title,
            "owner_id": playlist.owner_id,
            "owner_name": playlist.owner_name,
            "description": playlist.description,
            "track_count": playlist.track_count,
            "artwork_ref": playlist.artwork_ref,
            "is_generated": playlist.is_generated,
            "is_liked": playlist.is_liked,
        }

    def _deserialize_playlist(self, raw_playlist: object) -> Playlist:
        if not isinstance(raw_playlist, dict):
            raise StorageError("Library cache playlist entry is invalid")
        return Playlist(
            id=str(raw_playlist["id"]),
            title=str(raw_playlist["title"]),
            owner_id=self._optional_str(raw_playlist.get("owner_id")),
            owner_name=self._optional_str(raw_playlist.get("owner_name")),
            description=self._optional_str(raw_playlist.get("description")),
            track_count=self._optional_int(raw_playlist.get("track_count")),
            artwork_ref=self._optional_str(raw_playlist.get("artwork_ref")),
            is_generated=bool(raw_playlist.get("is_generated", False)),
            is_liked=bool(raw_playlist.get("is_liked", False)),
        )

    def _serialize_catalog_search(self, results: CatalogSearchResults) -> dict[str, object]:
        return {
            "tracks": [self._serialize_track(track) for track in results.tracks],
            "albums": [self._serialize_album(album) for album in results.albums],
            "singles": [self._serialize_album(album) for album in results.singles],
            "compilations": [self._serialize_album(album) for album in results.compilations],
            "artists": [self._serialize_artist(artist) for artist in results.artists],
            "playlists": [self._serialize_playlist(playlist) for playlist in results.playlists],
        }

    def _deserialize_catalog_search(self, raw_results: object) -> CatalogSearchResults:
        if not isinstance(raw_results, dict):
            raise StorageError("Library cache catalog search entry is invalid")
        return CatalogSearchResults(
            tracks=tuple(
                self._deserialize_track(raw_track)
                for raw_track in self._require_list(raw_results.get("tracks"))
            ),
            albums=tuple(
                self._deserialize_album(raw_album)
                for raw_album in self._require_list(raw_results.get("albums"))
            ),
            singles=tuple(
                self._deserialize_album(raw_album)
                for raw_album in self._require_list(raw_results.get("singles"))
            ),
            compilations=tuple(
                self._deserialize_album(raw_album)
                for raw_album in self._require_list(raw_results.get("compilations"))
            ),
            artists=tuple(
                self._deserialize_artist(raw_artist)
                for raw_artist in self._require_list(raw_results.get("artists"))
            ),
            playlists=tuple(
                self._deserialize_playlist(raw_playlist)
                for raw_playlist in self._require_list(raw_results.get("playlists"))
            ),
        )

    def _load_entity_snapshot(self, user_id: str, *, snapshot_key: str, mapper):
        payload = self._load_payload()
        raw_snapshots = payload.get(snapshot_key, {})
        if not isinstance(raw_snapshots, dict):
            raise StorageError("Library cache snapshot map is invalid")
        raw_snapshot = raw_snapshots.get(user_id)
        if raw_snapshot is None:
            return None
        if not isinstance(raw_snapshot, dict):
            raise StorageError("Library cache snapshot entry is invalid")
        if self._is_list_snapshot_expired(raw_snapshot.get("synced_at")):
            return None
        raw_items = raw_snapshot.get("items", ())
        if not isinstance(raw_items, list):
            raise StorageError("Library cache snapshot items are invalid")
        return tuple(mapper(raw_item) for raw_item in raw_items)

    def _save_entity_snapshot(
        self,
        user_id: str,
        *,
        snapshot_key: str,
        items,
        serializer,
    ) -> None:
        payload = self._load_payload()
        raw_snapshots = payload.setdefault(snapshot_key, {})
        if not isinstance(raw_snapshots, dict):
            raise StorageError("Library cache snapshot map is invalid")
        raw_snapshots[user_id] = {
            "items": [serializer(item) for item in items],
            "synced_at": self._now_iso(),
        }
        self._save_payload(payload)

    def _is_list_snapshot_expired(self, raw_value: object) -> bool:
        if not isinstance(raw_value, str):
            return True
        try:
            cached_at = datetime.fromisoformat(raw_value)
        except ValueError:
            return True
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - cached_at > self._LIST_CACHE_TTL

    def _normalize_search_query(self, query: str) -> str:
        return query.strip().casefold()

    def _require_list(self, value: object) -> list[object]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise StorageError("Library cache catalog search entry is invalid")
        return value

    def _now_iso(self) -> str:
        return datetime.now(tz=UTC).isoformat()

    def _is_expired(self, raw_value: object, *, ttl: timedelta | None = None) -> bool:
        if not isinstance(raw_value, str):
            return False
        try:
            cached_at = datetime.fromisoformat(raw_value)
        except ValueError:
            return True
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - cached_at > (ttl or self._CACHE_TTL)

    def _normalize_track_id(self, track_id: str) -> str:
        raw_track_id = str(track_id)
        base_id, separator, album_id = raw_track_id.partition(":")
        if separator and base_id.isdigit() and album_id.isdigit():
            return base_id
        return raw_track_id

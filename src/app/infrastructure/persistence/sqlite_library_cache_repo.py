from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

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


class SQLiteLibraryCacheRepo(LibraryCacheRepo):
    _CACHE_TTL = timedelta(days=7)
    _ARTWORK_TTL = timedelta(days=30)
    _LIST_CACHE_TTL = timedelta(days=1)
    _SEARCH_CACHE_TTL = timedelta(hours=1)

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._initialize()

    def load_recent_searches(self) -> tuple[str, ...]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "select query from recent_searches order by position asc"
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load recent searches") from exc
        return tuple(str(row["query"]) for row in rows)

    def save_recent_searches(self, searches: Sequence[str]) -> None:
        try:
            with self._connect() as connection:
                connection.execute("delete from recent_searches")
                connection.executemany(
                    (
                        "insert into recent_searches(query, position, updated_at) "
                        "values (?, ?, ?)"
                    ),
                    [
                        (query, position, self._now_iso())
                        for position, query in enumerate(searches)
                    ],
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save recent searches") from exc

    def load_catalog_search(self, query: str) -> CatalogSearchResults | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    (
                        "select data_json, cached_at from catalog_search_cache "
                        "where query = ?"
                    ),
                    (self._normalize_search_query(query),),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached catalog search") from exc
        if row is None or self._is_expired(row["cached_at"], ttl=self._SEARCH_CACHE_TTL):
            return None
        try:
            payload = json.loads(row["data_json"])
        except json.JSONDecodeError as exc:
            raise StorageError("Cached catalog search is invalid") from exc
        return self._decode_catalog_search(payload)

    def save_catalog_search(self, query: str, results: CatalogSearchResults) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into catalog_search_cache(query, data_json, cached_at) "
                        "values (?, ?, ?) "
                        "on conflict(query) do update set "
                        "data_json = excluded.data_json, "
                        "cached_at = excluded.cached_at"
                    ),
                    (
                        self._normalize_search_query(query),
                        json.dumps(
                            self._encode_catalog_search(results),
                            ensure_ascii=True,
                        ),
                        self._now_iso(),
                    ),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached catalog search") from exc

    def load_track_metadata(self, track_id: str) -> Track | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select * from tracks where id = ?",
                    (track_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached track metadata") from exc

        if row is None:
            return None
        if self._is_expired(row["cached_at"]):
            return None
        try:
            artists = json.loads(row["artists_json"])
            if not isinstance(artists, list):
                raise TypeError("artists_json must be a list")
            artist_ids = json.loads(row["artist_ids_json"] or "[]")
            if not isinstance(artist_ids, list):
                raise TypeError("artist_ids_json must be a list")
            waveform_bins = json.loads(row["waveform_bins_json"] or "[]")
            if not isinstance(waveform_bins, list):
                raise TypeError("waveform_bins_json must be a list")
            return Track(
                id=str(row["id"]),
                title=str(row["title"]),
                artists=tuple(str(artist) for artist in artists),
                version=row["version"],
                artist_ids=tuple(str(artist_id) for artist_id in artist_ids),
                album_id=row["album_id"],
                album_title=row["album_title"],
                album_year=row["album_year"],
                duration_ms=row["duration_ms"],
                stream_ref=row["stream_ref"],
                stream_ref_cached_at=self._optional_datetime(row["stream_ref_cached_at"]),
                artwork_ref=row["artwork_ref"],
                accent_color=row["accent_color"],
                waveform_bins=tuple(
                    float(value) for value in waveform_bins if isinstance(value, (int, float))
                ),
                available=bool(row["available"]),
                is_liked=bool(row["is_liked"]),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StorageError("Cached track metadata is invalid") from exc

    def save_track_metadata(self, track: Track) -> None:
        try:
            with self._connect() as connection:
                self._save_track_metadata_with_connection(connection, track)
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached track metadata") from exc

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select revision from liked_track_sync where user_id = ?",
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None
                rows = connection.execute(
                    "select track_id from liked_tracks where user_id = ?",
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load liked track ids") from exc
        return LikedTrackIds(
            user_id=user_id,
            revision=int(row["revision"]),
            track_ids=frozenset(str(item["track_id"]) for item in rows),
        )

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None:
        try:
            with self._connect() as connection:
                now = self._now_iso()
                connection.execute("begin")
                connection.execute(
                    "delete from liked_tracks where user_id = ?",
                    (liked_tracks.user_id,),
                )
                connection.executemany(
                    (
                        "insert into liked_tracks(user_id, track_id, updated_at) "
                        "values (?, ?, ?)"
                    ),
                    [
                        (liked_tracks.user_id, track_id, now)
                        for track_id in sorted(liked_tracks.track_ids)
                    ],
                )
                connection.execute(
                    (
                        "insert into liked_track_sync(user_id, revision, synced_at) "
                        "values (?, ?, ?) "
                        "on conflict(user_id) do update set "
                        "revision = excluded.revision, "
                        "synced_at = excluded.synced_at"
                    ),
                    (liked_tracks.user_id, liked_tracks.revision, now),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save liked track ids") from exc

    def load_liked_track_snapshot(self, user_id: str) -> LikedTrackSnapshot | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select revision from liked_track_snapshot_sync where user_id = ?",
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None
                rows = connection.execute(
                    (
                        "select s.track_id from liked_track_snapshot_items s "
                        "where s.user_id = ? "
                        "order by s.position asc"
                    ),
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load liked track snapshot") from exc

        tracks = tuple(
            track
            for track_id in (str(snapshot_row["track_id"]) for snapshot_row in rows)
            for track in (self.load_track_metadata(track_id),)
            if track is not None
        )
        return LikedTrackSnapshot(
            user_id=user_id,
            revision=int(row["revision"]),
            tracks=tracks,
        )

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot) -> None:
        try:
            with self._connect() as connection:
                now = self._now_iso()
                connection.execute("begin")
                for track in snapshot.tracks:
                    self._save_track_metadata_with_connection(connection, track)
                connection.execute(
                    "delete from liked_track_snapshot_items where user_id = ?",
                    (snapshot.user_id,),
                )
                connection.executemany(
                    (
                        "insert into liked_track_snapshot_items("
                        "user_id, position, track_id, updated_at"
                        ") "
                        "values (?, ?, ?, ?)"
                    ),
                    [
                        (snapshot.user_id, position, track.id, now)
                        for position, track in enumerate(snapshot.tracks)
                    ],
                )
                connection.execute(
                    (
                        "insert into liked_track_snapshot_sync(user_id, revision, synced_at) "
                        "values (?, ?, ?) "
                        "on conflict(user_id) do update set "
                        "revision = excluded.revision, "
                        "synced_at = excluded.synced_at"
                    ),
                    (snapshot.user_id, snapshot.revision, now),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save liked track snapshot") from exc

    def load_liked_album_snapshot(self, user_id: str) -> tuple[Album, ...] | None:
        return self._load_entity_snapshot(
            cache_key="liked_albums",
            user_id=user_id,
            mapper=self._decode_album,
        )

    def save_liked_album_snapshot(self, user_id: str, albums: Sequence[Album]) -> None:
        self._save_entity_snapshot(
            cache_key="liked_albums",
            user_id=user_id,
            items=albums,
            encoder=self._encode_album,
        )

    def load_liked_artist_snapshot(self, user_id: str) -> tuple[Artist, ...] | None:
        return self._load_entity_snapshot(
            cache_key="liked_artists",
            user_id=user_id,
            mapper=self._decode_artist,
        )

    def save_liked_artist_snapshot(self, user_id: str, artists: Sequence[Artist]) -> None:
        self._save_entity_snapshot(
            cache_key="liked_artists",
            user_id=user_id,
            items=artists,
            encoder=self._encode_artist,
        )

    def load_liked_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            cache_key="liked_playlists",
            user_id=user_id,
            mapper=self._decode_playlist,
        )

    def save_liked_playlist_snapshot(self, user_id: str, playlists: Sequence[Playlist]) -> None:
        self._save_entity_snapshot(
            cache_key="liked_playlists",
            user_id=user_id,
            items=playlists,
            encoder=self._encode_playlist,
        )

    def load_user_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            cache_key="user_playlists",
            user_id=user_id,
            mapper=self._decode_playlist,
        )

    def save_user_playlist_snapshot(self, user_id: str, playlists: Sequence[Playlist]) -> None:
        self._save_entity_snapshot(
            cache_key="user_playlists",
            user_id=user_id,
            items=playlists,
            encoder=self._encode_playlist,
        )

    def load_generated_playlist_snapshot(self, user_id: str) -> tuple[Playlist, ...] | None:
        return self._load_entity_snapshot(
            cache_key="generated_playlists",
            user_id=user_id,
            mapper=self._decode_playlist,
        )

    def save_generated_playlist_snapshot(
        self,
        user_id: str,
        playlists: Sequence[Playlist],
    ) -> None:
        self._save_entity_snapshot(
            cache_key="generated_playlists",
            user_id=user_id,
            items=playlists,
            encoder=self._encode_playlist,
        )

    def mark_track_liked(self, user_id: str, track_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into liked_tracks(user_id, track_id, updated_at) "
                        "values (?, ?, ?) "
                        "on conflict(user_id, track_id) do update set "
                        "updated_at = excluded.updated_at"
                    ),
                    (user_id, self._normalize_track_id(track_id), self._now_iso()),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to mark track liked") from exc

    def mark_track_unliked(self, user_id: str, track_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "delete from liked_tracks where user_id = ? and track_id = ?",
                    (user_id, self._normalize_track_id(track_id)),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to mark track unliked") from exc

    def load_artwork_ref(self, item_id: str) -> str | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select artwork_ref, cached_at from artwork where item_id = ?",
                    (item_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached artwork reference") from exc

        if row is None or self._is_expired(row["cached_at"], ttl=self._ARTWORK_TTL):
            return None
        return str(row["artwork_ref"])

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into artwork(item_id, artwork_ref, cached_at) "
                        "values (?, ?, ?) "
                        "on conflict(item_id) do update set "
                        "artwork_ref = excluded.artwork_ref, "
                        "cached_at = excluded.cached_at"
                    ),
                    (item_id, artwork_ref, self._now_iso()),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached artwork reference") from exc

    def _initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    create table if not exists recent_searches (
                        query text primary key,
                        position integer not null,
                        updated_at text not null
                    );

                    create table if not exists tracks (
                        id text primary key,
                        title text not null,
                        version text,
                        artists_json text not null,
                        artist_ids_json text not null default '[]',
                        album_id text,
                        album_title text,
                        album_year integer,
                        duration_ms integer,
                        stream_ref text,
                        stream_ref_cached_at text,
                        artwork_ref text,
                        accent_color text,
                        waveform_bins_json text not null default '[]',
                        available integer not null,
                        is_liked integer not null,
                        cached_at text not null
                    );

                    create table if not exists artwork (
                        item_id text primary key,
                        artwork_ref text not null,
                        cached_at text not null
                    );

                    create table if not exists catalog_search_cache (
                        query text primary key,
                        data_json text not null,
                        cached_at text not null
                    );

                    create table if not exists liked_track_sync (
                        user_id text primary key,
                        revision integer not null,
                        synced_at text not null
                    );

                    create table if not exists liked_tracks (
                        user_id text not null,
                        track_id text not null,
                        updated_at text not null,
                        primary key (user_id, track_id)
                    );

                    create table if not exists liked_track_snapshot_sync (
                        user_id text primary key,
                        revision integer not null,
                        synced_at text not null
                    );

                    create table if not exists liked_track_snapshot_items (
                        user_id text not null,
                        position integer not null,
                        track_id text not null,
                        updated_at text not null,
                        primary key (user_id, position)
                    );

                    create table if not exists entity_list_cache (
                        cache_key text not null,
                        user_id text not null,
                        data_json text not null,
                        synced_at text not null,
                        primary key (cache_key, user_id)
                    );
                    """
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="version",
                    definition="text",
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="artist_ids_json",
                    definition="text not null default '[]'",
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="album_id",
                    definition="text",
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="stream_ref_cached_at",
                    definition="text",
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="accent_color",
                    definition="text",
                )
                self._ensure_column(
                    connection,
                    table="tracks",
                    column="waveform_bins_json",
                    definition="text not null default '[]'",
                )
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("Failed to initialize library cache database") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _now_iso(self) -> str:
        return datetime.now(tz=UTC).isoformat()

    def _is_expired(self, raw_value: Any, *, ttl: timedelta | None = None) -> bool:
        if not isinstance(raw_value, str):
            return True
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

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"pragma table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"alter table {table} add column {column} {definition}")

    def _save_track_metadata_with_connection(
        self,
        connection: sqlite3.Connection,
        track: Track,
    ) -> None:
        connection.execute(
            (
                "insert into tracks("
                "id, title, version, artists_json, artist_ids_json, album_id, album_title, "
                "album_year, duration_ms, "
                "stream_ref, stream_ref_cached_at, artwork_ref, accent_color, waveform_bins_json, "
                "available, is_liked, cached_at"
                ") values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "on conflict(id) do update set "
                "title = excluded.title, "
                "version = excluded.version, "
                "artists_json = excluded.artists_json, "
                "artist_ids_json = excluded.artist_ids_json, "
                "album_id = excluded.album_id, "
                "album_title = excluded.album_title, "
                "album_year = excluded.album_year, "
                "duration_ms = excluded.duration_ms, "
                "stream_ref = excluded.stream_ref, "
                "stream_ref_cached_at = excluded.stream_ref_cached_at, "
                "artwork_ref = excluded.artwork_ref, "
                "accent_color = excluded.accent_color, "
                "waveform_bins_json = excluded.waveform_bins_json, "
                "available = excluded.available, "
                "is_liked = excluded.is_liked, "
                "cached_at = excluded.cached_at"
            ),
            (
                track.id,
                track.title,
                track.version,
                json.dumps(list(track.artists), ensure_ascii=True),
                json.dumps(list(track.artist_ids), ensure_ascii=True),
                track.album_id,
                track.album_title,
                track.album_year,
                track.duration_ms,
                track.stream_ref,
                (
                    track.stream_ref_cached_at.isoformat()
                    if track.stream_ref_cached_at is not None
                    else None
                ),
                track.artwork_ref,
                track.accent_color,
                json.dumps([float(value) for value in track.waveform_bins], ensure_ascii=True),
                int(track.available),
                int(track.is_liked),
                self._now_iso(),
            ),
        )

    def _load_entity_snapshot(self, *, cache_key: str, user_id: str, mapper):
        try:
            with self._connect() as connection:
                row = connection.execute(
                    (
                        "select data_json, synced_at from entity_list_cache "
                        "where cache_key = ? and user_id = ?"
                    ),
                    (cache_key, user_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached entity snapshot") from exc
        if row is None or self._is_list_snapshot_expired(row["synced_at"]):
            return None
        try:
            payload = json.loads(row["data_json"])
        except json.JSONDecodeError as exc:
            raise StorageError("Cached entity snapshot is invalid") from exc
        if not isinstance(payload, list):
            raise StorageError("Cached entity snapshot is invalid")
        return tuple(mapper(item) for item in payload)

    def _save_entity_snapshot(self, *, cache_key: str, user_id: str, items, encoder) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into entity_list_cache(cache_key, user_id, data_json, synced_at) "
                        "values (?, ?, ?, ?) "
                        "on conflict(cache_key, user_id) do update set "
                        "data_json = excluded.data_json, "
                        "synced_at = excluded.synced_at"
                    ),
                    (
                        cache_key,
                        user_id,
                        json.dumps([encoder(item) for item in items], ensure_ascii=True),
                        self._now_iso(),
                    ),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached entity snapshot") from exc

    def _encode_album(self, album: Album) -> dict[str, object]:
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

    def _decode_album(self, raw_album: object) -> Album:
        if not isinstance(raw_album, dict):
            raise StorageError("Cached album snapshot is invalid")
        return Album(
            id=str(raw_album["id"]),
            title=str(raw_album["title"]),
            artists=tuple(str(artist) for artist in raw_album.get("artists", ())),
            artist_ids=tuple(str(artist_id) for artist_id in raw_album.get("artist_ids", ())),
            is_liked=bool(raw_album.get("is_liked", False)),
            release_type=(
                str(raw_album["release_type"])
                if raw_album.get("release_type") is not None
                else None
            ),
            year=int(raw_album["year"]) if raw_album.get("year") is not None else None,
            track_count=(
                int(raw_album["track_count"]) if raw_album.get("track_count") is not None else None
            ),
            artwork_ref=(
                str(raw_album["artwork_ref"])
                if raw_album.get("artwork_ref") is not None
                else None
            ),
        )

    def _encode_artist(self, artist: Artist) -> dict[str, object]:
        return {
            "id": artist.id,
            "name": artist.name,
            "artwork_ref": artist.artwork_ref,
            "is_liked": artist.is_liked,
        }

    def _decode_artist(self, raw_artist: object) -> Artist:
        if not isinstance(raw_artist, dict):
            raise StorageError("Cached artist snapshot is invalid")
        return Artist(
            id=str(raw_artist["id"]),
            name=str(raw_artist["name"]),
            artwork_ref=(
                str(raw_artist["artwork_ref"])
                if raw_artist.get("artwork_ref") is not None
                else None
            ),
            is_liked=bool(raw_artist.get("is_liked", False)),
        )

    def _encode_playlist(self, playlist: Playlist) -> dict[str, object]:
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

    def _decode_playlist(self, raw_playlist: object) -> Playlist:
        if not isinstance(raw_playlist, dict):
            raise StorageError("Cached playlist snapshot is invalid")
        return Playlist(
            id=str(raw_playlist["id"]),
            title=str(raw_playlist["title"]),
            owner_id=(
                str(raw_playlist["owner_id"])
                if raw_playlist.get("owner_id") is not None
                else None
            ),
            owner_name=(
                str(raw_playlist["owner_name"])
                if raw_playlist.get("owner_name") is not None
                else None
            ),
            description=(
                str(raw_playlist["description"])
                if raw_playlist.get("description") is not None
                else None
            ),
            track_count=(
                int(raw_playlist["track_count"])
                if raw_playlist.get("track_count") is not None
                else None
            ),
            artwork_ref=(
                str(raw_playlist["artwork_ref"])
                if raw_playlist.get("artwork_ref") is not None
                else None
            ),
            is_generated=bool(raw_playlist.get("is_generated", False)),
            is_liked=bool(raw_playlist.get("is_liked", False)),
        )

    def _encode_catalog_search(self, results: CatalogSearchResults) -> dict[str, object]:
        return {
            "tracks": [self._encode_track(track) for track in results.tracks],
            "albums": [self._encode_album(album) for album in results.albums],
            "singles": [self._encode_album(album) for album in results.singles],
            "compilations": [self._encode_album(album) for album in results.compilations],
            "artists": [self._encode_artist(artist) for artist in results.artists],
            "playlists": [self._encode_playlist(playlist) for playlist in results.playlists],
        }

    def _decode_catalog_search(self, raw_results: object) -> CatalogSearchResults:
        if not isinstance(raw_results, dict):
            raise StorageError("Cached catalog search is invalid")
        return CatalogSearchResults(
            tracks=tuple(
                self._decode_track(raw_track)
                for raw_track in self._require_list(raw_results.get("tracks"))
            ),
            albums=tuple(
                self._decode_album(raw_album)
                for raw_album in self._require_list(raw_results.get("albums"))
            ),
            singles=tuple(
                self._decode_album(raw_album)
                for raw_album in self._require_list(raw_results.get("singles"))
            ),
            compilations=tuple(
                self._decode_album(raw_album)
                for raw_album in self._require_list(raw_results.get("compilations"))
            ),
            artists=tuple(
                self._decode_artist(raw_artist)
                for raw_artist in self._require_list(raw_results.get("artists"))
            ),
            playlists=tuple(
                self._decode_playlist(raw_playlist)
                for raw_playlist in self._require_list(raw_results.get("playlists"))
            ),
        )

    def _is_list_snapshot_expired(self, raw_value: Any) -> bool:
        if not isinstance(raw_value, str):
            return True
        try:
            cached_at = datetime.fromisoformat(raw_value)
        except ValueError:
            return True
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - cached_at > self._LIST_CACHE_TTL

    def _encode_track(self, track: Track) -> dict[str, object]:
        return {
            "id": track.id,
            "title": track.title,
            "version": track.version,
            "artists": list(track.artists),
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

    def _decode_track(self, raw_track: object) -> Track:
        if not isinstance(raw_track, dict):
            raise StorageError("Cached track metadata is invalid")
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
            raise StorageError("Cached track metadata is invalid") from exc

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

    def _normalize_search_query(self, query: str) -> str:
        return query.strip().casefold()

    def _require_list(self, value: object) -> list[object]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise StorageError("Cached catalog search is invalid")
        return value

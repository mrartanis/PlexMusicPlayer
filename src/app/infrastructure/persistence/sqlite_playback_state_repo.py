from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from app.domain import PlaybackStateRepo, QueueItem, SavedPlaybackQueue, Track
from app.domain.errors import StorageError


class SQLitePlaybackStateRepo(PlaybackStateRepo):
    _QUEUE_ID = 1

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._initialize()

    def load_playback_queue(self) -> SavedPlaybackQueue | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    (
                        "select queue_json, active_index, position_ms "
                        "from playback_queue where id = ?"
                    ),
                    (self._QUEUE_ID,),
                ).fetchone()
                if row is None:
                    return None
                item_rows = connection.execute(
                    (
                        "select * from playback_queue_items "
                        "where queue_id = ? order by position asc"
                    ),
                    (self._QUEUE_ID,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load playback queue") from exc

        active_index = row["active_index"]
        if active_index is not None:
            active_index = int(active_index)
        position_ms = max(0, int(row["position_ms"] or 0))
        try:
            if item_rows:
                queue = tuple(self._decode_queue_item_row(item_row) for item_row in item_rows)
            else:
                queue = self._decode_legacy_queue_json(row["queue_json"])
        except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
            raise StorageError("Saved playback queue is invalid") from exc
        return SavedPlaybackQueue(
            queue=queue,
            active_index=active_index,
            position_ms=position_ms,
        )

    def save_playback_queue(
        self,
        queue: Sequence[QueueItem],
        *,
        active_index: int | None,
        position_ms: int = 0,
    ) -> None:
        try:
            with self._connect() as connection:
                now = datetime.now(tz=UTC).isoformat()
                connection.execute("begin")
                connection.execute(
                    (
                        "insert into playback_queue("
                        "id, queue_json, active_index, position_ms, updated_at"
                        ") "
                        "values (?, ?, ?, ?, ?) "
                        "on conflict(id) do update set "
                        "queue_json = excluded.queue_json, "
                        "active_index = excluded.active_index, "
                        "position_ms = excluded.position_ms, "
                        "updated_at = excluded.updated_at"
                    ),
                    (
                        self._QUEUE_ID,
                        "[]",
                        active_index,
                        max(0, position_ms),
                        now,
                    ),
                )
                connection.execute(
                    "delete from playback_queue_items where queue_id = ?",
                    (self._QUEUE_ID,),
                )
                connection.executemany(
                    (
                        "insert into playback_queue_items("
                        "queue_id, position, track_id, title, artists_json, version, "
                        "artist_ids_json, album_id, album_title, album_year, duration_ms, "
                        "artwork_ref, accent_color, available, is_liked, source_type, "
                        "source_id, source_index, station_batch_id, radio_session_id, "
                        "radio_origin, radio_queue_anchor_track_id"
                        ") values ("
                        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
                        ")"
                    ),
                    [
                        self._encode_queue_item_row(
                            position=position,
                            item=item,
                        )
                        for position, item in enumerate(queue)
                    ],
                )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise StorageError("Failed to save playback queue") from exc

    def clear_playback_queue(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("begin")
                connection.execute(
                    "delete from playback_queue_items where queue_id = ?",
                    (self._QUEUE_ID,),
                )
                connection.execute(
                    "delete from playback_queue where id = ?",
                    (self._QUEUE_ID,),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to clear playback queue") from exc

    def _initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute("pragma foreign_keys = on")
                connection.executescript(
                    """
                    create table if not exists playback_queue (
                        id integer primary key check (id = 1),
                        queue_json text not null default '[]',
                        active_index integer,
                        position_ms integer not null default 0,
                        updated_at text not null
                    );

                    create table if not exists playback_queue_items (
                        queue_id integer not null,
                        position integer not null,
                        track_id text not null,
                        title text not null,
                        artists_json text not null,
                        version text,
                        artist_ids_json text not null default '[]',
                        album_id text,
                        album_title text,
                        album_year integer,
                        duration_ms integer,
                        artwork_ref text,
                        accent_color text,
                        available integer not null default 1,
                        is_liked integer not null default 0,
                        source_type text,
                        source_id text,
                        source_index integer,
                        station_batch_id text,
                        radio_session_id text,
                        radio_origin text,
                        radio_queue_anchor_track_id text,
                        primary key (queue_id, position),
                        foreign key(queue_id) references playback_queue(id) on delete cascade
                    );
                    """
                )
                self._ensure_column(
                    connection,
                    table="playback_queue",
                    column="position_ms",
                    definition="integer not null default 0",
                )
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("Failed to initialize playback state database") from exc

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

    def _decode_legacy_queue_json(self, queue_json: object) -> tuple[QueueItem, ...]:
        if queue_json is None:
            return ()
        payload = json.loads(str(queue_json))
        if not isinstance(payload, list):
            raise TypeError("queue_json must be a list")
        return tuple(self._decode_legacy_queue_item(item) for item in payload)

    def _decode_legacy_queue_item(self, payload: object) -> QueueItem:
        if not isinstance(payload, dict):
            raise TypeError("queue item must be a dict")
        raw_track = payload["track"]
        if not isinstance(raw_track, dict):
            raise TypeError("track must be a dict")
        raw_artists = raw_track["artists"]
        if not isinstance(raw_artists, list):
            raise TypeError("artists must be a list")
        return QueueItem(
            track=Track(
                id=str(raw_track["id"]),
                title=str(raw_track["title"]),
                artists=tuple(str(artist) for artist in raw_artists),
                version=(
                    str(raw_track["version"]) if raw_track.get("version") is not None else None
                ),
                artist_ids=tuple(
                    str(artist_id) for artist_id in raw_track.get("artist_ids", ())
                ),
                album_id=(
                    str(raw_track["album_id"]) if raw_track.get("album_id") is not None else None
                ),
                album_title=raw_track.get("album_title"),
                album_year=raw_track.get("album_year"),
                duration_ms=raw_track.get("duration_ms"),
                stream_ref=None,
                artwork_ref=raw_track.get("artwork_ref"),
                accent_color=raw_track.get("accent_color"),
                available=bool(raw_track.get("available", True)),
                is_liked=bool(raw_track.get("is_liked", False)),
            ),
            source_type=payload.get("source_type"),
            source_id=payload.get("source_id"),
            source_index=payload.get("source_index"),
            station_batch_id=payload.get("station_batch_id"),
            radio_session_id=payload.get("radio_session_id"),
            radio_origin=payload.get("radio_origin"),
            radio_queue_anchor_track_id=payload.get("radio_queue_anchor_track_id"),
        )

    def _encode_queue_item_row(self, *, position: int, item: QueueItem) -> tuple[object, ...]:
        return (
            self._QUEUE_ID,
            position,
            item.track.id,
            item.track.title,
            json.dumps(list(item.track.artists), ensure_ascii=True),
            item.track.version,
            json.dumps(list(item.track.artist_ids), ensure_ascii=True),
            item.track.album_id,
            item.track.album_title,
            item.track.album_year,
            item.track.duration_ms,
            item.track.artwork_ref,
            item.track.accent_color,
            int(bool(item.track.available)),
            int(bool(item.track.is_liked)),
            item.source_type,
            item.source_id,
            item.source_index,
            item.station_batch_id,
            item.radio_session_id,
            item.radio_origin,
            item.radio_queue_anchor_track_id,
        )

    def _decode_queue_item_row(self, row: sqlite3.Row) -> QueueItem:
        artists = json.loads(row["artists_json"])
        artist_ids = json.loads(row["artist_ids_json"] or "[]")
        if not isinstance(artists, list):
            raise TypeError("artists_json must be a list")
        if not isinstance(artist_ids, list):
            raise TypeError("artist_ids_json must be a list")
        return QueueItem(
            track=Track(
                id=str(row["track_id"]),
                title=str(row["title"]),
                artists=tuple(str(artist) for artist in artists),
                version=row["version"],
                artist_ids=tuple(str(artist_id) for artist_id in artist_ids),
                album_id=row["album_id"],
                album_title=row["album_title"],
                album_year=row["album_year"],
                duration_ms=row["duration_ms"],
                stream_ref=None,
                artwork_ref=row["artwork_ref"],
                accent_color=row["accent_color"],
                available=bool(row["available"]),
                is_liked=bool(row["is_liked"]),
            ),
            source_type=row["source_type"],
            source_id=row["source_id"],
            source_index=row["source_index"],
            station_batch_id=row["station_batch_id"],
            radio_session_id=row["radio_session_id"],
            radio_origin=row["radio_origin"],
            radio_queue_anchor_track_id=row["radio_queue_anchor_track_id"],
        )

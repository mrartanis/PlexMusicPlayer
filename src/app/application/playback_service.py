from __future__ import annotations

import math
import random
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import uuid4

from app.application.track_metadata import merge_cached_liked_state, merge_cached_liked_states
from app.domain import (
    LibraryCacheRepo,
    Logger,
    PlaybackEngine,
    PlaybackState,
    PlaybackStateRepo,
    PlaybackStatus,
    QueueItem,
    RadioSession,
    RepeatMode,
    Track,
    WaveformState,
)
from app.domain.errors import PlaybackBackendError, StreamResolveError
from app.domain.protocols import MusicService
from app.infrastructure.playback.stream_proxy_service import StreamProxyService


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    queue: tuple[QueueItem, ...]
    state: PlaybackState
    current_item: QueueItem | None


@dataclass(slots=True)
class _PlaybackTelemetrySession:
    track_id: str
    play_id: str
    origin: str
    plays_start_timestamp_iso: str | None = None
    plays_add_tracks_to_player_time: str | None = None
    started: bool = False
    terminal_reported: bool = False
    accumulated_played_ms: int = 0
    last_known_position_ms: int = 0
    last_accounted_position_ms: int = 0


@dataclass(frozen=True, slots=True)
class _ScrobbleContext:
    from_: str
    context: str
    context_item: str
    album_id: str | None = None
    playlist_id: str | None = None
    radio_session_id: str | None = None
    batch_id: str | None = None


class PlaybackService:
    _STREAM_REF_TTL = timedelta(hours=1)
    _STATION_FINISHED_RATIO = 0.9
    _STATION_FINISHED_REMAINING_SECONDS = 5.0
    _PLAY_ORIGIN_DESKTOP = "desktop_win-yaymp"
    _PLAY_ORIGIN_MY_WAVE = "desktop_win-radio-user-onyourwave"
    _PLAY_ORIGIN_STATION = "desktop_win-radio-station"
    _SCROBBLE_ALBUM_FROM = "mobile-album-track-default"
    _SCROBBLE_ARTIST_FROM = "mobile-artist-artist-default"
    _SCROBBLE_PLAYLIST_FROM = "mobile-playlist-playlist-default"
    _SCROBBLE_PLAYLIST_LIKES_KIND = "3"
    _STATION_QUEUE_REFILL_THRESHOLD = 3
    _STATION_QUEUE_BATCH_SIZE = 4
    _STATION_QUEUE_REFILL_MAX_ATTEMPTS = 3
    _STREAM_PREFETCH_AHEAD = 2
    _STATION_QUEUE_RETAIN_BEFORE_ACTIVE = 10
    _STATION_QUEUE_MAX_LENGTH = 1000
    _STATION_QUEUE_PERSIST_LENGTH = 50
    _POSITION_PERSIST_INTERVAL_SECONDS = 5.0
    _WAVEFORM_SUPPORTED = sys.platform != "win32"

    def __init__(
        self,
        *,
        playback_engine: PlaybackEngine,
        logger: Logger,
        music_service: MusicService | None = None,
        library_cache_repo: LibraryCacheRepo | None = None,
        playback_state_repo: PlaybackStateRepo | None = None,
        stream_proxy_service: StreamProxyService | None = None,
        waveform_progress_enabled: bool = False,
        randomizer: random.Random | None = None,
    ) -> None:
        self._playback_engine = playback_engine
        self._logger = logger
        self._music_service = music_service
        self._library_cache_repo = library_cache_repo
        self._playback_state_repo = playback_state_repo
        self._stream_proxy_service = stream_proxy_service
        self._waveform_progress_enabled = waveform_progress_enabled and self._WAVEFORM_SUPPORTED
        self._randomizer = randomizer or random.Random()
        self._queue: list[QueueItem] = []
        self._active_index: int | None = None
        self._active_item_loaded = False
        self._restored_position_ms = 0
        self._pending_restore_seek_ms = 0
        self._repeat_mode = RepeatMode.OFF
        self._shuffle_enabled = False
        self._volume = 100
        self._play_order: list[int] = []
        self._play_order_position: int | None = None
        self._last_observed_status = PlaybackStatus.STOPPED
        self._last_position_persisted_at = 0.0
        self._telemetry_session: _PlaybackTelemetrySession | None = None
        self._stream_prefetch_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="yaymp-stream-prefetch",
        )
        self._stream_prefetch_shutdown = False
        self._stream_prefetch_lock = Lock()
        self._stream_prefetch_in_flight: set[str] = set()
        self._stream_prefetch_results: dict[str, tuple[str, datetime]] = {}
        self._playback_engine.on_ready_for_seek(self._apply_pending_restore_seek)

    def shutdown(self) -> None:
        self._stream_prefetch_shutdown = True
        self._stream_prefetch_executor.shutdown(wait=False, cancel_futures=True)
        if self._stream_proxy_service is not None:
            self._stream_proxy_service.shutdown()

    def wait_for_pending_telemetry(self, *, timeout: float = 5.0) -> None:
        del timeout
        return

    def wait_for_pending_stream_prefetch(self, *, timeout: float = 5.0) -> None:
        if self._stream_prefetch_shutdown:
            return
        future = self._submit_stream_prefetch(lambda: None)
        if future is not None:
            future.result(timeout=timeout)

    def persist_current_state(self) -> None:
        self._persist_playback_queue(position_ms=self._current_position_ms())

    def replace_queue(
        self,
        tracks: Sequence[Track],
        *,
        start_index: int = 0,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        tracks = merge_cached_liked_states(
            tuple(tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        return self._replace_queue_items(
            tuple(
                self._build_queue_item(
                    track,
                    source_type=source_type,
                    source_id=source_id,
                    source_index=index,
                )
                for index, track in enumerate(tracks)
            ),
            start_index=start_index,
        )

    def append_queue(
        self,
        tracks: Sequence[Track],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        start_source_index = sum(
            1
            for item in self._queue
            if item.source_type == source_type and item.source_id == source_id
        )
        tracks = merge_cached_liked_states(
            tuple(tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        for offset, track in enumerate(tracks):
            self._queue.append(
                self._build_queue_item(
                    track,
                    source_type=source_type,
                    source_id=source_id,
                    source_index=start_source_index + offset,
                )
            )
        self._rebuild_play_order(anchor_index=self._active_index)
        self._logger.info("Appended %s tracks to queue", len(tracks))
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def insert_queue_next(
        self,
        tracks: Sequence[Track],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        if not tracks:
            return self.snapshot()
        if not self._queue or self._active_index is None:
            return self.append_queue(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )

        start_source_index = sum(
            1
            for item in self._queue
            if item.source_type == source_type and item.source_id == source_id
        )
        normalized_tracks = merge_cached_liked_states(
            tuple(tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        insert_at = self._active_index + 1
        for offset, track in enumerate(normalized_tracks):
            self._queue.insert(
                insert_at + offset,
                self._build_queue_item(
                    track,
                    source_type=source_type,
                    source_id=source_id,
                    source_index=start_source_index + offset,
                ),
            )
        self._rebuild_play_order(anchor_index=self._active_index)
        self._logger.info("Inserted %s tracks to play next", len(normalized_tracks))
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def restore_saved_queue(self) -> PlaybackSnapshot:
        if self._playback_state_repo is None:
            return self.snapshot()
        try:
            saved_queue = self._playback_state_repo.load_playback_queue()
        except Exception as exc:
            self._logger.warning("Failed to restore playback queue: %s", exc)
            self._clear_persisted_playback_queue()
            return self.snapshot()

        if saved_queue is None or not saved_queue.queue:
            return self.snapshot()

        self._queue = [
            self._build_queue_item(
                merge_cached_liked_state(
                    item.track,
                    self._library_cache_repo,
                    user_id=self._current_user_id(),
                ),
                source_type=item.source_type,
                source_id=item.source_id,
                source_index=item.source_index,
                station_batch_id=item.station_batch_id,
                radio_session_id=item.radio_session_id,
                radio_origin=item.radio_origin,
                radio_queue_anchor_track_id=item.radio_queue_anchor_track_id,
            )
            for item in saved_queue.queue
        ]
        if saved_queue.active_index is None:
            self._active_index = 0
        else:
            self._active_index = max(0, min(len(self._queue) - 1, saved_queue.active_index))
        self._active_item_loaded = False
        self._restored_position_ms = saved_queue.position_ms
        self._rebuild_play_order(anchor_index=self._active_index)
        self._logger.info("Restored %s playback queue items", len(self._queue))
        return self.snapshot()

    def snapshot(self) -> PlaybackSnapshot:
        self._ensure_station_queue_capacity(min_remaining=self._STATION_QUEUE_REFILL_THRESHOLD)
        return self._build_snapshot(self._playback_engine.get_state())

    def current_item(self) -> QueueItem | None:
        if self._active_index is None:
            return None
        if self._active_index < 0 or self._active_index >= len(self._queue):
            return None
        return self._queue[self._active_index]

    def play(self) -> PlaybackSnapshot:
        if self.current_item() is None:
            raise PlaybackBackendError("No active queue item to play")
        started_at = monotonic()
        if not self._active_item_loaded:
            self._pending_restore_seek_ms = self._restored_position_ms
            load_started_at = monotonic()
            self._load_current_item()
            self._logger.debug(
                "Playback load_current_item took %.3fs",
                monotonic() - load_started_at,
            )
        engine_play_started_at = monotonic()
        self._playback_engine.play()
        self._logger.debug(
            "Playback engine play took %.3fs",
            monotonic() - engine_play_started_at,
        )
        self._report_playback_started()
        self._logger.info("Playback started for index %s", self._active_index)
        snapshot = self.snapshot()
        self._logger.debug("Playback start path took %.3fs", monotonic() - started_at)
        return snapshot

    def pause(self) -> PlaybackSnapshot:
        self._playback_engine.pause()
        self._logger.info("Playback paused")
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def toggle_play_pause(self) -> PlaybackSnapshot:
        state = self.snapshot().state
        if state.status is PlaybackStatus.PLAYING:
            return self.pause()
        return self.play()

    def stop(self) -> PlaybackSnapshot:
        self._finalize_active_playback(natural_end=False)
        self._playback_engine.stop()
        self._logger.info("Playback stopped")
        self._persist_playback_queue(position_ms=0)
        return self.snapshot()

    def clear_queue(self) -> PlaybackSnapshot:
        self._finalize_active_playback(natural_end=False)
        self._playback_engine.stop()
        self._queue = []
        self._active_index = None
        self._active_item_loaded = False
        self._restored_position_ms = 0
        self._pending_restore_seek_ms = 0
        self._play_order = []
        self._play_order_position = None
        self._last_observed_status = PlaybackStatus.STOPPED
        self._telemetry_session = None
        self._clear_persisted_playback_queue()
        self._logger.info("Playback queue cleared")
        return self.snapshot()

    def play_track(
        self,
        track: Track,
        *,
        source_type: str | None = "track",
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        return self.replace_queue(
            (track,),
            start_index=0,
            source_type=source_type,
            source_id=source_id or track.id,
        )

    def play_track_by_id(self, track_id: str) -> PlaybackSnapshot:
        if self._music_service is None:
            raise PlaybackBackendError("Music service is not configured")
        track = merge_cached_liked_state(
            self._music_service.get_track(track_id),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        return self.play_track(track, source_type="track", source_id=track_id)

    def play_station(self, station_id: str) -> PlaybackSnapshot:
        if self._music_service is None:
            raise PlaybackBackendError("Music service is not configured")
        started_at = monotonic()
        radio_session = self._music_service.start_radio_session(
            station_id,
            limit=self._STATION_QUEUE_BATCH_SIZE,
        )
        self._logger.debug(
            "Station session start took %.3fs for %s",
            monotonic() - started_at,
            station_id,
        )
        tracks = merge_cached_liked_states(
            radio_session.tracks,
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        if not tracks:
            raise PlaybackBackendError(f"Station {station_id} returned no tracks")
        self._report_radio_session_started(radio_session)
        return self._replace_queue_items(
            tuple(
                self._build_queue_item(
                    track,
                    source_type="station",
                    source_id=station_id,
                    source_index=index,
                    station_batch_id=radio_session.batch_id,
                    radio_session_id=radio_session.session_id,
                    radio_origin=radio_session.feedback_from,
                    radio_queue_anchor_track_id=radio_session.queue_anchor_track_id,
                )
                for index, track in enumerate(tracks)
            ),
            start_index=0,
        )

    def next(self) -> PlaybackSnapshot:
        return self._advance_to_next_track(natural_end=False)

    def previous(self) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._repeat_mode is RepeatMode.ONE:
            self.seek(0)
            self._finalize_active_playback(natural_end=False)
            self._activate_index(self._active_index)
            return self.play()

        current_state = self._playback_engine.get_state()
        if current_state.position_ms > 3_000:
            self.seek(0)
            return self.snapshot()

        self._finalize_active_playback(natural_end=False)
        previous_index = self._resolve_previous_index()
        self._activate_index(previous_index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def seek(self, position_ms: int) -> PlaybackSnapshot:
        self._playback_engine.seek(position_ms)
        if self._telemetry_session is not None:
            bounded_position_ms = max(0, position_ms)
            self._telemetry_session.last_known_position_ms = bounded_position_ms
            self._telemetry_session.last_accounted_position_ms = bounded_position_ms
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def refresh(self) -> PlaybackSnapshot:
        engine_state = self._playback_engine.get_state()
        self._update_telemetry_position(engine_state)
        if self._should_auto_advance(engine_state):
            self._finalize_active_playback(natural_end=True, engine_state=engine_state)
            return self._advance_to_next_track(natural_end=True, finalize_current=False)
        self._prefetch_queue_ahead()
        self._persist_playback_position_if_due(engine_state)
        return self._build_snapshot(engine_state)

    def set_volume(self, volume: int) -> PlaybackSnapshot:
        bounded_volume = max(0, min(100, volume))
        self._volume = bounded_volume
        self._playback_engine.set_volume(self._ui_volume_to_engine_volume(bounded_volume))
        return self.snapshot()

    def set_repeat_mode(self, repeat_mode: RepeatMode) -> PlaybackSnapshot:
        self._repeat_mode = repeat_mode
        return self.snapshot()

    def set_waveform_progress_enabled(self, enabled: bool) -> PlaybackSnapshot:
        self._waveform_progress_enabled = enabled and self._WAVEFORM_SUPPORTED
        return self.snapshot()

    def set_shuffle_enabled(self, enabled: bool) -> PlaybackSnapshot:
        self._shuffle_enabled = enabled
        self._rebuild_play_order(anchor_index=self._active_index)
        return self.snapshot()

    def select_index(self, index: int) -> PlaybackSnapshot:
        if index < 0 or index >= len(self._queue):
            raise PlaybackBackendError("Queue index is out of range")
        self._finalize_active_playback(natural_end=False)
        self._activate_index(index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def move_queue_item_next(self, index: int) -> PlaybackSnapshot:
        if index < 0 or index >= len(self._queue):
            raise PlaybackBackendError("Queue index is out of range")
        if not self._queue:
            raise PlaybackBackendError("Playback queue cannot be empty")
        if self._active_index is None:
            target_index = 0
        else:
            target_index = min(self._active_index + 1, len(self._queue) - 1)
        if index == target_index:
            return self.snapshot()

        item = self._queue.pop(index)
        if self._active_index is not None and index < self._active_index:
            self._active_index -= 1
            target_index = min(self._active_index + 1, len(self._queue))
        self._queue.insert(target_index, item)
        if self._active_index is not None and target_index <= self._active_index:
            self._active_index += 1
        self._rebuild_play_order(anchor_index=self._active_index)
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def move_queue_item(self, source_index: int, target_index: int) -> PlaybackSnapshot:
        if source_index < 0 or source_index >= len(self._queue):
            raise PlaybackBackendError("Queue index is out of range")
        if target_index < 0 or target_index >= len(self._queue):
            raise PlaybackBackendError("Queue target index is out of range")
        if source_index == target_index:
            return self.snapshot()

        item = self._queue.pop(source_index)
        self._queue.insert(target_index, item)

        if self._active_index == source_index:
            self._active_index = target_index
        elif self._active_index is not None:
            if source_index < self._active_index <= target_index:
                self._active_index -= 1
            elif target_index <= self._active_index < source_index:
                self._active_index += 1

        self._rebuild_play_order(anchor_index=self._active_index)
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def remove_queue_index(self, index: int) -> PlaybackSnapshot:
        if index < 0 or index >= len(self._queue):
            raise PlaybackBackendError("Queue index is out of range")

        removing_active = self._active_index == index
        if removing_active:
            self._finalize_active_playback(natural_end=False)
        del self._queue[index]

        if not self._queue:
            self._playback_engine.stop()
            self._active_index = None
            self._active_item_loaded = False
            self._restored_position_ms = 0
            self._pending_restore_seek_ms = 0
            self._play_order = []
            self._play_order_position = None
            self._last_observed_status = PlaybackStatus.STOPPED
            self._telemetry_session = None
            self._clear_persisted_playback_queue()
            return self.snapshot()

        if self._active_index is not None and index < self._active_index:
            self._active_index -= 1

        if removing_active:
            replacement_index = min(index, len(self._queue) - 1)
            self._activate_index(replacement_index)
            snapshot = self.play()
            self._persist_playback_queue(position_ms=0)
            return snapshot

        self._rebuild_play_order(anchor_index=self._active_index)
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def _resolve_next_index(self) -> int | None:
        if not self._queue or self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._play_order_position is None:
            self._rebuild_play_order(anchor_index=self._active_index)

        assert self._play_order_position is not None
        next_position = self._play_order_position + 1
        if next_position >= len(self._play_order):
            if self._repeat_mode is RepeatMode.ALL:
                next_position = 0
            else:
                return None
        self._play_order_position = next_position
        return self._play_order[next_position]

    def _resolve_previous_index(self) -> int:
        if not self._queue or self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._play_order_position is None:
            self._rebuild_play_order(anchor_index=self._active_index)

        assert self._play_order_position is not None
        previous_position = self._play_order_position - 1
        if previous_position < 0:
            if self._repeat_mode is RepeatMode.ALL:
                previous_position = len(self._play_order) - 1
            else:
                previous_position = 0
        self._play_order_position = previous_position
        return self._play_order[previous_position]

    def _activate_index(self, index: int, *, preserve_restored_position: bool = False) -> None:
        current_item = self._queue[index]
        prepare_started_at = monotonic()
        prepared_item = self._prepare_queue_item(current_item)
        self._logger.debug(
            "Playback prepare queue item took %.3fs for track %s",
            monotonic() - prepare_started_at,
            prepared_item.track.id,
        )
        self._queue[index] = prepared_item
        stream_ref = prepared_item.track.stream_ref or ""
        playback_stream_ref = stream_ref
        if (
            self._waveform_progress_enabled
            and (
            self._stream_proxy_service is not None
            and stream_ref.startswith(("http://", "https://"))
            )
        ):
            playback_stream_ref = self._stream_proxy_service.create_session(
                track=prepared_item.track,
                stream_ref=stream_ref,
            )
        load_started_at = monotonic()
        self._playback_engine.load(prepared_item.track, stream_ref=playback_stream_ref)
        self._logger.debug(
            "Playback engine load took %.3fs for track %s",
            monotonic() - load_started_at,
            prepared_item.track.id,
        )
        self._playback_engine.set_volume(self._ui_volume_to_engine_volume(self._volume))
        self._active_index = index
        self._active_item_loaded = True
        if not preserve_restored_position:
            self._restored_position_ms = 0
        self._sync_play_order_position(index)
        self._telemetry_session = _PlaybackTelemetrySession(
            track_id=prepared_item.track.id,
            play_id=str(uuid4()),
            origin=self._play_origin_for_item(prepared_item),
            accumulated_played_ms=0,
            last_known_position_ms=(
                self._restored_position_ms if preserve_restored_position else 0
            ),
            last_accounted_position_ms=(
                self._restored_position_ms if preserve_restored_position else 0
            ),
        )

    def _prepare_queue_item(self, item: QueueItem) -> QueueItem:
        stream_ref = item.track.stream_ref
        if not self._has_fresh_stream_ref(item.track):
            prefetched = self._take_prefetched_stream_ref(item.track.id)
            if prefetched is not None:
                stream_ref, stream_ref_cached_at = prefetched
                self._logger.debug("Using prefetched stream for track %s", item.track.id)
            elif self._music_service is None:
                raise StreamResolveError("Track has no stream reference")
            else:
                resolve_started_at = monotonic()
                stream_ref = self._music_service.resolve_stream_ref(item.track)
                stream_ref_cached_at = datetime.now(tz=UTC)
                self._logger.debug(
                    "Synchronous stream resolve took %.3fs for track %s",
                    monotonic() - resolve_started_at,
                    item.track.id,
                )
        else:
            stream_ref_cached_at = item.track.stream_ref_cached_at
        if not stream_ref:
            raise StreamResolveError("Track has no stream reference")
        if stream_ref_cached_at is not None and stream_ref_cached_at.tzinfo is None:
            stream_ref_cached_at = stream_ref_cached_at.replace(tzinfo=UTC)
        return self._queue_item_with_stream_ref(
            item,
            stream_ref=stream_ref,
            stream_ref_cached_at=stream_ref_cached_at,
        )

    def _queue_item_with_stream_ref(
        self,
        item: QueueItem,
        *,
        stream_ref: str,
        stream_ref_cached_at: datetime | None,
    ) -> QueueItem:
        return QueueItem(
            track=Track(
                id=item.track.id,
                title=item.track.title,
                artists=item.track.artists,
                version=item.track.version,
                artist_ids=item.track.artist_ids,
                album_id=item.track.album_id,
                album_title=item.track.album_title,
                album_year=item.track.album_year,
                duration_ms=item.track.duration_ms,
                stream_ref=stream_ref,
                stream_ref_cached_at=stream_ref_cached_at,
                artwork_ref=item.track.artwork_ref,
                accent_color=item.track.accent_color,
                waveform_bins=item.track.waveform_bins,
                available=item.track.available,
                is_liked=item.track.is_liked,
            ),
            source_type=item.source_type,
            source_id=item.source_id,
            source_index=item.source_index,
            station_batch_id=item.station_batch_id,
            radio_session_id=item.radio_session_id,
            radio_origin=item.radio_origin,
            radio_queue_anchor_track_id=item.radio_queue_anchor_track_id,
        )

    def _has_fresh_stream_ref(self, track: Track) -> bool:
        stream_ref = track.stream_ref
        if not stream_ref:
            return False
        if not stream_ref.startswith(("http://", "https://")):
            return True
        cached_at = track.stream_ref_cached_at
        if cached_at is None:
            return False
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - cached_at <= self._STREAM_REF_TTL

    def _rebuild_play_order(self, *, anchor_index: int | None) -> None:
        self._play_order = list(range(len(self._queue)))
        if not self._play_order:
            self._play_order_position = None
            return

        if self._shuffle_enabled:
            self._randomizer.shuffle(self._play_order)
            if anchor_index is not None and anchor_index in self._play_order:
                self._play_order.remove(anchor_index)
                self._play_order.insert(0, anchor_index)
                self._play_order_position = 0
                return

        if anchor_index is None:
            self._play_order_position = 0
            return
        self._play_order_position = self._play_order.index(anchor_index)

    def _sync_play_order_position(self, index: int) -> None:
        if index not in self._play_order:
            self._rebuild_play_order(anchor_index=index)
            return
        self._play_order_position = self._play_order.index(index)

    def _load_current_item(self) -> None:
        current_item = self.current_item()
        if current_item is None:
            raise PlaybackBackendError("No current queue item")
        self._activate_index(
            self._active_index if self._active_index is not None else 0,
            preserve_restored_position=True,
        )

    def _compose_state(self, engine_state: PlaybackState) -> PlaybackState:
        position_ms = engine_state.position_ms
        if self.current_item() is not None and not self._active_item_loaded:
            position_ms = self._restored_position_ms
        waveform = WaveformState()
        current_item = self.current_item()
        effective_duration_ms = engine_state.duration_ms or (
            current_item.track.duration_ms if current_item is not None else None
        )
        if (
            self._waveform_progress_enabled
            and self._stream_proxy_service is not None
            and current_item is not None
        ):
            waveform = self._stream_proxy_service.get_waveform_state(current_item.track.id)
            if waveform.waveform_bins and current_item.track.waveform_bins:
                waveform = WaveformState(
                    buffered_position_ms=waveform.buffered_position_ms,
                    waveform_bins=waveform.waveform_bins,
                    waveform_known_position_ms=max(
                        waveform.waveform_known_position_ms,
                        current_item.track.duration_ms or 0,
                        effective_duration_ms or 0,
                    ),
                    waveform_mode=waveform.waveform_mode,
                )
            if (
                waveform.waveform_bins
                and current_item.track.duration_ms
                and waveform.waveform_known_position_ms >= current_item.track.duration_ms
                and not current_item.track.waveform_bins
            ):
                self._promote_cached_waveform_to_queue(
                    track_id=current_item.track.id,
                    waveform_bins=waveform.waveform_bins,
                )
                current_item = self.current_item()
        if (
            self._waveform_progress_enabled
            and current_item is not None
            and current_item.track.waveform_bins
            and (not waveform.waveform_bins or waveform.waveform_mode == "plain")
        ):
            known_duration_ms = max(
                current_item.track.duration_ms or 0,
                effective_duration_ms or 0,
            )
            waveform = WaveformState(
                buffered_position_ms=waveform.buffered_position_ms,
                waveform_bins=current_item.track.waveform_bins,
                waveform_known_position_ms=known_duration_ms,
                waveform_mode="cached",
            )
        return PlaybackState(
            status=engine_state.status,
            active_index=self._active_index,
            position_ms=position_ms,
            duration_ms=effective_duration_ms,
            volume=self._volume,
            shuffle_enabled=self._shuffle_enabled,
            repeat_mode=self._repeat_mode,
            audio_codec=engine_state.audio_codec,
            audio_bitrate=engine_state.audio_bitrate,
            waveform=waveform,
        )

    def _promote_cached_waveform_to_queue(
        self,
        *,
        track_id: str,
        waveform_bins: tuple[float, ...],
    ) -> None:
        updated = False
        new_queue: list[QueueItem] = []
        for item in self._queue:
            if item.track.id != track_id or item.track.waveform_bins:
                new_queue.append(item)
                continue
            new_queue.append(replace(item, track=replace(item.track, waveform_bins=waveform_bins)))
            updated = True
        if updated:
            self._queue = new_queue

    def _ui_volume_to_engine_volume(self, volume: int) -> int:
        if volume <= 0:
            return 0
        normalized = max(0.0, min(1.0, volume / 100.0))
        return round(math.sqrt(normalized) * 100)

    def _build_snapshot(self, engine_state: PlaybackState) -> PlaybackSnapshot:
        state = self._compose_state(engine_state)
        self._last_observed_status = state.status
        return PlaybackSnapshot(
            queue=tuple(self._queue),
            state=state,
            current_item=self.current_item(),
        )

    def _should_auto_advance(self, engine_state: PlaybackState) -> bool:
        return (
            engine_state.status is PlaybackStatus.STOPPED
            and self._last_observed_status is PlaybackStatus.PLAYING
            and self.current_item() is not None
        )

    def _ensure_station_queue_capacity(self, *, min_remaining: int) -> None:
        current_item = self.current_item()
        if current_item is None or current_item.source_type != "station":
            return
        if self._music_service is None or self._active_index is None:
            return

        remaining = len(self._queue) - self._active_index - 1
        if remaining >= min_remaining:
            return

        station_id = current_item.source_id
        if not station_id:
            return

        existing_ids = {item.track.id for item in self._queue}
        next_source_index = len(self._queue)
        appended = 0

        for _attempt in range(self._STATION_QUEUE_REFILL_MAX_ATTEMPTS):
            remaining = len(self._queue) - self._active_index - 1
            if remaining >= min_remaining:
                break

            radio_session = self._radio_session_for_queue_tail()
            if radio_session is None:
                break
            refill_count = max(1, min_remaining - remaining)
            radio_session = self._music_service.get_radio_session_tracks(
                radio_session,
                limit=refill_count,
            )
            fetched_tracks = merge_cached_liked_states(
                radio_session.tracks,
                self._library_cache_repo,
                user_id=self._current_user_id(),
            )
            if not fetched_tracks:
                break

            appended_this_attempt = 0
            for track in fetched_tracks:
                if track.id in existing_ids:
                    continue
                self._queue.append(
                    self._build_queue_item(
                        track,
                        source_type="station",
                        source_id=station_id,
                        source_index=next_source_index,
                        station_batch_id=radio_session.batch_id,
                        radio_session_id=radio_session.session_id,
                        radio_origin=radio_session.feedback_from,
                        radio_queue_anchor_track_id=radio_session.queue_anchor_track_id,
                    )
                )
                existing_ids.add(track.id)
                next_source_index += 1
                appended += 1
                appended_this_attempt += 1

            if appended_this_attempt == 0:
                continue

        if appended > 0:
            self._logger.info("Appended %s station tracks for %s", appended, station_id)
            self._trim_station_queue()
            self._rebuild_play_order(anchor_index=self._active_index)
            self._persist_playback_queue(position_ms=self._current_position_ms())

    def _prefetch_queue_ahead(self) -> None:
        self._ensure_station_queue_capacity(
            min_remaining=max(
                self._STATION_QUEUE_REFILL_THRESHOLD,
                self._STREAM_PREFETCH_AHEAD,
            )
        )
        if self._active_index is None:
            return
        last_index = min(
            len(self._queue),
            self._active_index + self._STREAM_PREFETCH_AHEAD + 1,
        )
        for index in range(self._active_index + 1, last_index):
            item = self._queue[index]
            if self._has_fresh_stream_ref(item.track):
                continue
            if self._apply_prefetched_stream_ref(index, item):
                continue
            self._schedule_stream_prefetch(item.track)

    def _submit_stream_prefetch(self, callback: Callable[[], None]) -> Future | None:
        if self._stream_prefetch_shutdown:
            return None
        try:
            return self._stream_prefetch_executor.submit(callback)
        except RuntimeError:
            return None

    def _schedule_stream_prefetch(self, track: Track) -> None:
        if self._music_service is None:
            return
        if self._has_fresh_stream_ref(track):
            return
        music_service = self._music_service
        with self._stream_prefetch_lock:
            if track.id in self._stream_prefetch_results:
                return
            if track.id in self._stream_prefetch_in_flight:
                return
            self._stream_prefetch_in_flight.add(track.id)

        def prefetch_safely() -> None:
            try:
                started_at = monotonic()
                stream_ref = music_service.resolve_stream_ref(track)
                cached_at = datetime.now(tz=UTC)
                elapsed = monotonic() - started_at
                if not stream_ref:
                    raise StreamResolveError("Track has no stream reference")
                with self._stream_prefetch_lock:
                    self._stream_prefetch_results[track.id] = (stream_ref, cached_at)
                self._logger.debug(
                    "Async stream prefetch took %.3fs for track %s",
                    elapsed,
                    track.id,
                )
            except Exception as exc:
                self._logger.warning(
                    "Failed to prefetch stream for track %s: %s",
                    track.id,
                    exc,
                )
            finally:
                with self._stream_prefetch_lock:
                    self._stream_prefetch_in_flight.discard(track.id)

        future = self._submit_stream_prefetch(prefetch_safely)
        if future is None:
            with self._stream_prefetch_lock:
                self._stream_prefetch_in_flight.discard(track.id)

    def _take_prefetched_stream_ref(self, track_id: str) -> tuple[str, datetime] | None:
        with self._stream_prefetch_lock:
            return self._stream_prefetch_results.pop(track_id, None)

    def _apply_prefetched_stream_ref(self, index: int, item: QueueItem) -> bool:
        prefetched = self._take_prefetched_stream_ref(item.track.id)
        if prefetched is None:
            return False
        stream_ref, cached_at = prefetched
        self._queue[index] = self._queue_item_with_stream_ref(
            item,
            stream_ref=stream_ref,
            stream_ref_cached_at=cached_at,
        )
        self._logger.debug("Applied prefetched stream for track %s", item.track.id)
        return True

    def _trim_station_queue(self) -> None:
        current_item = self.current_item()
        if current_item is None or current_item.source_type != "station":
            return
        if self._active_index is None or len(self._queue) <= self._STATION_QUEUE_MAX_LENGTH:
            return

        drop_count = max(
            len(self._queue) - self._STATION_QUEUE_MAX_LENGTH,
            self._active_index - self._STATION_QUEUE_RETAIN_BEFORE_ACTIVE,
        )
        drop_count = max(0, min(drop_count, self._active_index))
        if drop_count <= 0:
            return

        del self._queue[:drop_count]
        self._active_index -= drop_count

    def _persist_playback_position_if_due(self, engine_state: PlaybackState) -> None:
        if self.current_item() is None:
            return
        now = monotonic()
        if now - self._last_position_persisted_at < self._POSITION_PERSIST_INTERVAL_SECONDS:
            return
        self._persist_playback_queue(position_ms=engine_state.position_ms)

    def _apply_pending_restore_seek(self) -> None:
        if self._pending_restore_seek_ms <= 0:
            return
        position_ms = self._pending_restore_seek_ms
        try:
            self._playback_engine.seek(position_ms)
        except PlaybackBackendError as exc:
            self._pending_restore_seek_ms = 0
            self._restored_position_ms = 0
            self._logger.warning("Failed to restore playback position: %s", exc)
            return

        self._pending_restore_seek_ms = 0
        self._restored_position_ms = 0
        self._persist_playback_queue(position_ms=position_ms)

    def _persist_playback_queue(self, *, position_ms: int | None = None) -> None:
        if self._playback_state_repo is None:
            return
        queue, active_index = self._queue_for_persistence()
        if position_ms is None:
            position_ms = self._current_position_ms()
        try:
            self._playback_state_repo.save_playback_queue(
                queue,
                active_index=active_index,
                position_ms=position_ms if queue else 0,
            )
            self._last_position_persisted_at = monotonic()
        except Exception as exc:
            self._logger.warning("Failed to save playback queue: %s", exc)

    def _clear_persisted_playback_queue(self) -> None:
        if self._playback_state_repo is None:
            return
        try:
            self._playback_state_repo.clear_playback_queue()
        except Exception as exc:
            self._logger.warning("Failed to clear saved playback queue: %s", exc)

    def _queue_for_persistence(self) -> tuple[tuple[QueueItem, ...], int | None]:
        active_item = self.current_item()
        if active_item is not None and active_item.source_type == "demo":
            return (), None
        if (
            active_item is None
            or active_item.source_type != "station"
            or self._active_index is None
        ):
            return tuple(self._queue), self._active_index if self._queue else None

        start_index = max(0, self._active_index - self._STATION_QUEUE_RETAIN_BEFORE_ACTIVE)
        end_index = min(len(self._queue), start_index + self._STATION_QUEUE_PERSIST_LENGTH)
        if end_index - start_index < self._STATION_QUEUE_PERSIST_LENGTH:
            start_index = max(0, end_index - self._STATION_QUEUE_PERSIST_LENGTH)
        return tuple(self._queue[start_index:end_index]), self._active_index - start_index

    def _current_position_ms(self) -> int:
        if self.current_item() is not None and not self._active_item_loaded:
            return self._restored_position_ms
        return self._playback_engine.get_state().position_ms

    def _current_user_id(self) -> str | None:
        if self._music_service is None:
            return None
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None

    def _replace_queue_items(
        self,
        queue_items: tuple[QueueItem, ...],
        *,
        start_index: int,
    ) -> PlaybackSnapshot:
        if not queue_items:
            raise PlaybackBackendError("Playback queue cannot be empty")
        if start_index < 0 or start_index >= len(queue_items):
            raise PlaybackBackendError("Playback start index is out of range")

        previous_queue = self._queue
        previous_index = self._active_index
        previous_loaded = self._active_item_loaded
        previous_order = self._play_order
        previous_order_position = self._play_order_position
        previous_telemetry_session = self._telemetry_session

        self._finalize_active_playback(natural_end=False)
        self._queue = list(queue_items)
        self._rebuild_play_order(anchor_index=start_index)

        try:
            self._activate_index(start_index)
            snapshot = self.play()
            self._persist_playback_queue(position_ms=0)
            return snapshot
        except Exception:
            self._queue = previous_queue
            self._active_index = previous_index
            self._active_item_loaded = previous_loaded
            self._play_order = previous_order
            self._play_order_position = previous_order_position
            self._telemetry_session = previous_telemetry_session
            raise

    def _build_queue_item(
        self,
        track: Track,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        source_index: int | None = None,
        station_batch_id: str | None = None,
        radio_session_id: str | None = None,
        radio_origin: str | None = None,
        radio_queue_anchor_track_id: str | None = None,
    ) -> QueueItem:
        track = self._hydrate_cached_waveform(track)
        return QueueItem(
            track=track,
            source_type=source_type,
            source_id=source_id,
            source_index=source_index,
            station_batch_id=station_batch_id,
            radio_session_id=radio_session_id,
            radio_origin=radio_origin,
            radio_queue_anchor_track_id=radio_queue_anchor_track_id,
        )

    def _hydrate_cached_waveform(self, track: Track) -> Track:
        if track.waveform_bins or self._library_cache_repo is None:
            return track
        cached_track = self._library_cache_repo.load_track_metadata(track.id)
        if cached_track is None or not cached_track.waveform_bins:
            return track
        return Track(
            id=track.id,
            title=track.title,
            artists=track.artists,
            version=track.version,
            artist_ids=track.artist_ids,
            album_id=track.album_id,
            album_title=track.album_title,
            album_year=track.album_year,
            duration_ms=track.duration_ms,
            stream_ref=track.stream_ref,
            stream_ref_cached_at=track.stream_ref_cached_at,
            artwork_ref=track.artwork_ref,
            accent_color=track.accent_color,
            waveform_bins=cached_track.waveform_bins,
            available=track.available,
            is_liked=track.is_liked,
        )

    def _advance_to_next_track(
        self,
        *,
        natural_end: bool,
        finalize_current: bool = True,
    ) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if finalize_current:
            self._finalize_active_playback(natural_end=natural_end)

        if self._repeat_mode is RepeatMode.ONE:
            self._activate_index(self._active_index)
            return self.play()

        self._ensure_station_queue_capacity(min_remaining=1)
        next_index = self._resolve_next_index()
        if next_index is None:
            self._playback_engine.stop()
            self._telemetry_session = None
            self._last_observed_status = PlaybackStatus.STOPPED
            return self.snapshot()

        self._activate_index(next_index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def _play_origin_for_item(self, item: QueueItem) -> str:
        if item.source_type == "station":
            if item.source_id == "plex:random":
                return self._PLAY_ORIGIN_MY_WAVE
            return self._PLAY_ORIGIN_STATION
        return self._PLAY_ORIGIN_DESKTOP

    def _report_playback_started(self) -> None:
        session = self._telemetry_session
        if session is None or session.started:
            return
        now_iso = self._utc_now_iso()
        session.plays_start_timestamp_iso = now_iso
        session.plays_add_tracks_to_player_time = now_iso
        session.started = True

    def _finalize_active_playback(
        self,
        *,
        natural_end: bool,
        engine_state: PlaybackState | None = None,
    ) -> None:
        current_item = self.current_item()
        if current_item is None:
            return
        session = self._telemetry_session
        try:
            if session is None or session.terminal_reported or not session.started:
                return
            del natural_end, engine_state
            session.terminal_reported = True
        finally:
            self._close_stream_proxy_for_track(current_item.track.id)

    def _close_stream_proxy_for_track(self, track_id: str) -> None:
        if self._stream_proxy_service is not None:
            self._stream_proxy_service.close_track_session(track_id)

    def _should_treat_station_track_as_finished(
        self,
        track: Track,
        *,
        played_seconds: float,
        natural_end: bool,
    ) -> bool:
        if natural_end:
            return True
        if track.duration_ms is None or track.duration_ms <= 0:
            return False
        duration_seconds = track.duration_ms / 1000.0
        if played_seconds >= duration_seconds * self._STATION_FINISHED_RATIO:
            return True
        return duration_seconds - played_seconds <= self._STATION_FINISHED_REMAINING_SECONDS

    def _update_telemetry_position(self, engine_state: PlaybackState) -> None:
        if self._telemetry_session is None:
            return
        if engine_state.status is PlaybackStatus.PLAYING:
            delta_ms = engine_state.position_ms - self._telemetry_session.last_accounted_position_ms
            if delta_ms > 0:
                self._telemetry_session.accumulated_played_ms += delta_ms
            self._telemetry_session.last_accounted_position_ms = max(0, engine_state.position_ms)
        position_ms = engine_state.position_ms
        if position_ms <= 0 and engine_state.status is PlaybackStatus.STOPPED:
            return
        self._telemetry_session.last_known_position_ms = max(0, position_ms)

    def _track_length_seconds(self, track: Track) -> int:
        if track.duration_ms is None:
            return 0
        return max(0, int(track.duration_ms // 1000))

    def _track_length_seconds_float(self, track: Track) -> float:
        if track.duration_ms is None:
            return 0.0
        return round(max(0.0, track.duration_ms / 1000.0), 3)

    def _utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _debug_logging_enabled(self) -> bool:
        is_enabled_for = getattr(self._logger, "isEnabledFor", None)
        if callable(is_enabled_for):
            try:
                import logging

                return bool(is_enabled_for(logging.DEBUG))
            except Exception:
                return False
        return False

    def _log_telemetry_failure(
        self,
        message: str,
        *args: object,
        exc: Exception,
    ) -> None:
        if self._debug_logging_enabled():
            self._logger.exception(f"{message}: %r", *args, exc)
            return
        self._logger.warning(f"{message}: %s", *args, exc)

    def _submit_telemetry(self, callback: Callable[[], None]) -> Future | None:
        del callback
        return None

    def _report_play_audio(
        self,
        track: Track,
        *,
        origin: str,
        play_id: str,
        track_length_seconds: int,
        total_played_seconds: int,
        end_position_seconds: int,
        playlist_id: str | None = None,
        timestamp_iso: str | None = None,
    ) -> None:
        del (
            track,
            origin,
            play_id,
            track_length_seconds,
            total_played_seconds,
            end_position_seconds,
            playlist_id,
            timestamp_iso,
        )
        return

    def _report_plays_event(
        self,
        current_item: QueueItem,
        *,
        timestamp_iso: str,
        total_played_seconds: float,
        end_position_seconds: float,
        change_reason: str | None = None,
    ) -> None:
        del (
            current_item,
            timestamp_iso,
            total_played_seconds,
            end_position_seconds,
            change_reason,
        )
        return

    def _play_audio_playlist_id(self, item: QueueItem) -> str | None:
        scrobble = self._scrobble_context_for_item(item)
        if scrobble is None:
            return None
        return scrobble.playlist_id

    def _scrobble_context_for_item(self, item: QueueItem) -> _ScrobbleContext | None:
        user_id = self._current_user_id()
        liked_playlist_id = (
            f"{user_id}:{self._SCROBBLE_PLAYLIST_LIKES_KIND}" if user_id is not None else None
        )
        if item.source_type == "station" and item.source_id and item.radio_session_id:
            return _ScrobbleContext(
                from_=item.radio_origin or self._radio_scrobble_from(item.source_id),
                context="radio",
                context_item=item.source_id,
                album_id=item.track.album_id,
                radio_session_id=item.radio_session_id,
                batch_id=item.station_batch_id,
            )
        if item.source_type == "playlist":
            playlist_id = self._playlist_context_id(item.source_id, fallback_user_id=user_id)
            if playlist_id is None:
                return None
            return _ScrobbleContext(
                from_=self._SCROBBLE_PLAYLIST_FROM,
                context="playlist",
                context_item=playlist_id,
                album_id=item.track.album_id,
                playlist_id=playlist_id,
            )
        if item.source_type == "collection" and liked_playlist_id is not None:
            return _ScrobbleContext(
                from_=self._SCROBBLE_PLAYLIST_FROM,
                context="playlist",
                context_item=liked_playlist_id,
                album_id=item.track.album_id,
                playlist_id=liked_playlist_id,
            )
        if item.source_type == "artist":
            artist_id = item.source_id or next(iter(item.track.artist_ids), None)
            if artist_id is None:
                return None
            return _ScrobbleContext(
                from_=self._SCROBBLE_ARTIST_FROM,
                context="artist",
                context_item=artist_id,
                album_id=item.track.album_id,
            )
        if item.source_type == "album" and item.track.album_id is not None:
            return _ScrobbleContext(
                from_=self._SCROBBLE_ALBUM_FROM,
                context="album",
                context_item=item.track.album_id,
                album_id=item.track.album_id,
            )
        if liked_playlist_id is not None:
            return _ScrobbleContext(
                from_=self._SCROBBLE_PLAYLIST_FROM,
                context="playlist",
                context_item=liked_playlist_id,
                album_id=item.track.album_id,
                playlist_id=liked_playlist_id,
            )
        if item.track.album_id is not None:
            return _ScrobbleContext(
                from_=self._SCROBBLE_ALBUM_FROM,
                context="album",
                context_item=item.track.album_id,
                album_id=item.track.album_id,
            )
        return None

    def _playlist_context_id(
        self,
        source_id: str | None,
        *,
        fallback_user_id: str | None,
    ) -> str | None:
        if source_id is None:
            return None
        if ":" in source_id:
            return source_id
        if fallback_user_id is None:
            return None
        return f"{fallback_user_id}:{source_id}"

    def _radio_scrobble_from(self, station_id: str) -> str:
        if station_id == "plex:random":
            return "plex-random-mix"
        return f"radio-mobile-{station_id.replace(':', '-')}-default"

    def _radio_session_from_item(self, item: QueueItem) -> RadioSession | None:
        if (
            item.source_type != "station"
            or not item.source_id
            or not item.radio_session_id
            or not item.radio_origin
        ):
            return None
        return RadioSession(
            station_id=item.source_id,
            session_id=item.radio_session_id,
            batch_id=item.station_batch_id,
            feedback_from=item.radio_origin,
            queue_anchor_track_id=item.radio_queue_anchor_track_id,
            tracks=(item.track,),
        )

    def _radio_session_for_queue_tail(self) -> RadioSession | None:
        for item in reversed(self._queue):
            session = self._radio_session_from_item(item)
            if session is not None:
                return session
        return None

    def _report_radio_session_started(self, session: RadioSession) -> None:
        del session
        return

    def _report_radio_track_started(self, current_item: QueueItem) -> None:
        del current_item
        return

    def _report_radio_track_finished(
        self,
        current_item: QueueItem,
        played_seconds: float,
    ) -> None:
        del current_item, played_seconds
        return

    def _report_radio_track_skipped(
        self,
        current_item: QueueItem,
        played_seconds: float,
    ) -> None:
        del current_item, played_seconds
        return

    def _radio_feedback_track_id(self, track: Track) -> str:
        if track.album_id:
            return f"{track.id}:{track.album_id}"
        return track.id

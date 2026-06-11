from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from app.application.error_presenter import user_facing_error_message
from app.application.playback_service import PlaybackService, PlaybackSnapshot
from app.domain import Logger, RepeatMode, Track
from app.domain.errors import DomainError


class _PlaybackWorker(QObject):
    snapshot_ready = Signal(object)
    playback_failed = Signal(str)
    shutdown_flushed = Signal()

    def __init__(self, *, playback_service: PlaybackService, logger: Logger) -> None:
        super().__init__()
        self._playback_service = playback_service
        self._logger = logger

    @Slot(object)
    def execute_operation(self, operation: Callable[[], PlaybackSnapshot]) -> None:
        try:
            self.snapshot_ready.emit(operation())
        except DomainError as exc:
            self._logger.warning("Playback operation failed: %s", exc)
            self.playback_failed.emit(user_facing_error_message(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.warning("Unexpected playback operation failure: %s", exc)
            self.playback_failed.emit(str(exc))

    @Slot()
    def flush_for_shutdown(self) -> None:
        try:
            self._playback_service.persist_current_state()
        except DomainError as exc:
            self._logger.warning("Playback shutdown flush failed: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.warning("Unexpected shutdown flush failure: %s", exc)
        self.shutdown_flushed.emit()


class PlaybackController(QObject):
    playback_changed = Signal(object)
    playback_failed = Signal(str)
    _operation_requested = Signal(object)
    _shutdown_flush_requested = Signal()

    def __init__(self, *, playback_service: PlaybackService, logger: Logger) -> None:
        super().__init__()
        self._playback_service = playback_service
        self._logger = logger
        self._shutdown_started = False
        self._worker_thread = QThread(self)
        self._worker = _PlaybackWorker(
            playback_service=playback_service,
            logger=logger,
        )
        self._worker.moveToThread(self._worker_thread)
        self._operation_requested.connect(
            self._worker.execute_operation,
            Qt.ConnectionType.QueuedConnection,
        )
        self._shutdown_flush_requested.connect(
            self._worker.flush_for_shutdown,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.snapshot_ready.connect(self._emit_snapshot)
        self._worker.playback_failed.connect(self.playback_failed.emit)
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.start()

    def initialize(self) -> None:
        self._dispatch(self._playback_service.snapshot)

    def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        flush_completed = Event()
        self._worker.shutdown_flushed.connect(flush_completed.set)
        self._shutdown_flush_requested.emit()
        flush_completed.wait(timeout=10.0)
        self._worker_thread.quit()
        self._worker_thread.wait(3000)
        self._playback_service.shutdown()

    def play(self) -> None:
        self._dispatch(self._playback_service.play)

    def pause(self) -> None:
        self._dispatch(self._playback_service.pause)

    def previous(self) -> None:
        self._dispatch(self._playback_service.previous)

    def next(self) -> None:
        self._dispatch(self._playback_service.next)

    def seek(self, position_ms: int) -> None:
        self._dispatch(lambda: self._playback_service.seek(position_ms))

    def set_volume(self, volume: int) -> None:
        self._dispatch(lambda: self._playback_service.set_volume(volume))

    def set_shuffle_enabled(self, enabled: bool) -> None:
        self._dispatch(lambda: self._playback_service.set_shuffle_enabled(enabled))

    def set_repeat_mode(self, repeat_mode: RepeatMode) -> None:
        self._dispatch(lambda: self._playback_service.set_repeat_mode(repeat_mode))

    def set_waveform_progress_enabled(self, enabled: bool) -> None:
        self._dispatch(lambda: self._playback_service.set_waveform_progress_enabled(enabled))

    def select_index(self, index: int) -> None:
        self._dispatch(lambda: self._playback_service.select_index(index))

    def play_track_by_id(self, track_id: str) -> None:
        self._dispatch(lambda: self._playback_service.play_track_by_id(track_id))

    def play_track(self, track: Track) -> None:
        self._dispatch(lambda: self._playback_service.play_track(track))

    def play_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        start_index: int,
        source_type: str,
        source_id: str,
    ) -> None:
        self._dispatch(
            lambda: self._playback_service.replace_queue(
                tracks,
                start_index=start_index,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def append_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str,
        source_id: str,
    ) -> None:
        self._dispatch(
            lambda: self._playback_service.append_queue(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def play_tracks_next(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str,
        source_id: str,
    ) -> None:
        self._dispatch(
            lambda: self._playback_service.insert_queue_next(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def play_track_next(
        self,
        track: Track,
        *,
        source_type: str | None = "track",
        source_id: str | None = None,
    ) -> None:
        self._dispatch(
            lambda: self._playback_service.insert_queue_next(
                (track,),
                source_type=source_type,
                source_id=source_id or track.id,
            )
        )

    def play_station(self, station_id: str) -> None:
        self._dispatch(lambda: self._playback_service.play_station(station_id))

    def clear_queue(self) -> None:
        self._dispatch(self._playback_service.clear_queue)

    def move_queue_item_next(self, index: int) -> None:
        self._dispatch(lambda: self._playback_service.move_queue_item_next(index))

    def move_queue_item(self, source_index: int, target_index: int) -> None:
        self._dispatch(lambda: self._playback_service.move_queue_item(source_index, target_index))

    def remove_queue_index(self, index: int) -> None:
        self._dispatch(lambda: self._playback_service.remove_queue_index(index))

    def refresh(self) -> None:
        self._dispatch(self._playback_service.refresh)

    def _dispatch(self, operation: Callable[[], PlaybackSnapshot]) -> None:
        if self._shutdown_started:
            return
        self._operation_requested.emit(operation)

    def _emit_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        self.playback_changed.emit(snapshot)

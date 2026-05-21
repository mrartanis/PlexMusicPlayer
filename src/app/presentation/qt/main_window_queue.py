from __future__ import annotations

from PySide6.QtCore import QModelIndex

from app.domain.playback import QueueItem


class MainWindowQueueMixin:
    def _render_queue(self, snapshot) -> None:
        queue_key = self._queue_key(snapshot.queue)
        active_index = snapshot.state.active_index
        playback_status = snapshot.state.status
        queue_changed = queue_key != self._rendered_queue_key
        active_changed = active_index != self._rendered_active_index
        status_changed = playback_status != self._rendered_playback_status

        if queue_changed:
            self._queue_model.set_queue(snapshot.queue)
            self._rendered_queue_key = queue_key
            if (
                self._queue_selected_index is not None
                and self._queue_selected_index >= len(snapshot.queue)
            ):
                self._queue_selected_index = None
            self._restore_queue_selection()

        if queue_changed or active_changed or status_changed:
            self._queue_model.set_active_state(active_index, playback_status)
            self._queue_delegate.sync_animation(active_index, playback_status)
            self._queue_list.sync_waveform(active_index, playback_status)

        if active_changed and active_index is not None and self._should_autoscroll_queue():
            self._queue_list.scrollTo(self._queue_model.index(active_index, 0))
        self._rendered_active_index = active_index
        self._rendered_playback_status = playback_status

    def _set_queue_selected_index(self, row: int | None) -> None:
        self._queue_selected_index = row
        self._queue_model.set_selected_index(row)

    def _restore_queue_selection(self) -> None:
        selection_model = self._queue_list.selectionModel()
        if selection_model is None:
            return
        selection_model.blockSignals(True)
        try:
            if self._queue_selected_index is None:
                self._queue_list.setCurrentIndex(QModelIndex())
                selection_model.clearSelection()
                self._queue_model.set_selected_index(None)
                return
            model_index = self._queue_model.index(self._queue_selected_index, 0)
            if not model_index.isValid():
                self._queue_selected_index = None
                self._queue_model.set_selected_index(None)
                self._queue_list.setCurrentIndex(QModelIndex())
                selection_model.clearSelection()
                return
            self._queue_list.setCurrentIndex(model_index)
            self._queue_model.set_selected_index(self._queue_selected_index)
        finally:
            selection_model.blockSignals(False)

    def _queue_key(
        self,
        queue: tuple[QueueItem, ...],
    ) -> tuple[tuple[str, str, str, str, str], ...]:
        return tuple(
            (
                item.track.id,
                item.track.title,
                item.track.version or "",
                item.track.album_title or "",
                ",".join(item.track.artists),
            )
            for item in queue
        )

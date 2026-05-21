from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QListView, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from app.domain.playback import PlaybackStatus, QueueItem
from app.presentation.qt.main_window_styles import _palette_for_theme


class QueueListModel(QAbstractListModel):
    QueueItemRole = Qt.ItemDataRole.UserRole + 1
    ActiveRole = Qt.ItemDataRole.UserRole + 2
    SelectedRole = Qt.ItemDataRole.UserRole + 3
    PlaybackStatusRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: tuple[QueueItem, ...] = ()
        self._active_index: int | None = None
        self._selected_index: int | None = None
        self._playback_status = PlaybackStatus.STOPPED

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object | None:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.QueueItemRole:
            return item
        if role == self.ActiveRole:
            return index.row() == self._active_index
        if role == self.SelectedRole:
            return index.row() == self._selected_index
        if role == self.PlaybackStatusRole:
            return self._playback_status
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base_flags = super().flags(index)
        if not index.isValid():
            return base_flags | Qt.ItemFlag.ItemIsDropEnabled
        return (
            base_flags
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def set_queue(self, items: tuple[QueueItem, ...]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def set_active_state(
        self,
        active_index: int | None,
        playback_status: PlaybackStatus,
    ) -> None:
        previous_active = self._active_index
        previous_status = self._playback_status
        self._active_index = active_index
        self._playback_status = playback_status
        self._emit_row_updates(
            previous_active,
            active_index,
            include_active=(
                previous_active != active_index
                or previous_status != playback_status
            ),
        )

    def set_selected_index(self, selected_index: int | None) -> None:
        previous_selected = self._selected_index
        self._selected_index = selected_index
        self._emit_row_updates(
            previous_selected,
            selected_index,
            include_active=False,
        )

    def queue_item_at(self, row: int) -> QueueItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def replace_queue_item(self, row: int, item: QueueItem) -> None:
        if not 0 <= row < len(self._items):
            return
        items = list(self._items)
        items[row] = item
        self._items = tuple(items)
        model_index = self.index(row, 0)
        self.dataChanged.emit(
            model_index,
            model_index,
            [
                self.QueueItemRole,
                self.ActiveRole,
                self.SelectedRole,
                self.PlaybackStatusRole,
            ],
        )

    def active_index(self) -> int | None:
        return self._active_index

    def selected_index(self) -> int | None:
        return self._selected_index

    def _emit_row_updates(
        self,
        previous_row: int | None,
        current_row: int | None,
        *,
        include_active: bool,
    ) -> None:
        rows = {
            row for row in (previous_row, current_row, self._active_index, self._selected_index)
            if row is not None and 0 <= row < len(self._items)
        }
        roles = [self.QueueItemRole, self.SelectedRole]
        if include_active:
            roles.extend([self.ActiveRole, self.PlaybackStatusRole])
        for row in rows:
            model_index = self.index(row, 0)
            self.dataChanged.emit(model_index, model_index, roles)


class QueueWaveformOverlay(QWidget):
    _ANIMATION_FRAMES = (
        (0.42, 0.70, 0.74, 0.48),
        (0.44, 0.72, 0.76, 0.46),
        (0.46, 0.74, 0.78, 0.44),
        (0.48, 0.76, 0.80, 0.42),
        (0.50, 0.78, 0.82, 0.40),
        (0.52, 0.80, 0.84, 0.38),
        (0.54, 0.82, 0.86, 0.36),
        (0.52, 0.84, 0.88, 0.38),
        (0.50, 0.86, 0.90, 0.40),
        (0.48, 0.88, 0.92, 0.42),
        (0.46, 0.90, 0.94, 0.44),
        (0.44, 0.88, 0.92, 0.46),
        (0.42, 0.86, 0.90, 0.48),
        (0.40, 0.84, 0.88, 0.50),
        (0.38, 0.82, 0.86, 0.52),
        (0.36, 0.80, 0.84, 0.54),
        (0.38, 0.78, 0.82, 0.56),
        (0.40, 0.76, 0.80, 0.58),
        (0.42, 0.74, 0.78, 0.60),
        (0.44, 0.72, 0.76, 0.62),
        (0.46, 0.70, 0.74, 0.64),
        (0.48, 0.68, 0.72, 0.62),
        (0.50, 0.66, 0.70, 0.60),
        (0.52, 0.64, 0.68, 0.58),
        (0.54, 0.62, 0.66, 0.56),
        (0.52, 0.60, 0.64, 0.54),
        (0.50, 0.58, 0.62, 0.52),
        (0.48, 0.56, 0.60, 0.50),
        (0.46, 0.58, 0.62, 0.48),
        (0.44, 0.60, 0.64, 0.46),
        (0.42, 0.62, 0.66, 0.44),
        (0.40, 0.64, 0.68, 0.42),
        (0.38, 0.66, 0.70, 0.44),
        (0.36, 0.68, 0.72, 0.46),
        (0.38, 0.70, 0.74, 0.48),
        (0.40, 0.72, 0.76, 0.50),
    )
    _INDICATOR_WIDTH = 18
    _INDICATOR_GAP = 8
    _DURATION_WIDTH = 58
    _ROW_INSET_X = 2
    _ROW_INSET_Y = 1

    def __init__(self, *, parent: "QueueListView", accent_provider) -> None:
        super().__init__(parent.viewport())
        self._view = parent
        self._accent_provider = accent_provider
        self._frame_index = 0
        self._active_row: int | None = None
        self._playback_status = PlaybackStatus.STOPPED
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._advance_animation)
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def sync_state(self, active_row: int | None, playback_status: PlaybackStatus) -> None:
        self._active_row = active_row
        self._playback_status = self._normalize_playback_status(playback_status)
        if active_row is None:
            self._timer.stop()
            self._frame_index = 0
            self.hide()
            return
        if self._playback_status == PlaybackStatus.PLAYING:
            self._timer.start()
        else:
            self._timer.stop()
            self._frame_index = 0
        self._sync_geometry()
        self.show()
        self.update()

    def refresh_position(self) -> None:
        if self._active_row is None:
            self.hide()
            return
        self._sync_geometry()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._accent_provider()))
        bar_width = 3
        gap = 1
        baseline = self.height() - 1
        min_height = 4
        drawable_height = self.height() - 1
        levels = self._ANIMATION_FRAMES[self._frame_index]
        if self._playback_status != PlaybackStatus.PLAYING:
            levels = (0.48, 0.68, 0.54, 0.78)
        for index, factor in enumerate(levels):
            height = max(min_height, int(drawable_height * factor))
            x = index * (bar_width + gap) + 1
            y = baseline - height
            painter.drawRect(x, y, bar_width, height)

    def _advance_animation(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self._ANIMATION_FRAMES)
        self.update()

    def _sync_geometry(self) -> None:
        if self._active_row is None:
            self.hide()
            return
        model = self._view.model()
        if model is None:
            self.hide()
            return
        index = model.index(self._active_row, 0)
        if not index.isValid():
            self.hide()
            return
        row_rect = self._view.visualRect(index)
        if not row_rect.isValid() or row_rect.isEmpty():
            self.hide()
            return
        content_rect = row_rect.adjusted(
            self._ROW_INSET_X + 6,
            self._ROW_INSET_Y + 5,
            -(self._ROW_INSET_X + 6),
            -(self._ROW_INSET_Y + 5),
        )
        duration_rect = QRect(
            content_rect.right() - self._DURATION_WIDTH + 1,
            content_rect.top(),
            self._DURATION_WIDTH,
            content_rect.height(),
        )
        rect = QRect(
            duration_rect.left() - self._INDICATOR_GAP - self._INDICATOR_WIDTH,
            content_rect.center().y() - 7,
            self._INDICATOR_WIDTH,
            14,
        )
        self.setGeometry(rect.adjusted(-1, -1, 1, 1))

    def _normalize_playback_status(self, value: object) -> PlaybackStatus:
        if isinstance(value, PlaybackStatus):
            return value
        if isinstance(value, str):
            try:
                return PlaybackStatus(value)
            except ValueError:
                return PlaybackStatus.STOPPED
        return PlaybackStatus.STOPPED


class QueueRowDelegate(QStyledItemDelegate):
    _ROW_HEIGHT = 48
    _THUMB_SIZE = 38
    _ROW_INSET_X = 2
    _ROW_INSET_Y = 1
    _TEXT_GAP = 8
    _DURATION_WIDTH = 58
    _INDICATOR_WIDTH = 18
    _INDICATOR_GAP = 8

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        thumb_provider,
        thumb_requester,
        format_ms,
        accent_provider,
        accent_text_provider,
        theme_provider,
        corner_style_provider,
    ) -> None:
        super().__init__(parent)
        self._thumb_provider = thumb_provider
        self._thumb_requester = thumb_requester
        self._format_ms = format_ms
        self._accent_provider = accent_provider
        self._accent_text_provider = accent_text_provider
        self._theme_provider = theme_provider
        self._corner_style_provider = corner_style_provider

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        del option, index
        return QSize(0, self._ROW_HEIGHT)

    def sync_animation(
        self,
        active_row: int | None,
        playback_status: PlaybackStatus,
    ) -> None:
        del active_row, playback_status

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        queue_item = index.data(QueueListModel.QueueItemRole)
        if not isinstance(queue_item, QueueItem):
            return
        is_active = bool(index.data(QueueListModel.ActiveRole))
        is_selected = bool(index.data(QueueListModel.SelectedRole))
        playback_status = self._normalize_playback_status(
            index.data(QueueListModel.PlaybackStatusRole)
        )

        palette = _palette_for_theme(self._theme_provider())
        accent = QColor(self._accent_provider())
        accent_text = QColor(self._accent_text_provider())
        row_radius = 8 if self._corner_style_provider() == "rounded" else 0
        active_row_bg = QColor(accent)
        active_row_bg.setAlphaF(0.18 if self._theme_provider() == "light" else 0.22)
        transparent = QColor(0, 0, 0, 0)
        if is_selected:
            background = accent
            title_color = accent_text
            secondary_color = accent_text
            duration_color = accent_text
            indicator_color = accent_text
        elif is_active:
            background = active_row_bg
            title_color = QColor(palette.text_title)
            secondary_color = QColor(palette.text_secondary)
            duration_color = QColor(palette.text_primary)
            indicator_color = accent
        else:
            background = transparent
            title_color = QColor(palette.text_title)
            secondary_color = QColor(palette.text_secondary)
            duration_color = QColor(palette.text_primary)
            indicator_color = accent

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        row_rect = option.rect.adjusted(
            self._ROW_INSET_X,
            self._ROW_INSET_Y,
            -self._ROW_INSET_X,
            -self._ROW_INSET_Y,
        )
        painter.drawRoundedRect(row_rect, row_radius, row_radius)

        content_rect = row_rect.adjusted(6, 5, -6, -5)
        thumb_rect = QRect(
            content_rect.left(),
            content_rect.top(),
            self._THUMB_SIZE,
            self._THUMB_SIZE,
        )
        painter.setBrush(QColor(palette.art_thumb_bg))
        painter.drawRoundedRect(
            thumb_rect,
            6 if self._corner_style_provider() == "rounded" else 0,
            6 if self._corner_style_provider() == "rounded" else 0,
        )
        pixmap = self._thumb_provider(queue_item.track.artwork_ref, self._THUMB_SIZE)
        if pixmap is None and queue_item.track.artwork_ref:
            self._thumb_requester(
                queue_item.track.artwork_ref,
                self._THUMB_SIZE,
                index.row(),
            )
        if pixmap is not None:
            painter.drawPixmap(thumb_rect, pixmap)
        else:
            painter.setPen(QColor(palette.album_art_text))
            note_font = QFont(option.font)
            note_font.setPointSize(max(10, note_font.pointSize()))
            painter.setFont(note_font)
            painter.drawText(thumb_rect, Qt.AlignmentFlag.AlignCenter, "♪")

        duration_rect = QRect(
            content_rect.right() - self._DURATION_WIDTH + 1,
            content_rect.top(),
            self._DURATION_WIDTH,
            content_rect.height(),
        )
        indicator_width = self._INDICATOR_WIDTH + self._INDICATOR_GAP if is_active else 0
        text_left = thumb_rect.right() + 1 + self._TEXT_GAP
        text_right = duration_rect.left() - indicator_width - self._TEXT_GAP
        text_rect = QRect(
            text_left,
            content_rect.top(),
            max(10, text_right - text_left),
            content_rect.height(),
        )
        title_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), 18)
        subtitle_rect = QRect(
            text_rect.left(),
            text_rect.bottom() - 16,
            text_rect.width(),
            16,
        )
        title_font = QFont(option.font)
        title_font.setWeight(QFont.Weight.DemiBold)
        subtitle_font = QFont(option.font)
        subtitle_font.setPointSize(max(10, option.font.pointSize() - 1))
        duration_font = QFont("Menlo", max(10, option.font.pointSize() - 1))
        if duration_font.family() != "Menlo":
            duration_font = QFont(option.font)
            duration_font.setPointSize(max(10, option.font.pointSize() - 1))

        painter.setPen(title_color)
        painter.setFont(title_font)
        title_metrics = painter.fontMetrics()
        version = queue_item.track.version or ""
        version_font = QFont(option.font)
        version_font.setPointSize(max(9, option.font.pointSize() - 2))
        version_text = f" · {version}" if version else ""
        version_width = 0
        if version_text:
            painter.setFont(version_font)
            version_width = painter.fontMetrics().horizontalAdvance(version_text)
            painter.setFont(title_font)
        title_text = painter.fontMetrics().elidedText(
            queue_item.track.title,
            Qt.TextElideMode.ElideRight,
            max(10, title_rect.width() - version_width),
        )
        title_width = min(title_metrics.horizontalAdvance(title_text), title_rect.width())
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_text,
        )
        if version_text and title_width < title_rect.width():
            version_rect = QRect(
                title_rect.left() + title_width,
                title_rect.top(),
                max(0, title_rect.width() - title_width),
                title_rect.height(),
            )
            painter.setPen(secondary_color)
            painter.setFont(version_font)
            painter.drawText(
                version_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                painter.fontMetrics().elidedText(
                    version_text,
                    Qt.TextElideMode.ElideRight,
                    version_rect.width(),
                ),
            )

        subtitle_parts = (", ".join(queue_item.track.artists), queue_item.track.album_title or "")
        subtitle_text = " · ".join(part for part in subtitle_parts if part)
        painter.setPen(secondary_color)
        painter.setFont(subtitle_font)
        subtitle_text = painter.fontMetrics().elidedText(
            subtitle_text,
            Qt.TextElideMode.ElideRight,
            subtitle_rect.width(),
        )
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            subtitle_text,
        )

        painter.setPen(duration_color)
        painter.setFont(duration_font)
        painter.drawText(
            duration_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._format_ms(queue_item.track.duration_ms),
        )

        if is_active:
            indicator_rect = QRect(
                duration_rect.left() - self._INDICATOR_GAP - self._INDICATOR_WIDTH,
                content_rect.center().y() - 7,
                self._INDICATOR_WIDTH,
                14,
            )
            if playback_status != PlaybackStatus.PLAYING:
                self._paint_indicator(painter, indicator_rect, indicator_color)
        painter.restore()

    def _paint_indicator(
        self,
        painter: QPainter,
        rect: QRect,
        color: QColor,
    ) -> None:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        bar_width = 3
        gap = 1
        baseline = rect.bottom()
        min_height = 4
        drawable_height = rect.height() - 1
        for index, factor in enumerate((0.48, 0.68, 0.54, 0.78)):
            height = max(min_height, int(drawable_height * factor))
            x = rect.left() + index * (bar_width + gap) + 1
            y = baseline - height
            painter.drawRect(x, y, bar_width, height)
        painter.restore()

    def _normalize_playback_status(self, value: object) -> PlaybackStatus:
        if isinstance(value, PlaybackStatus):
            return value
        if isinstance(value, str):
            try:
                return PlaybackStatus(value)
            except ValueError:
                return PlaybackStatus.STOPPED
        return PlaybackStatus.STOPPED

    def update_row(self, row: int) -> None:
        self._update_row(row)

    def _update_row(self, row: int) -> None:
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        view = parent
        if not hasattr(view, "model"):
            return
        model = view.model()
        if model is None:
            return
        index = model.index(row, 0)
        if not index.isValid():
            return
        rect = view.visualRect(index)
        if not rect.isValid():
            return
        view.viewport().update(rect)


class QueueListView(QListView):
    reorder_requested = Signal(int, int)

    def __init__(self, parent: QWidget | None = None, *, accent_provider=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._waveform_overlay = QueueWaveformOverlay(
            parent=self,
            accent_provider=accent_provider or (lambda: "#DAA435"),
        )

    def sync_waveform(self, active_row: int | None, playback_status: PlaybackStatus) -> None:
        self._waveform_overlay.sync_state(active_row, playback_status)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._waveform_overlay.refresh_position()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._waveform_overlay.refresh_position()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        event.acceptProposedAction()
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        source_row = self.currentIndex().row()
        if source_row < 0:
            event.ignore()
            return

        target_row = self._target_row_for_event(event)
        row_count = self.model().rowCount() if self.model() is not None else 0
        if row_count <= 0:
            event.ignore()
            return
        target_row = max(0, min(target_row, row_count))
        final_row = target_row - 1 if target_row > source_row else target_row
        if final_row == source_row:
            event.acceptProposedAction()
            return

        self.reorder_requested.emit(source_row, final_row)
        event.acceptProposedAction()

    def _target_row_for_event(self, event: QDropEvent) -> int:
        position = event.position().toPoint()
        index = self.indexAt(position)
        if not index.isValid():
            model = self.model()
            return model.rowCount() if model is not None else 0
        rect = self.visualRect(index)
        if position.y() > rect.center().y():
            return index.row() + 1
        return index.row()

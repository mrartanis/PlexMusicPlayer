from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.presentation.qt.main_window_windowing import MainWindowWindowingMixin


class _ShutdownStub:
    def shutdown(self) -> None:
        return None


class _WindowingHarness(MainWindowWindowingMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._system_media = _ShutdownStub()
        self._controller = _ShutdownStub()
        self._library_controller = _ShutdownStub()
        self._pending_system_move = False
        self._pending_system_move_origin = QPointF()
        self._manual_window_drag_active = False
        self._manual_window_drag_origin = QPointF()
        self._manual_window_drag_window_pos = self.pos()
        self._last_move_target = self.pos()
        self._auth_flow_checked = True
        self._title_bar = QLabel("title", self)
        self._title_drag_handle = QLabel("drag", self)
        self._player_panel_frame = QLabel("panel", self)
        self._track_metadata_zone = QLabel("meta-zone", self)
        self._artwork_label = QLabel("art", self)
        self._track_title_label = QLabel("title-label", self)
        self._track_meta_label = QLabel("artist", self)
        self._track_album_label = QLabel("album", self)
        for widget in (
            self._title_bar,
            self._title_drag_handle,
            self._player_panel_frame,
            self._track_metadata_zone,
            self._artwork_label,
            self._track_title_label,
            self._track_meta_label,
            self._track_album_label,
        ):
            widget.installEventFilter(self)
        self._system_move_calls = 0
        self._force_system_move_result = False

    def _handle_frame_resize_event(self, watched: object, event) -> bool:
        del watched, event
        return False

    def _start_system_move(self) -> bool:
        self._system_move_calls += 1
        return self._force_system_move_result

    def move(self, *args) -> None:
        if len(args) == 1:
            self._last_move_target = args[0]
        elif len(args) == 2:
            from PySide6.QtCore import QPoint

            self._last_move_target = QPoint(args[0], args[1])
        return


def _mouse_event(
    event_type: QEvent.Type,
    *,
    global_position: tuple[float, float],
    button: Qt.MouseButton = Qt.MouseButton.NoButton,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
) -> QMouseEvent:
    local = QPointF(10, 10)
    global_pos = QPointF(*global_position)
    return QMouseEvent(
        event_type,
        local,
        global_pos,
        global_pos,
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_player_header_drag_uses_manual_fallback_when_system_move_fails(qtbot) -> None:
    window = _WindowingHarness()
    qtbot.addWidget(window)
    threshold = QApplication.startDragDistance()

    press_event = _mouse_event(
        QEvent.Type.MouseButtonPress,
        global_position=(10, 10),
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    move_event = _mouse_event(
        QEvent.Type.MouseMove,
        global_position=(10 + threshold + 5, 10),
        buttons=Qt.MouseButton.LeftButton,
    )
    followup_move_event = _mouse_event(
        QEvent.Type.MouseMove,
        global_position=(10 + threshold + 12, 10),
        buttons=Qt.MouseButton.LeftButton,
    )
    release_event = _mouse_event(
        QEvent.Type.MouseButtonRelease,
        global_position=(10 + threshold + 12, 10),
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.NoButton,
    )

    assert window.eventFilter(window._artwork_label, press_event) is True
    assert window._pending_system_move is True

    assert window.eventFilter(window._artwork_label, move_event) is True
    assert window._pending_system_move is False
    assert window._system_move_calls == 1
    assert window._manual_window_drag_active is True

    assert window.eventFilter(window._artwork_label, followup_move_event) is True
    assert window._last_move_target.x() == 7

    assert window.eventFilter(window._artwork_label, release_event) is False
    assert window._manual_window_drag_active is False

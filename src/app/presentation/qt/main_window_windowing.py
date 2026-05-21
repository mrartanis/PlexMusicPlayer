from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent, QShowEvent, QWheelEvent


class MainWindowWindowingMixin:
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._fit_track_text_labels()
        update_responsive_layout = getattr(self, "_update_responsive_layout", None)
        if callable(update_responsive_layout):
            update_responsive_layout()
        if self._auth_flow_checked:
            return
        self._auth_flow_checked = True
        QTimer.singleShot(0, self._maybe_start_auth_flow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_track_text_labels()
        update_responsive_layout = getattr(self, "_update_responsive_layout", None)
        if callable(update_responsive_layout):
            update_responsive_layout()
        relayout_queue_rows = getattr(self, "_relayout_queue_rows", None)
        if callable(relayout_queue_rows):
            QTimer.singleShot(0, relayout_queue_rows)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        refresh_window_button = getattr(self, "_refresh_window_maximize_button", None)
        if callable(refresh_window_button) and event.type() == QEvent.Type.WindowStateChange:
            refresh_window_button()

    def closeEvent(self, event: QCloseEvent) -> None:
        flush_my_wave_history = getattr(self, "_flush_my_wave_history", None)
        if callable(flush_my_wave_history):
            flush_my_wave_history()
        self._system_media.shutdown()
        self._controller.shutdown()
        self._library_controller.shutdown()
        super().closeEvent(event)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if self._handle_frame_resize_event(watched, event):
            return True
        auth_label = getattr(self, "_auth_label", None)
        title_bar = getattr(self, "_title_bar", None)
        title_drag_handle = getattr(self, "_title_drag_handle", None)
        settings_popup = getattr(self, "_settings_popup", None)
        volume_button = getattr(self, "_volume_button", None)
        volume_popup = getattr(self, "_volume_popup", None)
        volume_slider = getattr(self, "_volume_slider", None)
        queue_list = getattr(self, "_queue_list", None)
        player_panel_frame = getattr(self, "_player_panel_frame", None)
        track_metadata_zone = getattr(self, "_track_metadata_zone", None)
        artwork_label = getattr(self, "_artwork_label", None)
        track_title_label = getattr(self, "_track_title_label", None)
        track_meta_label = getattr(self, "_track_meta_label", None)
        track_album_label = getattr(self, "_track_album_label", None)
        queue_viewport = queue_list.viewport() if queue_list is not None else None
        mark_queue_user_interaction = getattr(self, "_mark_queue_user_interaction", None)
        if watched is auth_label:
            if event.type() == QEvent.Type.MouseButtonPress:
                if settings_popup is not None and settings_popup.isVisible():
                    settings_popup.hide()
                else:
                    self._show_settings_popup()
                return True
            return False
        if watched in {title_bar, title_drag_handle}:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_maximized()
                return True
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = self._as_mouse_event(event)
                if (
                    mouse_event is not None
                    and mouse_event.button() == Qt.MouseButton.LeftButton
                    and not self.isMaximized()
                ):
                    self._start_system_move()
                    return True
            return False
        if watched in {
            player_panel_frame,
            track_metadata_zone,
            artwork_label,
            track_title_label,
            track_meta_label,
            track_album_label,
        }:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = self._as_mouse_event(event)
                if (
                    mouse_event is not None
                    and mouse_event.button() == Qt.MouseButton.LeftButton
                    and not self.isMaximized()
                ):
                    self._start_system_move()
                    return True
            return False
        if watched is settings_popup:
            if event.type() == QEvent.Type.Leave and settings_popup is not None:
                settings_popup.hide()
            return False
        if watched is volume_button:
            if event.type() == QEvent.Type.Enter:
                self._show_volume_popup()
            if event.type() == QEvent.Type.Wheel:
                wheel_event = self._as_wheel_event(event)
                if wheel_event is not None:
                    self._adjust_volume_by_steps(self._wheel_steps(wheel_event))
                    return True
            return False
        if watched is volume_popup:
            if event.type() == QEvent.Type.Leave:
                self._hide_volume_popup_if_idle()
            if event.type() == QEvent.Type.Wheel:
                wheel_event = self._as_wheel_event(event)
                if wheel_event is not None:
                    self._adjust_volume_by_steps(self._wheel_steps(wheel_event))
                    return True
            return False
        if watched is volume_slider:
            if event.type() == QEvent.Type.Enter:
                self._show_volume_popup()
            if event.type() == QEvent.Type.Leave:
                self._hide_volume_popup_if_idle()
            if event.type() == QEvent.Type.Wheel:
                wheel_event = self._as_wheel_event(event)
                if wheel_event is not None:
                    self._adjust_volume_by_steps(self._wheel_steps(wheel_event))
                    return True
            return False
        if watched in {queue_list, queue_viewport}:
            if event.type() in {
                QEvent.Type.Wheel,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.KeyPress,
            } and callable(mark_queue_user_interaction):
                mark_queue_user_interaction()
            return False
        return super().eventFilter(watched, event)

    def _as_mouse_event(self, event: QEvent) -> QMouseEvent | None:
        return event if isinstance(event, QMouseEvent) else None

    def _as_wheel_event(self, event: QEvent) -> QWheelEvent | None:
        return event if isinstance(event, QWheelEvent) else None

    def _wheel_steps(self, event: QWheelEvent) -> int:
        delta = event.angleDelta().y()
        if delta == 0:
            return 0
        return int(delta / 120) if abs(delta) >= 120 else (1 if delta > 0 else -1)

    def _is_macos_window_controls(self) -> bool:
        return sys.platform == "darwin"

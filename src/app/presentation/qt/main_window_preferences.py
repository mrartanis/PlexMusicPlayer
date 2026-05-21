from __future__ import annotations

from os import environ

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.application.error_presenter import user_facing_error_message
from app.domain import PlaybackStatus
from app.domain.errors import DomainError
from app.presentation.qt.auth_dialog import AuthDialog
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.main_window_styles import build_main_window_stylesheet


class MainWindowPreferencesMixin:
    def _build_settings_popup(self) -> None:
        popup_shell = QWidget(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        popup_shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup_shell.installEventFilter(self)
        shell_layout = QVBoxLayout(popup_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("settings-popup")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        shell_layout.addWidget(frame)

        self._settings_popup = popup_shell
        self._settings_popup_frame = frame
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._settings_theme_label = QLabel(self._t("settings.section.theme"))
        self._settings_theme_label.setObjectName("settings-section")
        layout.addWidget(self._settings_theme_label)
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(6)
        self._theme_button_labels: dict[str, str] = {}
        for theme_id, title in (
            ("system", self._t("settings.option.theme.system")),
            ("light", self._t("settings.option.theme.light")),
            ("dark", self._t("settings.option.theme.dark")),
        ):
            button = QPushButton(title)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=theme_id: self._set_theme_preference(selected)
            )
            self._theme_buttons[theme_id] = button
            self._theme_button_labels[theme_id] = title
            theme_row.addWidget(button)
        layout.addLayout(theme_row)

        self._settings_corner_label = QLabel(self._t("settings.section.corners"))
        self._settings_corner_label.setObjectName("settings-section")
        layout.addWidget(self._settings_corner_label)
        corner_row = QHBoxLayout()
        corner_row.setContentsMargins(0, 0, 0, 0)
        corner_row.setSpacing(6)
        self._corner_style_buttons: dict[str, QPushButton] = {}
        self._corner_button_labels: dict[str, str] = {}
        for corner_style, title in (
            ("straight", self._t("settings.option.corner.straight")),
            ("rounded", self._t("settings.option.corner.rounded")),
        ):
            button = QPushButton(title)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=corner_style: self._set_corner_style_preference(
                    selected
                )
            )
            self._corner_style_buttons[corner_style] = button
            self._corner_button_labels[corner_style] = title
            corner_row.addWidget(button)
        layout.addLayout(corner_row)

        self._settings_language_label = QLabel(self._t("settings.section.language"))
        self._settings_language_label.setObjectName("settings-section")
        layout.addWidget(self._settings_language_label)
        language_row = QHBoxLayout()
        language_row.setContentsMargins(0, 0, 0, 0)
        language_row.setSpacing(6)
        self._language_buttons: dict[str, QPushButton] = {}
        self._language_button_labels: dict[str, str] = {}
        for language, title in (
            ("system", self._t("settings.option.language.system")),
            ("en", self._t("settings.option.language.en")),
            ("ru", self._t("settings.option.language.ru")),
        ):
            button = QPushButton(title)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=language: self._set_language_preference(selected)
            )
            self._language_buttons[language] = button
            self._language_button_labels[language] = title
            language_row.addWidget(button)
        layout.addLayout(language_row)

        self._settings_waveform_progress_label = QLabel(
            self._t("settings.section.waveform_progress")
        )
        self._settings_waveform_progress_label.setObjectName("settings-section")
        layout.addWidget(self._settings_waveform_progress_label)
        waveform_row = QHBoxLayout()
        waveform_row.setContentsMargins(0, 0, 0, 0)
        waveform_row.setSpacing(6)
        self._waveform_progress_buttons: dict[bool, QPushButton] = {}
        for enabled, title in (
            (False, self._t("settings.option.waveform_progress.disabled")),
            (True, self._t("settings.option.waveform_progress.enabled")),
        ):
            button = QPushButton(title)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda checked=False, selected=enabled: self._set_waveform_progress_enabled(
                    selected
                )
            )
            self._waveform_progress_buttons[enabled] = button
            waveform_row.addWidget(button)
        layout.addLayout(waveform_row)

        self._logout_button = QPushButton(self._t("action.logout"))
        self._logout_button.setObjectName("settings-action")
        self._logout_button.clicked.connect(self._logout)
        layout.addWidget(self._logout_button)
        popup_shell.hide()

    def _build_volume_popup(self) -> None:
        self._volume_popup = QFrame(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._volume_popup.setObjectName("volume-popup")
        self._volume_popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._volume_popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self._volume_popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._volume_slider, 0, Qt.AlignmentFlag.AlignCenter)
        self._volume_popup.installEventFilter(self)
        self._volume_slider.installEventFilter(self)
        self._volume_popup.hide()

    def _show_settings_popup(self) -> None:
        if self._settings_popup is None:
            return
        self._settings_popup.adjustSize()
        anchor_widget = (
            self._settings_button
            if hasattr(self, "_settings_button")
            else self._auth_label
        )
        anchor = anchor_widget.mapToGlobal(QPoint(0, anchor_widget.height() + 6))
        screen = self.screen().availableGeometry()
        x = min(anchor.x(), screen.right() - self._settings_popup.width() - 8)
        x = max(screen.left() + 8, x)
        y = min(anchor.y(), screen.bottom() - self._settings_popup.height() - 8)
        self._settings_popup.move(QPoint(x, y))
        self._settings_popup.show()
        self._settings_popup.raise_()

    def _show_volume_popup(self) -> None:
        if self._volume_popup is None:
            return
        self._volume_popup.adjustSize()
        position = self._volume_button.mapToGlobal(
            QPoint(
                -self._volume_popup.width() // 2 + self._volume_button.width() // 2,
                -self._volume_popup.height() - 6,
            ),
        )
        self._volume_popup.move(position)
        self._volume_popup.show()
        self._volume_popup.raise_()

    def _hide_volume_popup_if_idle(self) -> None:
        if self._volume_popup is None:
            return
        if getattr(self, "_volume_slider_drag_active", False):
            return
        if self._volume_popup.geometry().contains(QCursor.pos()):
            return
        button_pos = self._volume_button.mapFromGlobal(QCursor.pos())
        if self._volume_button.geometry().contains(button_pos):
            return
        self._volume_popup.hide()

    def _set_theme_preference(self, theme: str) -> None:
        self._container.services.settings_service.save_theme_preference(theme)
        self._render_theme_preference(theme)
        self._apply_theme()
        self._status_label.setText(
            self._t("settings.theme", value=self._t(f"settings.option.theme.{theme}"))
        )

    def _set_corner_style_preference(self, corner_style: str) -> None:
        self._container.services.settings_service.save_corner_style_preference(corner_style)
        self._render_corner_style_preference(corner_style)
        self._apply_theme()
        self._status_label.setText(
            self._t(
                "settings.corner_style",
                value=self._t(f"settings.option.corner.{corner_style}"),
            )
        )

    def _set_language_preference(self, language: str) -> None:
        self._container.services.settings_service.save_language_preference(language)
        self._render_language_preference(language)
        self._refresh_localized_texts()
        self._status_label.setText(
            self._t(
                "settings.language_preference",
                value=self._t(f"settings.option.language.{language}"),
            )
        )

    def _set_waveform_progress_enabled(self, enabled: bool) -> None:
        self._container.services.settings_service.save_waveform_progress_enabled(enabled)
        self._render_waveform_progress_enabled(enabled)
        if hasattr(self, "_seek_slider"):
            self._seek_slider.set_waveform_enabled(enabled)
        self._controller.set_waveform_progress_enabled(enabled)
        option_key = (
            "settings.option.waveform_progress.enabled"
            if enabled
            else "settings.option.waveform_progress.disabled"
        )
        self._status_label.setText(
            self._t("settings.waveform_progress", value=self._t(option_key))
        )

    def _render_theme_preference(self, theme: str) -> None:
        for candidate, button in self._theme_buttons.items():
            button.setChecked(candidate == theme)

    def _render_corner_style_preference(self, corner_style: str) -> None:
        for candidate, button in self._corner_style_buttons.items():
            button.setChecked(candidate == corner_style)

    def _render_language_preference(self, language: str) -> None:
        for candidate, button in self._language_buttons.items():
            button.setChecked(candidate == language)

    def _render_waveform_progress_enabled(self, enabled: bool) -> None:
        for candidate, button in getattr(self, "_waveform_progress_buttons", {}).items():
            button.setChecked(candidate == enabled)

    def _logout(self) -> None:
        self._container.services.auth_service.clear_session()
        self._container.services.music_service.clear_auth_session()
        if self._settings_popup is not None:
            self._settings_popup.hide()
        self._render_auth_state()
        self._status_label.setText(self._t("status.logged_out"))
        self._maybe_start_auth_flow()

    def _apply_saved_settings_to_ui(self) -> None:
        self._render_theme_preference(self._stored_theme_preference())
        self._render_corner_style_preference(self._stored_corner_style_preference())
        self._render_language_preference(self._stored_language_preference())
        self._render_waveform_progress_enabled(
            self._container.services.settings_service.load_waveform_progress_enabled()
        )
        if hasattr(self, "_seek_slider"):
            self._seek_slider.set_waveform_enabled(
                self._container.services.settings_service.load_waveform_progress_enabled()
            )
        self._normalize_settings_option_button_widths()
        self._refresh_localized_texts()
        self._apply_theme()

    def _normalize_settings_option_button_widths(self) -> None:
        button_groups = (
            getattr(self, "_theme_buttons", {}).values(),
            getattr(self, "_corner_style_buttons", {}).values(),
            getattr(self, "_language_buttons", {}).values(),
            getattr(self, "_waveform_progress_buttons", {}).values(),
        )
        buttons = [button for group in button_groups for button in group]
        if not buttons:
            return
        common_width = max(button.sizeHint().width() for button in buttons)
        for button in buttons:
            button.setMinimumWidth(common_width)

    def _maybe_start_auth_flow(self) -> None:
        if self._container.services.auth_service.current_session() is not None:
            return
        if self._is_headless_test_run():
            return

        self._auth_dialog = AuthDialog(
            parent=None,
            window_title=self._t("app.auth_dialog.title"),
            status_text=self._t("app.auth_dialog.status"),
            music_service=self._container.services.music_service,
            logger=self._container.logger,
        )
        self._auth_dialog.session_captured.connect(self._complete_auth_flow)
        self._auth_dialog.finished.connect(self._clear_auth_dialog)
        self._auth_dialog.show()
        self._auth_dialog.raise_()
        self._auth_dialog.activateWindow()

    def _complete_auth_flow(self, session) -> None:
        try:
            self._container.services.music_service.apply_auth_session(session)
            session = self._container.services.auth_service.save_session(session)
        except DomainError as exc:
            self._container.logger.warning("Auth flow failed: %s", exc)
            self._status_label.setText(
                self._t("status.auth_error", message=user_facing_error_message(exc))
            )
            return

        username = self._session_identity_text(session)
        self._status_label.setText(self._t("status.authenticated_as", username=username))
        self._render_auth_state()

    def _clear_auth_dialog(self) -> None:
        if (
            self._container.services.auth_service.current_session() is None
            and not self._is_headless_test_run()
        ):
            QApplication.quit()
        self._auth_dialog = None

    def _is_headless_test_run(self) -> bool:
        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return True
        return environ.get("QT_QPA_PLATFORM") == "offscreen"

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            build_main_window_stylesheet(
                accent=self._accent_color,
                accent_text=self._accent_text_color(),
                theme=self._resolved_theme_mode(),
                corner_style=self._stored_corner_style_preference(),
            )
        )
        self._my_wave_top_button.set_visuals(
            accent=self._accent_color,
            accent_text=self._accent_text_color(),
            trailing=self._my_wave_trailing_color(),
            rounded=self._stored_corner_style_preference() == "rounded",
            theme_mode=self._resolved_theme_mode(),
        )
        if hasattr(self, "_seek_slider"):
            self._seek_slider.set_visuals(
                accent=self._accent_color,
                theme_mode=self._resolved_theme_mode(),
                rounded=self._stored_corner_style_preference() == "rounded",
            )
        self._refresh_theme_icons()
        if self._browser_dialog is not None:
            self._browser_dialog.setStyleSheet(self.styleSheet())
        if getattr(self, "_sidebar_popup", None) is not None:
            self._sidebar_popup.setStyleSheet(self.styleSheet())
        if self._settings_popup is not None:
            self._settings_popup.setStyleSheet(self.styleSheet())
        if self._volume_popup is not None:
            self._volume_popup.setStyleSheet(self.styleSheet())

    def _stored_theme_preference(self) -> str:
        return self._container.services.settings_service.load_theme_preference()

    def _resolved_theme_mode(self) -> str:
        preference = self._stored_theme_preference()
        if preference in {"light", "dark"}:
            return preference
        app = QApplication.instance()
        if app is None:
            return "dark"
        return (
            "light"
            if app.styleHints().colorScheme() == Qt.ColorScheme.Light
            else "dark"
        )

    def _stored_corner_style_preference(self) -> str:
        return self._container.services.settings_service.load_corner_style_preference()

    def _stored_language_preference(self) -> str:
        return self._container.services.settings_service.load_language_preference()

    def _theme_icon_color(self) -> str:
        return "#1f2736" if self._resolved_theme_mode() == "light" else "#ffffff"

    def _refresh_theme_icons(self) -> None:
        icon_color = self._theme_icon_color()
        if hasattr(self, "_window_minimize_button"):
            self._window_minimize_button.setIcon(
                create_icon("window-minimize.svg", color=icon_color)
            )
        if hasattr(self, "_window_maximize_button"):
            self._refresh_window_maximize_button()
        if hasattr(self, "_window_close_button"):
            self._window_close_button.setIcon(create_icon("window-close.svg", color=icon_color))
        if hasattr(self, "_volume_button"):
            self._volume_button.setIcon(create_icon("volume.svg", color=icon_color))
        if hasattr(self, "_settings_button"):
            self._settings_button.setIcon(create_icon("settings.svg", color=icon_color))
        if hasattr(self, "_previous_button"):
            self._previous_button.setIcon(create_icon("previous.svg", color=icon_color))
        if hasattr(self, "_next_button"):
            self._next_button.setIcon(create_icon("next.svg", color=icon_color))
        if hasattr(self, "_play_all_button"):
            self._play_all_button.setIcon(create_icon("play.svg", color=icon_color))
        if hasattr(self, "_append_all_button"):
            self._append_all_button.setIcon(create_icon("add_to_playlist.svg", color=icon_color))
        if hasattr(self, "_queue_shuffle_button"):
            self._queue_shuffle_button.setIcon(
                create_icon("shuffle_playlist.svg", color=icon_color)
            )
        if hasattr(self, "_clear_queue_button"):
            self._clear_queue_button.setIcon(create_icon("clear_playlist.svg", color=icon_color))
        if hasattr(self, "_play_pause_button"):
            status_value = self._play_pause_button.property("playback_status") or "stopped"
            self._render_play_pause_button(PlaybackStatus(status_value))
        if hasattr(self, "_like_track_button"):
            self._render_current_track_like_button(
                self._current_track.is_liked if self._current_track else False
            )

    def _refresh_localized_texts(self) -> None:
        self.setWindowTitle(self._t("app.title"))
        if hasattr(self, "_settings_theme_label"):
            self._settings_theme_label.setText(self._t("settings.section.theme"))
        if hasattr(self, "_settings_corner_label"):
            self._settings_corner_label.setText(self._t("settings.section.corners"))
        if hasattr(self, "_settings_language_label"):
            self._settings_language_label.setText(self._t("settings.section.language"))
        if hasattr(self, "_settings_waveform_progress_label"):
            self._settings_waveform_progress_label.setText(
                self._t("settings.section.waveform_progress")
            )
        if hasattr(self, "_logout_button"):
            self._logout_button.setText(self._t("action.logout"))
        for theme_id, button in getattr(self, "_theme_buttons", {}).items():
            button.setText(self._t(f"settings.option.theme.{theme_id}"))
        for corner_style, button in getattr(self, "_corner_style_buttons", {}).items():
            button.setText(self._t(f"settings.option.corner.{corner_style}"))
        for language, button in getattr(self, "_language_buttons", {}).items():
            button.setText(self._t(f"settings.option.language.{language}"))
        for enabled, button in getattr(self, "_waveform_progress_buttons", {}).items():
            key = (
                "settings.option.waveform_progress.enabled"
                if enabled
                else "settings.option.waveform_progress.disabled"
            )
            button.setText(self._t(key))
        self._normalize_settings_option_button_widths()
        if getattr(self, "_auth_dialog", None) is not None:
            self._auth_dialog.apply_texts(
                window_title=self._t("app.auth_dialog.title"),
                status_text=self._t("app.auth_dialog.status"),
            )
        refresh_main = getattr(self, "_refresh_main_window_texts", None)
        if callable(refresh_main):
            refresh_main()
        auto_open_enabled = self._browser_auto_open_enabled
        self._browser_auto_open_enabled = False
        try:
            self._library_controller.refresh_localized_content()
        finally:
            self._browser_auto_open_enabled = auto_open_enabled

    def _refresh_window_maximize_button(self) -> None:
        if not hasattr(self, "_window_maximize_button"):
            return
        icon_color = self._theme_icon_color()
        if self._is_macos_window_controls() and self._title_bar is not None:
            self._title_bar.setVisible(not self.isFullScreen())
        if not self._is_macos_window_controls():
            self._window_maximize_button.setIcon(
                create_icon("window-maximize.svg", color=icon_color)
            )
            self._window_maximize_button.setToolTip(
                self._t("action.restore") if self.isMaximized() else self._t("action.maximize")
            )
            return
        if self.isFullScreen():
            self._window_maximize_button.setIcon(
                create_icon("window-maximize.svg", color=icon_color)
            )
            self._window_maximize_button.setToolTip(self._t("action.exit_full_screen"))
            return
        self._window_maximize_button.setIcon(
            create_icon("window-maximize.svg", color=icon_color)
        )
        self._window_maximize_button.setToolTip(self._t("action.full_screen"))

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.my_wave_button import MyWaveButton
from app.presentation.qt.waveform_seek_bar import WaveformSeekBar


class MainWindowLayoutMixin:
    def _build_player_panel(self) -> QFrame:
        frame = self._panel_frame("Main Player")
        frame.installEventFilter(self)
        self._player_panel_frame = frame
        layout = frame.layout()
        assert layout is not None

        self._seek_slider = WaveformSeekBar()
        self._seek_slider.setMaximum(300_000)
        self._seek_slider.setSingleStep(1_000)
        self._seek_slider.setPageStep(10_000)
        self._seek_slider.setObjectName("seek-slider")
        self._seek_slider.setMinimumWidth(280)
        self._seek_slider.setMaximumWidth(16_777_215)
        self._seek_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._seek_label = self._panel_label("0:00 / 0:00")
        self._seek_label.setObjectName("seek-label")
        self._seek_label.setFixedHeight(28)
        self._seek_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._seek_label.setMinimumWidth(92)
        self._seek_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._volume_slider = QSlider(Qt.Orientation.Vertical)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setObjectName("volume-slider")
        self._volume_slider.setFixedSize(26, 118)
        self._volume_label = self._panel_label("100%")
        self._track_title_label = self._panel_label(self._t("label.starter_signal"))
        self._track_title_label.setObjectName("track-title")
        self._track_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_title_label.setWordWrap(True)
        self._track_title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_title_label.setMaximumHeight(108)
        self._track_version_label = self._panel_label("")
        self._track_version_label.setObjectName("track-version")
        self._track_version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_version_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_version_label.setMaximumHeight(28)
        self._track_version_label.setWordWrap(True)
        self._track_version_label.setVisible(False)
        self._track_meta_label = self._panel_label(self._t("label.artist_metadata"))
        self._track_meta_label.setObjectName("track-artist")
        self._track_meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_meta_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_meta_label.setMaximumHeight(72)
        self._track_meta_label.setWordWrap(True)
        self._track_album_label = self._panel_label(self._t("label.album"))
        self._track_album_label.setObjectName("track-album")
        self._track_album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_album_label.setWordWrap(True)
        self._track_album_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_album_label.setMaximumHeight(72)
        self._audio_info_label = self._panel_label("")
        self._audio_info_label.setObjectName("queue-audio-info")
        self._audio_info_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._track_technical_label = self._panel_label("")
        self._track_technical_label.setObjectName("track-tech")
        self._track_technical_label.setVisible(False)
        self._playback_state_label = self._panel_label(self._t("label.playback_state.stopped"))
        self._playback_state_label.setObjectName("playback-state")
        self._status_label = self._panel_label("")
        self._status_label.setObjectName("inline-status")
        self._status_label.setVisible(False)
        self._queue_status_label = self._panel_label(self._t("label.queue_idle"), align_right=True)
        self._queue_status_label.setObjectName("queue-summary")
        self._artwork_label = QLabel(self._t("label.no_cover"))
        self._artwork_label.setObjectName("album-art")
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label.setFixedSize(self._COMPACT_ARTWORK_SIZE, self._COMPACT_ARTWORK_SIZE)
        self._artwork_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._artwork_label.installEventFilter(self)
        self._sidebar_toggle_button = QPushButton("≡")
        self._sidebar_toggle_button.setObjectName("sidebar-toggle")
        self._sidebar_toggle_button.setToolTip(self._t("action.toggle_navigation"))
        self._sidebar_toggle_button.setFixedSize(30, 28)
        self._my_wave_top_button = MyWaveButton(self._t("nav.my_wave"))
        self._my_wave_top_button.setObjectName("my-wave-button")
        self._my_wave_top_button.setFixedHeight(28)
        self._auth_label = self._panel_label(self._t("label.login_required"), align_right=True)
        self._auth_label.setObjectName("auth-label")
        self._auth_label.setFixedHeight(28)
        self._auth_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._auth_label.installEventFilter(self)
        self._settings_button = QPushButton()
        self._settings_button.setObjectName("settings-toggle-button")
        self._settings_button.setToolTip(self._t("action.settings"))
        self._settings_button.setAccessibleName(self._t("action.settings"))
        self._settings_button.setFixedSize(28, 28)
        self._volume_button = QPushButton()
        self._volume_button.setObjectName("volume-button")
        self._volume_button.setIcon(create_icon("volume.svg"))
        self._volume_button.setToolTip(self._t("action.volume"))
        self._volume_button.setFixedSize(34, 32)
        self._volume_button.installEventFilter(self)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(self._sidebar_toggle_button)
        top_row.addWidget(self._my_wave_top_button)
        top_row.addStretch(1)
        top_row.addWidget(self._auth_label, 0, Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._settings_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(top_row)
        layout.addSpacing(6)

        self._hero_widget = QWidget()
        self._hero_widget.setFixedHeight(self._artwork_label.height())
        info_widget = QWidget()
        info_widget.setMinimumWidth(0)
        info_widget.setFixedHeight(self._artwork_label.height())
        info_widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self._hero_info_widget = info_widget
        self._hero_info_layout = QVBoxLayout(info_widget)
        self._hero_info_layout.setSpacing(5)
        self._hero_info_layout.setContentsMargins(0, 0, 0, 0)
        text_block = QWidget()
        text_block.setObjectName("track-metadata-zone")
        text_block.setMinimumWidth(0)
        text_block.setFixedHeight(176)
        text_block.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        text_block.installEventFilter(self)
        self._track_metadata_zone = text_block
        self._text_block_layout = QVBoxLayout(text_block)
        self._text_block_layout.setContentsMargins(0, 0, 0, 0)
        self._text_block_layout.setSpacing(5)
        self._text_block_layout.addStretch(1)
        self._track_title_label.installEventFilter(self)
        self._text_block_layout.addWidget(self._track_title_label)
        self._track_version_label.installEventFilter(self)
        self._text_block_layout.addWidget(self._track_version_label)
        self._track_meta_label.installEventFilter(self)
        self._text_block_layout.addWidget(self._track_meta_label)
        self._track_album_label.installEventFilter(self)
        self._text_block_layout.addWidget(self._track_album_label)
        self._text_block_layout.addStretch(1)
        self._transport_widget = QWidget()
        self._transport_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self._transport_widget.setLayout(self._build_transport_bar())
        self._hero_info_layout.addStretch(1)
        self._hero_info_layout.addWidget(text_block)
        self._hero_info_layout.addStretch(1)
        self._hero_info_layout.addWidget(self._transport_widget)
        self._hero_info_layout.addSpacing(10)

        self._progress_widget = QWidget()
        self._progress_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        progress_row = QHBoxLayout(self._progress_widget)
        progress_row.setSpacing(8)
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.addWidget(self._seek_slider, 1)
        progress_row.addWidget(self._seek_label)
        progress_row.addWidget(self._volume_button)
        progress_row.addWidget(self._like_track_button)

        self._player_right_widget = QWidget()
        self._player_right_widget.setMinimumWidth(self._PLAYER_MIN_WIDTH)
        self._player_right_widget.setMaximumWidth(self._PLAYER_MAX_WIDTH)
        self._player_right_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._player_right_layout = QVBoxLayout(self._player_right_widget)
        self._player_right_layout.setContentsMargins(0, 0, 0, 0)
        self._player_right_layout.setSpacing(8)
        self._player_right_layout.addWidget(self._hero_widget)
        self._player_right_layout.addWidget(self._progress_widget)
        self._player_right_layout.addStretch(1)

        self._player_body_widget = QWidget()
        self._player_body_layout = QHBoxLayout(self._player_body_widget)
        self._player_body_layout.setContentsMargins(0, 0, 0, 0)
        self._player_body_layout.setSpacing(14)
        self._player_left_spacer = QWidget()
        self._player_left_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._player_right_spacer = QWidget()
        self._player_right_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._player_body_layout.addWidget(self._player_left_spacer, 1)
        self._player_body_layout.addWidget(self._player_right_widget, 0)
        self._player_body_layout.addWidget(self._player_right_spacer, 1)
        self._player_left_spacer.hide()
        self._player_right_spacer.hide()

        layout.addWidget(self._player_body_widget, 1)
        self._build_settings_popup()
        self._build_volume_popup()
        self._track_label_base_sizes = {
            self._track_title_label: 28,
            self._track_version_label: 12,
            self._track_meta_label: 16,
            self._track_album_label: 13,
        }
        self._configure_player_right_layout(wide=False)
        return frame

    def _build_nav_panel(self, *, primary: bool = True) -> QFrame:
        frame = self._panel_frame("Navigation")
        frame.setObjectName("sidebar")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        frame.setMinimumWidth(self._SIDEBAR_ZONE_MIN_WIDTH)
        frame.setMaximumWidth(self._SIDEBAR_ZONE_MAX_WIDTH)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = frame.layout()
        assert layout is not None
        search_button = QPushButton(self._t("action.search"))
        liked_button = QPushButton(self._t("nav.my_tracks"))
        liked_albums_button = QPushButton(self._t("nav.my_albums"))
        liked_artists_button = QPushButton(self._t("nav.my_artists"))
        playlists_button = QPushButton(self._t("nav.playlists"))
        if primary:
            self._search_nav_button = search_button
            self._liked_nav_button = liked_button
            self._liked_albums_nav_button = liked_albums_button
            self._liked_artists_nav_button = liked_artists_button
            self._playlists_nav_button = playlists_button
        else:
            self._popup_search_nav_button = search_button
            self._popup_liked_nav_button = liked_button
            self._popup_liked_albums_nav_button = liked_albums_button
            self._popup_liked_artists_nav_button = liked_artists_button
            self._popup_playlists_nav_button = playlists_button
        library_label = QLabel(self._t("label.library"))
        library_label.setObjectName("nav-section")
        if primary:
            self._nav_library_label = library_label
        else:
            self._popup_nav_library_label = library_label
        layout.addWidget(library_label)
        for button in (
            liked_button,
            liked_albums_button,
            liked_artists_button,
            playlists_button,
        ):
            layout.addWidget(button)
        layout.addSpacing(8)
        discovery_label = QLabel(self._t("label.discovery"))
        discovery_label.setObjectName("nav-section")
        if primary:
            self._nav_discovery_label = discovery_label
        else:
            self._popup_nav_discovery_label = discovery_label
        layout.addWidget(discovery_label)
        layout.addWidget(search_button)
        layout.addStretch(1)
        return frame

    def _build_sidebar_popup(self) -> None:
        popup_shell = QWidget(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        popup_shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup_layout = QVBoxLayout(popup_shell)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)
        popup_panel = self._build_nav_panel(primary=False)
        popup_layout.addWidget(popup_panel)
        popup_shell.adjustSize()
        popup_shell.hide()
        popup_shell.move(self.mapToGlobal(QPoint(14, 54)))
        popup_shell.raise_()
        popup_shell.setStyleSheet(self.styleSheet())
        self._sidebar_popup = popup_shell
        self._sidebar_popup_panel = popup_panel

    def _toggle_sidebar(self) -> None:
        if self._sidebar_popup is None:
            return
        if self._sidebar_docked:
            return
        if self._sidebar_popup.isVisible():
            self._sidebar_popup.hide()
            return
        if self._sidebar_panel is not None:
            self._sidebar_panel.show()
        position = self._sidebar_toggle_button.mapTo(
            self,
            QPoint(0, self._sidebar_toggle_button.height() + 6),
        )
        self._sidebar_popup.move(self.mapToGlobal(position))
        self._sidebar_popup.adjustSize()
        self._sidebar_popup.show()
        self._sidebar_popup.raise_()

    def _update_responsive_layout(self) -> None:
        self._set_player_queue_wide(self.width() >= self._PLAYER_QUEUE_WIDE_BREAKPOINT)
        self._set_sidebar_docked(self.width() >= self._SIDEBAR_DOCK_BREAKPOINT)
        self._set_browser_docked(self.width() >= self._BROWSER_DOCK_BREAKPOINT)
        self._update_wide_zone_balance()

    def _set_sidebar_docked(self, docked: bool) -> None:
        if self._sidebar_docked == docked or self._sidebar_panel is None:
            return
        self._sidebar_docked = docked
        if docked:
            if self._sidebar_popup is not None:
                self._sidebar_popup.hide()
            layout = self._sidebar_panel.layout()
            if layout is not None:
                layout.setContentsMargins(8, 0, 8, 2)
            self._move_widget_to_layout(self._sidebar_panel, self._sidebar_host_layout)
            if self._sidebar_host_layout is not None:
                self._sidebar_host_layout.setAlignment(
                    self._sidebar_panel,
                    Qt.AlignmentFlag.AlignTop,
                )
            if self._sidebar_host is not None:
                self._sidebar_host.show()
            if self._left_zone is not None:
                self._left_zone.show()
            self._sidebar_panel.show()
            self._sidebar_toggle_button.hide()
            self._update_wide_zone_balance()
            return
        if self._sidebar_host_layout is not None:
            self._sidebar_host_layout.removeWidget(self._sidebar_panel)
        if self._sidebar_host is not None:
            self._sidebar_host.hide()
        if self._left_zone is not None and not self._player_queue_wide:
            self._left_zone.hide()
        layout = self._sidebar_panel.layout()
        if layout is not None:
            layout.setContentsMargins(8, 10, 8, 10)
        self._sidebar_panel.hide()
        self._sidebar_toggle_button.show()
        self._update_wide_zone_balance()

    def _set_browser_docked(self, docked: bool) -> None:
        if self._browser_docked == docked or self._browser_panel is None:
            return
        self._browser_docked = docked
        if docked:
            if self._browser_dialog is not None:
                self._browser_dialog.hide()
            self._move_widget_to_layout(self._browser_panel, self._browser_host_layout)
            if self._browser_host is not None:
                self._browser_host.show()
            self._browser_panel.show()
            self._browser_close_button.hide()
            self._update_wide_zone_balance()
            return
        if self._browser_host_layout is not None:
            self._browser_host_layout.removeWidget(self._browser_panel)
        if self._browser_host is not None:
            self._browser_host.hide()
        if self._browser_dialog is not None and self._browser_dialog.layout() is not None:
            self._move_widget_to_layout(self._browser_panel, self._browser_dialog.layout())
        self._browser_close_button.show()
        self._update_wide_zone_balance()

    def _move_widget_to_layout(self, widget: QWidget, layout) -> None:
        parent = widget.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().removeWidget(widget)
        widget.setParent(None)
        layout.addWidget(widget)
        widget.show()

    def _set_player_queue_wide(self, wide: bool) -> None:
        queue_panel = getattr(self, "_queue_panel_widget", None)
        if queue_panel is None or self._player_queue_wide == wide:
            return
        self._player_queue_wide = wide
        if wide:
            self._move_widget_to_layout(queue_panel, self._queue_host_layout)
            if self._queue_host is not None:
                self._queue_host.show()
            if self._left_zone is not None and self._sidebar_docked:
                self._left_zone.show()
            self._player_left_spacer.show()
            self._player_right_spacer.show()
            self._player_body_layout.setStretch(0, 1)
            self._player_body_layout.setStretch(1, 0)
            self._player_body_layout.setStretch(2, 1)
            self._configure_player_right_layout(wide=True)
            self._update_wide_zone_balance()
            return
        self._move_widget_to_layout(queue_panel, self._main_column_layout)
        if self._queue_host is not None:
            self._queue_host.hide()
        self._player_left_spacer.hide()
        self._player_right_spacer.hide()
        self._player_body_layout.setStretch(0, 0)
        self._player_body_layout.setStretch(1, 0)
        self._player_body_layout.setStretch(2, 0)
        self._configure_player_right_layout(wide=False)
        self._update_wide_zone_balance()

    def _update_wide_zone_balance(self) -> None:
        if (
            self._left_zone is None
            or self._browser_host is None
            or self._main_column_widget is None
        ):
            return
        left_visible = self._sidebar_docked or self._player_queue_wide
        right_visible = self._browser_docked
        if not left_visible:
            self._left_zone.hide()
        else:
            self._left_zone.show()
        if not right_visible:
            self._browser_host.hide()
        self._left_zone.setMinimumWidth(0)
        self._left_zone.setMaximumWidth(
            self._WIDE_SIDE_ZONE_MAX_WIDTH if left_visible else 16_777_215
        )
        self._browser_host.setMinimumWidth(self._BROWSER_ZONE_MIN_WIDTH)
        self._browser_host.setMaximumWidth(self._BROWSER_ZONE_MAX_WIDTH)
        if self._queue_host is not None:
            queue_host_max_width = self._WIDE_SIDE_ZONE_MAX_WIDTH
            if self._sidebar_docked and self._sidebar_host is not None:
                queue_host_max_width -= (
                    self._SIDEBAR_ZONE_MAX_WIDTH + self._left_zone_layout.spacing()
                )
            self._queue_host.setMaximumWidth(max(0, queue_host_max_width))
        if not self._player_queue_wide or not left_visible or not right_visible:
            self._player_left_spacer.setMinimumWidth(0)
            self._player_left_spacer.setMaximumWidth(16_777_215)
            self._player_right_spacer.setMinimumWidth(0)
            self._player_right_spacer.setMaximumWidth(16_777_215)
            return
        left_width = self._left_zone.width()
        right_width = self._browser_host.width()
        if left_width <= 0:
            left_width = self._left_zone.sizeHint().width()
        if right_width <= 0:
            right_width = self._browser_host.sizeHint().width()
        delta = right_width - left_width
        left_pad = max(0, delta // 2)
        right_pad = max(0, -delta // 2)
        self._player_left_spacer.setMinimumWidth(left_pad)
        self._player_left_spacer.setMaximumWidth(16_777_215)
        self._player_right_spacer.setMinimumWidth(right_pad)
        self._player_right_spacer.setMaximumWidth(16_777_215)

    def _configure_player_right_layout(self, *, wide: bool) -> None:
        self._apply_player_visual_mode(wide=wide)
        self._rebuild_hero_layout(wide=wide)
        self._player_right_layout.removeWidget(self._hero_widget)
        self._player_right_layout.removeWidget(self._transport_widget)
        self._player_right_layout.removeWidget(self._progress_widget)
        self._clear_layout_widgets(self._player_right_layout)
        if wide:
            self._player_right_layout.addStretch(1)
            self._player_right_layout.addWidget(self._hero_widget, 0, Qt.AlignmentFlag.AlignHCenter)
            self._player_right_layout.addStretch(1)
            self._player_right_layout.addWidget(
                self._transport_widget,
                0,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            )
            self._player_right_layout.addWidget(self._progress_widget, 0)
            return
        self._player_right_layout.addWidget(self._hero_widget)
        self._player_right_layout.addWidget(self._progress_widget)
        if hasattr(self, "_player_panel_frame") and self._player_panel_frame is not None:
            self._player_panel_frame.setFixedHeight(self._PLAYER_PANEL_COMPACT_HEIGHT)

    def _apply_player_visual_mode(self, *, wide: bool) -> None:
        artwork_size = self._WIDE_ARTWORK_SIZE if wide else self._COMPACT_ARTWORK_SIZE
        self._artwork_label.setFixedSize(artwork_size, artwork_size)
        if wide:
            if self._player_panel_frame is not None:
                self._player_panel_frame.setMinimumHeight(self._PLAYER_PANEL_COMPACT_HEIGHT)
                self._player_panel_frame.setMaximumHeight(16_777_215)
                self._player_panel_frame.setSizePolicy(
                    QSizePolicy.Policy.Preferred,
                    QSizePolicy.Policy.Expanding,
                )
            self._seek_slider.setMinimumWidth(max(320, artwork_size))
            self._seek_slider.setMaximumWidth(16_777_215)
            self._seek_slider.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self._progress_widget.setMinimumWidth(self._PLAYER_MIN_WIDTH)
            self._progress_widget.setMaximumWidth(self._PLAYER_MAX_WIDTH)
            self._progress_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self._track_metadata_zone.setMinimumWidth(artwork_size)
            self._track_metadata_zone.setMaximumWidth(self._PLAYER_MAX_WIDTH)
            self._track_metadata_zone.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            self._track_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._track_meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._track_album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            if self._player_panel_frame is not None:
                self._player_panel_frame.setFixedHeight(self._PLAYER_PANEL_COMPACT_HEIGHT)
            self._seek_slider.setMinimumWidth(280)
            self._seek_slider.setMaximumWidth(16_777_215)
            self._seek_slider.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self._progress_widget.setMinimumWidth(self._PLAYER_MIN_WIDTH)
            self._progress_widget.setMaximumWidth(self._PLAYER_MAX_WIDTH)
            self._progress_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            self._track_metadata_zone.setMinimumWidth(0)
            self._track_metadata_zone.setMaximumWidth(16_777_215)
            self._track_metadata_zone.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
        self._fit_track_text_labels()

    def _rebuild_hero_layout(self, *, wide: bool) -> None:
        hero_layout = self._hero_widget.layout()
        if hero_layout is None:
            hero_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self._hero_widget)
            hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(10 if wide else 14)
        self._clear_layout_widgets(hero_layout)
        if wide:
            hero_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            hero_layout.addWidget(self._artwork_label, 0, Qt.AlignmentFlag.AlignHCenter)
            hero_layout.addWidget(
                self._track_metadata_zone,
                0,
                Qt.AlignmentFlag.AlignHCenter,
            )
            self._hero_widget.setMinimumHeight(self._artwork_label.height() + 220)
            self._hero_widget.setMaximumHeight(16_777_215)
            return
        hero_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        hero_layout.addWidget(self._artwork_label, 0, Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self._hero_info_widget, 1)
        self._hero_widget.setFixedHeight(self._artwork_label.height())
        self._hero_info_layout.removeWidget(self._track_metadata_zone)
        self._hero_info_layout.removeWidget(self._transport_widget)
        self._clear_layout_widgets(self._hero_info_layout)
        self._hero_info_layout.addStretch(1)
        self._hero_info_layout.addWidget(self._track_metadata_zone)
        self._hero_info_layout.addStretch(1)
        self._hero_info_layout.addWidget(self._transport_widget)
        self._hero_info_layout.addSpacing(10)

    def _clear_layout_widgets(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _fit_track_text_labels(self) -> None:
        self._fit_track_text_label(self._track_title_label, min_point_size=20, max_lines=3)
        self._fit_track_text_label(self._track_version_label, min_point_size=10, max_lines=1)
        self._fit_track_text_label(self._track_meta_label, min_point_size=12, max_lines=3)
        self._fit_track_text_label(self._track_album_label, min_point_size=11, max_lines=3)

    def _fit_track_text_label(
        self,
        label: QLabel,
        *,
        min_point_size: int,
        max_lines: int,
    ) -> None:
        base_size = self._track_label_base_sizes.get(label)
        if base_size is None:
            return
        text = label.text().strip()
        font = QFont(label.font())
        font.setPointSize(base_size)
        label.setFont(font)
        if not text:
            return

        available_width = max(80, label.contentsRect().width() or label.width())
        available_height = max(1, label.maximumHeight())
        flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)

        for point_size in range(base_size, min_point_size - 1, -1):
            font.setPointSize(point_size)
            metrics = label.fontMetrics() if point_size == font.pointSize() else None
            label.setFont(font)
            metrics = label.fontMetrics() if metrics is None else metrics
            rect = metrics.boundingRect(0, 0, available_width, 4096, flags, text)
            fits_height = rect.height() <= available_height
            fits_lines = rect.height() <= metrics.lineSpacing() * max_lines
            if fits_height and fits_lines:
                return

        font.setPointSize(min_point_size)
        label.setFont(font)

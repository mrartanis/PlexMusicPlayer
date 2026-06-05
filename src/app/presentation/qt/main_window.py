from __future__ import annotations

import sys
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from os import environ
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.container import AppContainer
from app.domain import PlaybackStatus, Track
from app.presentation.qt.auth_dialog import AuthDialog
from app.presentation.qt.i18n import UiTextCatalog
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.library_controller import BrowserContent, LibraryController
from app.presentation.qt.main_window_artwork import MainWindowArtworkMixin
from app.presentation.qt.main_window_browser import MainWindowBrowserMixin
from app.presentation.qt.main_window_layout import MainWindowLayoutMixin
from app.presentation.qt.main_window_library import MainWindowLibraryMixin
from app.presentation.qt.main_window_preferences import MainWindowPreferencesMixin
from app.presentation.qt.main_window_queue import MainWindowQueueMixin
from app.presentation.qt.main_window_queue_view import (
    QueueListModel,
    QueueListView,
    QueueRowDelegate,
)
from app.presentation.qt.main_window_windowing import MainWindowWindowingMixin
from app.presentation.qt.playback_controller import PlaybackController
from app.presentation.qt.system_media import build_system_media_integration
from app.presentation.qt.track_display import display_track_title


class MainWindow(
    MainWindowWindowingMixin,
    MainWindowQueueMixin,
    MainWindowArtworkMixin,
    MainWindowBrowserMixin,
    MainWindowLibraryMixin,
    MainWindowLayoutMixin,
    MainWindowPreferencesMixin,
    QMainWindow,
):
    _RESIZE_MARGIN = 8
    _SIDEBAR_DOCK_BREAKPOINT = 1360
    _BROWSER_DOCK_BREAKPOINT = 1820
    _PLAYER_MIN_WIDTH = 560
    _PLAYER_MAX_WIDTH = 700
    _PLAYER_QUEUE_WIDE_BREAKPOINT = 1180
    _WIDE_SIDE_ZONE_MAX_WIDTH = 920
    _BROWSER_ZONE_MIN_WIDTH = 460
    _BROWSER_ZONE_MAX_WIDTH = 920
    _SIDEBAR_ZONE_MIN_WIDTH = 170
    _SIDEBAR_ZONE_MAX_WIDTH = 210
    _COMPACT_ARTWORK_SIZE = 300
    _WIDE_ARTWORK_SIZE = 512
    _PLAYER_PANEL_COMPACT_HEIGHT = 434
    _QUEUE_PANEL_MIN_HEIGHT = 172
    _WINDOW_MIN_HEIGHT = 704
    _QUEUE_AUTOSCROLL_IDLE_SECONDS = 1.6
    _MY_WAVE_STATION_ID = "plex:random"
    _MY_WAVE_PERSIST_INTERVAL_MS = 5_000
    _THUMB_SOURCE_CACHE_LIMIT = 192
    _THUMB_SCALED_CACHE_LIMIT = 384
    _THUMB_SOURCE_MAX_EDGE = 128
    _paged_source_page_ready = Signal(int, object, str, str, int)
    _paged_source_failed = Signal(int, str)
    _paged_source_finished = Signal(int, int)

    def __init__(self, *, container: AppContainer) -> None:
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._container = container
        self._ui_text_catalog = UiTextCatalog(
            settings_service=container.services.settings_service
        )
        self._controller = PlaybackController(
            playback_service=container.services.playback_service,
            logger=container.logger,
        )
        self._library_controller = LibraryController(
            search_service=container.services.search_service,
            library_service=container.services.library_service,
            logger=container.logger,
            translate=self._t,
        )
        self._current_track: Track | None = None
        self._current_browser_content: BrowserContent | None = None
        self._artwork_manager = QNetworkAccessManager(self)
        self._pending_artwork_track_id: str | None = None
        self._pending_thumb_labels: dict[str, list[QLabel]] = {}
        self._pending_thumb_callbacks: dict[str, list[Callable[[], None]]] = {}
        self._queued_thumb_downloads: list[tuple[str, Path]] = []
        self._active_thumb_downloads = 0
        self._max_active_thumb_downloads = 4
        self._thumb_source_pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._thumb_scaled_pixmap_cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._auth_dialog: AuthDialog | None = None
        self._auth_flow_checked = False
        self._browser_tab_ids: tuple[str, ...] = ()
        self._updating_browser_tabs = False
        self._loading_more_content = False
        self._accent_color = "#DAA435"
        self._queue_collapsed = False
        self._browser_auto_open_enabled = False
        self._browser_dialog: QDialog | None = None
        self._settings_popup: QFrame | None = None
        self._theme_buttons: dict[str, QPushButton] = {}
        self._volume_popup: QFrame | None = None
        self._sidebar_popup: QFrame | None = None
        self._sidebar_panel: QFrame | None = None
        self._sidebar_host: QWidget | None = None
        self._sidebar_host_layout: QVBoxLayout | None = None
        self._left_zone: QWidget | None = None
        self._left_zone_layout: QHBoxLayout | None = None
        self._queue_host: QWidget | None = None
        self._queue_host_layout: QVBoxLayout | None = None
        self._sidebar_docked = False
        self._title_bar: QFrame | None = None
        self._title_drag_handle: QWidget | None = None
        self._player_panel_frame: QFrame | None = None
        self._track_metadata_zone: QWidget | None = None
        self._browser_host: QWidget | None = None
        self._browser_host_layout: QVBoxLayout | None = None
        self._browser_docked = False
        self._player_queue_wide = False
        self._rendered_queue_key: tuple[tuple[str, str, str, str], ...] = ()
        self._rendered_active_index: int | None = None
        self._rendered_playback_status = PlaybackStatus.STOPPED
        self._queue_selected_index: int | None = None
        self._queue_last_interaction_at = 0.0
        self._track_like_overrides: dict[str, bool] = {}
        self._track_label_base_sizes: dict[QLabel, int] = {}
        self._updating_resize_cursor = False
        self._pending_system_move = False
        self._pending_system_move_origin = QPointF()
        self._manual_window_drag_active = False
        self._manual_window_drag_origin = QPointF()
        self._manual_window_drag_window_pos = QPoint()
        self._volume_slider_drag_active = False
        self._my_wave_pending = False
        self._my_wave_active = False
        self._my_wave_history_dirty = False
        self._last_my_wave_persist_bucket: int | None = None
        self._pending_artwork_track: Track | None = None
        self._pending_system_media_snapshot = None
        self._paged_source_request_id = 0
        self._paged_source_started = False
        self._paged_source_mode = "play"
        self._paged_source_title = ""
        self._artwork_render_timer = QTimer(self)
        self._artwork_render_timer.setSingleShot(True)
        self._artwork_render_timer.setInterval(0)
        self._artwork_render_timer.timeout.connect(self._flush_deferred_artwork)
        self._system_media_timer = QTimer(self)
        self._system_media_timer.setSingleShot(True)
        self._system_media_timer.setInterval(40)
        self._system_media_timer.timeout.connect(self._flush_system_media_update)
        self._paged_source_page_ready.connect(self._handle_paged_source_page_ready)
        self._paged_source_failed.connect(self._handle_paged_source_failed)
        self._paged_source_finished.connect(self._handle_paged_source_finished)
        self._playback_poll_timer = QTimer(self)
        self._playback_poll_timer.setInterval(1000)
        self.setWindowTitle(self._t("app.title"))
        self._build_ui()
        self._system_media = build_system_media_integration(
            playback_controller=self._controller,
            artwork_cache=container.services.artwork_cache,
            window=self,
            logger=container.logger,
        )
        self.setMinimumWidth(600)
        self.setMinimumHeight(self._WINDOW_MIN_HEIGHT)
        self.resize(self.minimumWidth(), 720)
        self._apply_saved_settings_to_ui()
        self._restore_my_wave_history()
        self._wire_controller()
        self._system_media.initialize()
        self._controller.initialize()
        self._library_controller.initialize()
        self._browser_auto_open_enabled = True
        self._hide_browser_panel()
        self._render_auth_state()
        self._playback_poll_timer.start()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("window-root")
        root.installEventFilter(self)
        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(6)

        outer_layout.addWidget(self._build_title_bar())
        outer_layout.addLayout(self._build_body(), 1)

        self.setCentralWidget(root)
        self._apply_theme()

    def _build_title_bar(self) -> QFrame:
        frame = self._plain_frame("top-bar")
        frame.setObjectName("top-bar")
        frame.setFixedHeight(32)
        frame.installEventFilter(self)
        self._title_bar = frame
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(6)
        self._window_minimize_button = self._icon_button(
            "window-minimize.svg",
            self._t("action.minimize"),
        )
        self._window_minimize_button.setObjectName("window-control-button")
        self._window_maximize_button = self._icon_button(
            "window-maximize.svg",
            self._t("action.maximize"),
        )
        self._window_maximize_button.setObjectName("window-control-button")
        self._window_close_button = self._icon_button("window-close.svg", self._t("action.close"))
        self._window_close_button.setObjectName("window-close-button")
        window_buttons = (
            self._window_close_button,
            self._window_minimize_button,
            self._window_maximize_button,
        )
        if environ.get("QT_QPA_PLATFORM") != "offscreen" and sys.platform == "darwin":
            for button in window_buttons:
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._title_drag_handle = QWidget()
        self._title_drag_handle.setObjectName("title-drag-handle")
        self._title_drag_handle.installEventFilter(self)
        layout.addWidget(self._title_drag_handle, 1)
        if environ.get("QT_QPA_PLATFORM") == "offscreen" or sys.platform != "darwin":
            for button in (
                self._window_minimize_button,
                self._window_maximize_button,
                self._window_close_button,
            ):
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        return frame

    def _build_transport_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self._previous_button = self._icon_button("previous.svg", self._t("action.previous"))
        self._play_pause_button = self._icon_button("play.svg", self._t("action.play"))
        self._play_pause_button.setObjectName("play-button")
        self._play_pause_button.setFixedSize(52, 44)
        self._next_button = self._icon_button("next.svg", self._t("action.next"))
        self._like_track_button = QPushButton()
        self._like_track_button.setObjectName("like-current-button")
        self._like_track_button.setIcon(create_icon("heart_outline.svg"))
        self._like_track_button.setToolTip(self._t("track.tooltip.like"))
        self._like_track_button.setFixedSize(34, 32)
        for button in (
            self._previous_button,
            self._play_pause_button,
            self._next_button,
            self._like_track_button,
        ):
            layout.addWidget(button)
        return layout

    def _build_body(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self._left_zone = QWidget()
        self._left_zone.installEventFilter(self)
        self._left_zone.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._left_zone_layout = QHBoxLayout(self._left_zone)
        self._left_zone_layout.setContentsMargins(0, 0, 0, 0)
        self._left_zone_layout.setSpacing(8)
        self._sidebar_host = QWidget()
        self._sidebar_host.setMinimumWidth(self._SIDEBAR_ZONE_MIN_WIDTH)
        self._sidebar_host.setMaximumWidth(self._SIDEBAR_ZONE_MAX_WIDTH)
        self._sidebar_host.installEventFilter(self)
        self._sidebar_host_layout = QVBoxLayout(self._sidebar_host)
        self._sidebar_host_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_host_layout.setSpacing(0)
        self._sidebar_host.hide()
        self._left_zone_layout.addWidget(self._sidebar_host, 0)
        self._queue_host = QWidget()
        self._queue_host.installEventFilter(self)
        self._queue_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._queue_host_layout = QVBoxLayout(self._queue_host)
        self._queue_host_layout.setContentsMargins(0, 0, 0, 0)
        self._queue_host_layout.setSpacing(0)
        self._queue_host.hide()
        self._left_zone_layout.addWidget(self._queue_host, 1)
        self._left_zone.hide()
        layout.addWidget(self._left_zone, 1)
        self._main_column_widget = QWidget()
        self._main_column_widget.installEventFilter(self)
        self._main_column_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._main_column_layout = QVBoxLayout(self._main_column_widget)
        self._main_column_layout.setContentsMargins(0, 0, 0, 0)
        self._main_column_layout.setSpacing(4)
        self._main_column_layout.addWidget(self._build_player_panel(), 0)
        self._main_column_layout.addWidget(self._build_queue_panel(), 1)
        layout.addWidget(self._main_column_widget, 0)
        self._browser_host = QWidget()
        self._browser_host.setMinimumWidth(self._BROWSER_ZONE_MIN_WIDTH)
        self._browser_host.setMaximumWidth(self._BROWSER_ZONE_MAX_WIDTH)
        self._browser_host.installEventFilter(self)
        self._browser_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._browser_host_layout = QVBoxLayout(self._browser_host)
        self._browser_host_layout.setContentsMargins(0, 0, 0, 0)
        self._browser_host_layout.setSpacing(0)
        self._browser_host.hide()
        layout.addWidget(self._browser_host, 1)
        layout.setStretch(0, 1)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)

        self._sidebar_panel = self._build_nav_panel()
        self._sidebar_panel.installEventFilter(self)
        if self._sidebar_host_layout is not None:
            self._sidebar_host_layout.addWidget(self._sidebar_panel)
        self._build_sidebar_popup()
        self._browser_panel = self._build_browser_panel()
        self._browser_panel.installEventFilter(self)
        self._build_browser_dialog()
        return layout

    def _build_queue_panel(self) -> QFrame:
        frame = self._panel_frame("Queue")
        frame.setObjectName("queue-panel")
        self._queue_panel_widget = frame
        frame.setMinimumHeight(self._QUEUE_PANEL_MIN_HEIGHT)
        layout = frame.layout()
        assert layout is not None
        self._queue_separator = QFrame()
        self._queue_separator.setObjectName("queue-separator")
        self._queue_separator.setFixedHeight(1)
        layout.addWidget(self._queue_separator)
        self._queue_list = QueueListView(accent_provider=lambda: self._accent_color)
        self._queue_list.setObjectName("queue-list")
        self._queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._queue_list.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._queue_list.installEventFilter(self)
        self._queue_list.viewport().installEventFilter(self)
        self._queue_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._queue_model = QueueListModel(self._queue_list)
        self._queue_delegate = QueueRowDelegate(
            parent=self._queue_list,
            thumb_provider=self._thumb_pixmap_for_artwork_ref,
            thumb_requester=self._request_thumb_for_queue_row,
            format_ms=self._format_ms,
            accent_provider=lambda: self._accent_color,
            accent_text_provider=self._accent_text_color,
            theme_provider=self._resolved_theme_mode,
            corner_style_provider=self._stored_corner_style_preference,
        )
        self._queue_list.setModel(self._queue_model)
        self._queue_list.setItemDelegate(self._queue_delegate)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(
            self._queue_status_label,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        footer.addWidget(self._audio_info_label, 0, Qt.AlignmentFlag.AlignVCenter)
        footer.addStretch(1)
        self._queue_shuffle_button = QPushButton()
        self._queue_shuffle_button.setObjectName("queue-icon-button")
        self._queue_shuffle_button.setToolTip(self._t("action.shuffle_queue"))
        self._queue_shuffle_button.setFixedSize(34, 32)
        self._queue_shuffle_button.setCheckable(True)
        self._queue_shuffle_button.setIcon(create_icon("shuffle_playlist.svg"))
        self._clear_queue_button = QPushButton()
        self._clear_queue_button.setObjectName("queue-icon-button")
        self._clear_queue_button.setToolTip(self._t("action.clear_queue"))
        self._clear_queue_button.setFixedSize(34, 32)
        self._clear_queue_button.setIcon(create_icon("clear_playlist.svg"))
        self._clear_queue_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        footer.addWidget(self._queue_shuffle_button)
        footer.addWidget(self._clear_queue_button)
        layout.addWidget(self._queue_list)
        layout.addLayout(footer)
        return frame

    def _wire_controller(self) -> None:
        self._controller.playback_changed.connect(self._render_snapshot)
        self._controller.playback_failed.connect(self._render_error)
        self._library_controller.content_changed.connect(self._render_content)
        self._library_controller.content_failed.connect(self._render_library_error)
        self._library_controller.track_liked.connect(self._render_track_liked)
        self._library_controller.track_unliked.connect(self._render_track_unliked)
        self._library_controller.album_liked.connect(self._render_album_liked)
        self._library_controller.album_unliked.connect(self._render_album_unliked)
        self._library_controller.artist_liked.connect(self._render_artist_liked)
        self._library_controller.artist_unliked.connect(self._render_artist_unliked)
        self._library_controller.playlist_liked.connect(self._render_playlist_liked)
        self._library_controller.playlist_unliked.connect(self._render_playlist_unliked)
        self._sidebar_toggle_button.clicked.connect(self._toggle_sidebar)
        self._previous_button.clicked.connect(self._controller.previous)
        self._play_pause_button.clicked.connect(self._toggle_play_pause)
        self._next_button.clicked.connect(self._controller.next)
        self._seek_slider.sliderReleased.connect(self._apply_seek)
        self._volume_slider.sliderPressed.connect(self._on_volume_slider_pressed)
        self._volume_slider.sliderReleased.connect(self._on_volume_slider_released)
        self._volume_slider.valueChanged.connect(self._apply_volume)
        self._queue_list.doubleClicked.connect(self._select_queue_item)
        self._queue_list.reorder_requested.connect(self._reorder_queue_item)
        selection_model = self._queue_list.selectionModel()
        assert selection_model is not None
        selection_model.currentChanged.connect(self._select_queue_highlight_row)
        self._clear_queue_button.clicked.connect(self._clear_queue_and_cancel_paged_source)
        self._clear_queue_button.customContextMenuRequested.connect(
            self._show_clear_queue_context_menu
        )
        self._queue_shuffle_button.toggled.connect(self._controller.set_shuffle_enabled)
        self._browser_back_button.clicked.connect(self._library_controller.go_back)
        self._browser_close_button.clicked.connect(self._hide_browser_panel)
        self._content_list.itemDoubleClicked.connect(self._open_content_item)
        self._content_list.customContextMenuRequested.connect(self._show_content_context_menu)
        self._content_list.verticalScrollBar().valueChanged.connect(self._maybe_load_more_content)
        self._queue_list.customContextMenuRequested.connect(self._show_queue_context_menu)
        self._search_button.clicked.connect(self._run_search)
        self._search_input.returnPressed.connect(self._run_search)
        self._recent_searches_combo.activated.connect(self._apply_recent_search)
        self._search_nav_button.clicked.connect(self._show_search)
        self._popup_search_nav_button.clicked.connect(self._show_search)
        self._liked_nav_button.clicked.connect(self._library_controller.load_liked_tracks)
        self._popup_liked_nav_button.clicked.connect(self._library_controller.load_liked_tracks)
        self._liked_albums_nav_button.clicked.connect(self._library_controller.load_liked_albums)
        self._popup_liked_albums_nav_button.clicked.connect(
            self._library_controller.load_liked_albums
        )
        self._liked_artists_nav_button.clicked.connect(
            self._library_controller.load_liked_artists
        )
        self._popup_liked_artists_nav_button.clicked.connect(
            self._library_controller.load_liked_artists
        )
        self._playlists_nav_button.clicked.connect(self._library_controller.load_playlists)
        self._popup_playlists_nav_button.clicked.connect(self._library_controller.load_playlists)
        self._my_wave_top_button.clicked.connect(self._start_my_wave)
        self._settings_button.clicked.connect(self._show_settings_popup)
        self._like_track_button.clicked.connect(self._toggle_current_track_like)
        self._play_all_button.clicked.connect(self._play_current_source)
        self._append_all_button.clicked.connect(self._append_current_source)
        self._browser_tabs.currentChanged.connect(self._change_browser_tab)
        self._window_minimize_button.clicked.connect(self.showMinimized)
        self._window_maximize_button.clicked.connect(self._toggle_maximized)
        self._window_close_button.clicked.connect(self.close)
        self._playback_poll_timer.timeout.connect(self._controller.refresh)
        self._artwork_manager.finished.connect(self._handle_artwork_downloaded)

    def _apply_seek(self) -> None:
        self._controller.seek(self._seek_slider.value())

    def _toggle_play_pause(self) -> None:
        if self._play_pause_button.property("playback_status") == PlaybackStatus.PLAYING.value:
            self._controller.pause()
            return
        self._controller.play()

    def _toggle_maximized(self) -> None:
        if self._is_macos_window_controls():
            if self.isFullScreen():
                self.showNormal()
                return
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
                if self.isMaximized():
                    self.showNormal()
                else:
                    self.showMaximized()
                self._refresh_window_maximize_button()
                return
            self.showFullScreen()
            self._refresh_window_maximize_button()
            return
        if self.isMaximized():
            self.showNormal()
            return
        self.showMaximized()

    def _toggle_current_track_like(self) -> None:
        if self._current_track is None:
            self._status_label.setText(self._t("status.prompt_select_track"))
            return
        self._toggle_track_like(self._current_track)

    def _apply_volume(self, volume: int) -> None:
        self._controller.set_volume(volume)
        self._container.services.settings_service.save_volume(volume)

    def _on_volume_slider_pressed(self) -> None:
        self._volume_slider_drag_active = True
        self._show_volume_popup()

    def _on_volume_slider_released(self) -> None:
        self._volume_slider_drag_active = False
        self._hide_volume_popup_if_idle()

    def _adjust_volume_by_steps(self, steps: int) -> None:
        if steps == 0:
            return
        current = self._volume_slider.value()
        target = max(0, min(100, current + steps * 2))
        if target == current:
            return
        self._volume_slider.setValue(target)
        self._show_volume_popup()

    def _select_queue_item(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._mark_queue_user_interaction()
        self._set_queue_selected_index(index.row())
        self._controller.select_index(index.row())

    def _select_queue_highlight(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._mark_queue_user_interaction()
        self._set_queue_selected_index(index.row())

    def _select_queue_highlight_row(self, current: QModelIndex, previous: QModelIndex) -> None:
        del previous
        if not self._queue_list.hasFocus():
            return
        self._mark_queue_user_interaction()
        self._set_queue_selected_index(current.row() if current.isValid() else None)

    def _reorder_queue_item(self, source_row: int, target_row: int) -> None:
        self._mark_queue_user_interaction()
        self._set_queue_selected_index(target_row)
        self._controller.move_queue_item(source_row, target_row)

    def _mark_queue_user_interaction(self) -> None:
        self._queue_last_interaction_at = monotonic()

    def _should_autoscroll_queue(self) -> bool:
        return (
            monotonic() - self._queue_last_interaction_at
            >= self._QUEUE_AUTOSCROLL_IDLE_SECONDS
        )

    def _start_my_wave(self) -> None:
        self._my_wave_pending = True
        self._controller.play_station(self._MY_WAVE_STATION_ID)

    def _render_snapshot(self, snapshot) -> None:
        current_item = snapshot.current_item
        queue = snapshot.queue
        state = snapshot.state

        if current_item is not None:
            current_track = self._track_with_like_override(current_item.track)
            self._current_track = current_track
            artists = ", ".join(current_track.artists)
            track_title = display_track_title(current_track)
            album_text = (
                f"{current_track.album_title or 'Single'}"
                f"{self._format_year(current_track.album_year)}"
            )
            self._track_title_label.setText(current_track.title)
            self._track_title_label.setToolTip(track_title)
            self._track_version_label.setText(current_track.version or "")
            self._track_version_label.setToolTip(current_track.version or "")
            self._track_version_label.setVisible(bool(current_track.version))
            self._track_meta_label.setText(artists or self._t("label.unknown_artist"))
            self._track_meta_label.setToolTip(artists)
            self._track_album_label.setText(
                album_text
            )
            self._track_album_label.setToolTip(album_text)
            self._fit_track_text_labels()
            self._render_current_track_like_button(current_track.is_liked)
            self._defer_artwork_render(current_track)
        else:
            self._current_track = None
            self._track_title_label.setText(self._t("label.no_track_selected"))
            self._track_version_label.setText("")
            self._track_version_label.setVisible(False)
            self._track_meta_label.setText(self._t("track.choose_music"))
            self._track_album_label.setText("")
            self._fit_track_text_labels()
            self._render_current_track_like_button(False)
            self._pending_artwork_track = None
            self._artwork_render_timer.stop()
            self._clear_artwork()
            self._set_accent_color("#DAA435")

        self._render_play_pause_button(state.status)
        self._render_my_wave_button_state(current_item, state.status, state.position_ms)
        self._seek_slider.blockSignals(True)
        self._seek_slider.setMaximum(state.duration_ms or 300_000)
        self._seek_slider.setValue(state.position_ms)
        self._seek_slider.set_waveform_state(
            buffered_position_ms=state.waveform.buffered_position_ms,
            waveform_bins=state.waveform.waveform_bins,
            waveform_known_position_ms=state.waveform.waveform_known_position_ms,
            waveform_mode=state.waveform.waveform_mode,
        )
        self._seek_slider.blockSignals(False)
        self._seek_label.setText(
            f"{self._format_ms(state.position_ms)} / {self._format_ms(state.duration_ms)}"
        )
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(state.volume)
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{state.volume}%")
        self._queue_shuffle_button.blockSignals(True)
        self._queue_shuffle_button.setChecked(state.shuffle_enabled)
        self._queue_shuffle_button.blockSignals(False)
        self._queue_status_label.setText(
            self._t(
                "status.queue_summary",
                count=len(queue),
                duration=self._format_ms(self._queue_duration_ms(queue)),
            )
        )
        self._audio_info_label.setText(
            self._format_audio_info(state.audio_codec, state.audio_bitrate)
        )
        self._render_queue(snapshot)
        self._render_auth_state()
        self._defer_system_media_update(snapshot)

    def _defer_artwork_render(self, track: Track) -> None:
        self._pending_artwork_track = track
        self._artwork_render_timer.start()

    def _flush_deferred_artwork(self) -> None:
        track = self._pending_artwork_track
        if track is None:
            return
        self._pending_artwork_track = None
        if self._current_track is None or self._current_track.id != track.id:
            return
        self._render_artwork(track)

    def _defer_system_media_update(self, snapshot) -> None:
        self._pending_system_media_snapshot = snapshot
        self._system_media_timer.start()

    def _flush_system_media_update(self) -> None:
        snapshot = self._pending_system_media_snapshot
        if snapshot is None:
            return
        self._pending_system_media_snapshot = None
        self._system_media.update_snapshot(snapshot)

    def _track_with_like_override(self, track: Track) -> Track:
        liked = self._track_like_overrides.get(track.id)
        if liked is None or liked == track.is_liked:
            return track
        return replace(track, is_liked=liked)

    def _render_current_track_like_button(self, is_liked: bool) -> None:
        self._like_track_button.setIcon(
            create_icon("heart.svg", color=self._accent_color)
            if is_liked
            else create_icon("heart_outline.svg", color=self._theme_icon_color())
        )
        tooltip = self._t("track.tooltip.unlike") if is_liked else self._t("track.tooltip.like")
        self._like_track_button.setToolTip(tooltip)
        self._like_track_button.setAccessibleName(tooltip)

    def _render_play_pause_button(self, status: PlaybackStatus) -> None:
        self._play_pause_button.setProperty("playback_status", status.value)
        if status is PlaybackStatus.PLAYING:
            self._play_pause_button.setIcon(
                create_icon("pause.svg", color=self._accent_text_color())
            )
            self._play_pause_button.setToolTip(self._t("action.pause"))
            self._play_pause_button.setAccessibleName(self._t("action.pause"))
            return
        self._play_pause_button.setIcon(create_icon("play.svg", color=self._accent_text_color()))
        self._play_pause_button.setToolTip(self._t("action.play"))
        self._play_pause_button.setAccessibleName(self._t("action.play"))

    def _render_my_wave_button_state(
        self,
        current_item,
        status: PlaybackStatus,
        position_ms: int,
    ) -> None:
        is_my_wave = (
            current_item is not None
            and current_item.source_type == "station"
            and current_item.source_id == self._MY_WAVE_STATION_ID
        )
        self._my_wave_active = is_my_wave and status is PlaybackStatus.PLAYING
        if is_my_wave:
            self._my_wave_pending = False
        if self._my_wave_top_button.sync_playback(
            enabled=self._my_wave_active,
            track_id=current_item.track.id if is_my_wave else None,
            position_ms=position_ms,
            accent=self._accent_color,
        ):
            self._my_wave_history_dirty = True
        self._maybe_persist_my_wave_history(
            status=status,
            position_ms=position_ms,
        )

    def _my_wave_trailing_color(self) -> str:
        if self._resolved_theme_mode() == "light":
            return "#efd9a8"
        return "#5d4921"

    def _render_error(self, message: str) -> None:
        self._my_wave_pending = False
        self._my_wave_active = False
        self._status_label.setText(self._t("status.playback_error", message=message))

    def _restore_my_wave_history(self) -> None:
        samples = self._container.services.settings_service.load_my_wave_history()
        self._my_wave_top_button.restore_history(samples)
        self._my_wave_history_dirty = False
        self._last_my_wave_persist_bucket = None

    def _persist_my_wave_history(self) -> None:
        self._container.services.settings_service.save_my_wave_history(
            self._my_wave_top_button.export_history()
        )
        self._my_wave_history_dirty = False

    def _maybe_persist_my_wave_history(
        self,
        *,
        status: PlaybackStatus,
        position_ms: int,
    ) -> None:
        if not self._my_wave_history_dirty:
            return
        if status is PlaybackStatus.PLAYING:
            bucket = max(0, position_ms) // self._MY_WAVE_PERSIST_INTERVAL_MS
            if bucket == self._last_my_wave_persist_bucket:
                return
            self._persist_my_wave_history()
            self._last_my_wave_persist_bucket = bucket
            return
        self._persist_my_wave_history()

    def _flush_my_wave_history(self) -> None:
        if self._my_wave_history_dirty:
            self._persist_my_wave_history()

    def _render_auth_state(self) -> None:
        session = self._container.services.auth_service.current_session()
        if session is None:
            self._auth_label.setText(self._t("label.login_required"))
            if hasattr(self, "_logout_button"):
                self._logout_button.setEnabled(False)
            return
        self._auth_label.setText(self._session_identity_text(session))
        if hasattr(self, "_logout_button"):
            self._logout_button.setEnabled(True)

    def _session_identity_text(self, session) -> str:
        display_name = (session.display_name or "").strip()
        if display_name and display_name.casefold() != "plex":
            return display_name
        return (
            session.server_name
            or display_name
            or session.user_id
            or "Plex"
        )

    def _t(self, key: str, **params: object) -> str:
        return self._ui_text_catalog.text(key, **params)

    def _refresh_main_window_texts(self) -> None:
        self._window_minimize_button.setToolTip(self._t("action.minimize"))
        self._window_minimize_button.setAccessibleName(self._t("action.minimize"))
        self._window_close_button.setToolTip(self._t("action.close"))
        self._window_close_button.setAccessibleName(self._t("action.close"))
        self._previous_button.setToolTip(self._t("action.previous"))
        self._previous_button.setAccessibleName(self._t("action.previous"))
        self._next_button.setToolTip(self._t("action.next"))
        self._next_button.setAccessibleName(self._t("action.next"))
        self._sidebar_toggle_button.setToolTip(self._t("action.toggle_navigation"))
        self._my_wave_top_button.setText(self._t("nav.my_wave"))
        self._settings_button.setToolTip(self._t("action.settings"))
        self._settings_button.setAccessibleName(self._t("action.settings"))
        self._volume_button.setToolTip(self._t("action.volume"))
        self._queue_shuffle_button.setToolTip(self._t("action.shuffle_queue"))
        self._clear_queue_button.setToolTip(self._t("action.clear_queue"))
        self._search_button.setText(self._t("action.search"))
        self._play_all_button.setText(self._t("action.play_all"))
        self._append_all_button.setText(self._t("action.append_all"))
        self._search_input.setPlaceholderText(self._t("browser.placeholder.search"))
        self._recent_searches_combo.setPlaceholderText(
            self._t("browser.placeholder.recent_searches")
        )
        self._browser_back_button.setToolTip(self._t("action.back"))
        self._browser_close_button.setToolTip(self._t("action.close"))
        self._browser_dialog.setWindowTitle(self._t("window.search_library"))
        self._search_nav_button.setText(self._t("action.search"))
        self._liked_nav_button.setText(self._t("nav.my_tracks"))
        self._liked_albums_nav_button.setText(self._t("nav.my_albums"))
        self._liked_artists_nav_button.setText(self._t("nav.my_artists"))
        self._playlists_nav_button.setText(self._t("nav.playlists"))
        self._nav_library_label.setText(self._t("label.library"))
        self._nav_discovery_label.setText(self._t("label.discovery"))
        self._popup_search_nav_button.setText(self._t("action.search"))
        self._popup_liked_nav_button.setText(self._t("nav.my_tracks"))
        self._popup_liked_albums_nav_button.setText(self._t("nav.my_albums"))
        self._popup_liked_artists_nav_button.setText(self._t("nav.my_artists"))
        self._popup_playlists_nav_button.setText(self._t("nav.playlists"))
        self._popup_nav_library_label.setText(self._t("label.library"))
        self._popup_nav_discovery_label.setText(self._t("label.discovery"))
        self._render_auth_state()
        self._refresh_window_maximize_button()
        self._render_snapshot(self._container.services.playback_service.snapshot())


    def _plain_frame(self, name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(name)
        return frame

    def _panel_frame(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setObjectName(title.lower().replace(" ", "-"))

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 0, 8, 2)
        layout.setSpacing(2)
        return frame

    def _panel_label(self, text: str, *, align_right: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(
            Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        )
        return label


    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(create_icon(icon_name))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(34, 32)
        return button

    def _format_ms(self, value: int | None) -> str:
        if value is None:
            return "0:00"
        minutes, remainder = divmod(value // 1000, 60)
        return f"{minutes}:{remainder:02d}"

    def _handle_frame_resize_event(self, watched: object, event: QEvent) -> bool:
        if self._updating_resize_cursor:
            return False
        if self.isMaximized():
            self._set_resize_cursor(None)
            return False
        if not isinstance(watched, QWidget):
            return False
        if watched.window() is not self:
            return False
        if event.type() not in {
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Leave,
        }:
            return False
        if event.type() == QEvent.Type.Leave:
            if watched is self:
                self._set_resize_cursor(None)
            return False

        mouse_event = self._as_mouse_event(event)
        if mouse_event is None:
            return False
        edges = self._resize_edges_for_global_pos(mouse_event.globalPosition().toPoint())
        if event.type() == QEvent.Type.MouseMove:
            if edges == Qt.Edge(0):
                self._set_resize_cursor(None)
            else:
                self._set_resize_cursor(self._cursor_for_edges(edges))
            return False
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and mouse_event.button() == Qt.MouseButton.LeftButton
            and edges != Qt.Edge(0)
        ):
            self._start_system_resize(edges)
            return True
        return False

    def _resize_edges_for_global_pos(self, global_pos: QPoint) -> Qt.Edge:
        rect = self.frameGeometry()
        edges = Qt.Edge(0)
        if abs(global_pos.x() - rect.left()) <= self._RESIZE_MARGIN:
            edges |= Qt.Edge.LeftEdge
        elif abs(global_pos.x() - rect.right()) <= self._RESIZE_MARGIN:
            edges |= Qt.Edge.RightEdge
        if abs(global_pos.y() - rect.top()) <= self._RESIZE_MARGIN:
            edges |= Qt.Edge.TopEdge
        elif abs(global_pos.y() - rect.bottom()) <= self._RESIZE_MARGIN:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _cursor_for_edges(self, edges: Qt.Edge) -> Qt.CursorShape:
        if edges in {Qt.Edge.TopEdge, Qt.Edge.BottomEdge}:
            return Qt.CursorShape.SizeVerCursor
        if edges in {Qt.Edge.LeftEdge, Qt.Edge.RightEdge}:
            return Qt.CursorShape.SizeHorCursor
        if edges in {
            Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
        }:
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.SizeBDiagCursor

    def _start_system_move(self) -> bool:
        window_handle = self.windowHandle()
        if window_handle is not None:
            return bool(window_handle.startSystemMove())
        return False

    def _start_system_resize(self, edges: Qt.Edge) -> None:
        window_handle = self.windowHandle()
        if window_handle is not None:
            window_handle.startSystemResize(edges)

    def _set_resize_cursor(self, cursor: Qt.CursorShape | None) -> None:
        self._updating_resize_cursor = True
        try:
            if cursor is None:
                QWidget.unsetCursor(self)
            else:
                QWidget.setCursor(self, cursor)
        finally:
            self._updating_resize_cursor = False

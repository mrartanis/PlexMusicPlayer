from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain import Album, Artist, Playlist, Station, Track
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.library_controller import BrowserContent, BrowserItem, BrowserTab


class MainWindowBrowserMixin:
    def _build_browser_panel(self) -> QFrame:
        frame = self._panel_frame("Search / Library")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        base_layout = frame.layout()
        assert base_layout is not None
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(self._t("browser.placeholder.search"))
        self._search_button = QPushButton(self._t("action.search"))
        self._search_loading = QProgressBar()
        self._search_loading.setRange(0, 0)
        self._search_loading.setTextVisible(False)
        self._search_loading.setFixedWidth(30)
        self._search_loading.setFixedHeight(12)
        self._search_loading.hide()
        self._recent_searches_combo = QComboBox()
        self._recent_searches_combo.setPlaceholderText(self._t("browser.placeholder.recent_searches"))
        self._recent_searches_combo.addItem(self._t("browser.placeholder.recent_searches"))
        self._browser_title_label = self._panel_label(self._t("library.search"))
        self._browser_title_label.setObjectName("browser-title")
        self._browser_back_button = QPushButton("‹")
        self._browser_back_button.setObjectName("panel-back-button")
        self._browser_back_button.setToolTip(self._t("action.back"))
        self._browser_back_button.setFixedSize(32, 30)
        self._browser_back_button.setEnabled(False)
        self._browser_close_button = QPushButton("×")
        self._browser_close_button.setObjectName("panel-close-button")
        self._browser_close_button.setToolTip(self._t("action.close"))
        self._browser_close_button.setFixedSize(32, 30)
        self._browser_tabs = QTabWidget()
        self._browser_tabs.setVisible(False)
        self._content_list = QListWidget()
        self._content_list.setAlternatingRowColors(True)
        self._content_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._content_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._play_all_button = QPushButton(self._t("action.play_all"))
        self._play_all_button.setIcon(create_icon("play.svg"))
        self._play_all_button.setFixedHeight(32)
        self._append_all_button = QPushButton(self._t("action.append_all"))
        self._append_all_button.setIcon(create_icon("add_to_playlist.svg"))
        self._append_all_button.setFixedHeight(32)
        header_row.addWidget(self._browser_back_button)
        header_row.addWidget(self._browser_title_label, 1)
        header_row.addWidget(self._browser_close_button)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_button)
        search_row.addWidget(self._search_loading, 0, Qt.AlignmentFlag.AlignVCenter)
        search_row.addWidget(self._recent_searches_combo)
        browser_footer = QWidget()
        browser_footer.setFixedHeight(32)
        like_row = QHBoxLayout(browser_footer)
        like_row.setSpacing(8)
        like_row.setContentsMargins(0, 0, 0, 0)
        like_row.addWidget(self._play_all_button, 0, Qt.AlignmentFlag.AlignVCenter)
        like_row.addWidget(self._append_all_button, 0, Qt.AlignmentFlag.AlignVCenter)
        like_row.addStretch(1)
        base_layout.addLayout(header_row)
        base_layout.addLayout(search_row)
        base_layout.addWidget(self._browser_tabs)
        base_layout.addWidget(self._content_list, 1)
        base_layout.addWidget(browser_footer, 0, Qt.AlignmentFlag.AlignBottom)
        return frame

    def _build_browser_dialog(self) -> None:
        self._browser_dialog = QDialog(self)
        self._browser_dialog.setWindowTitle(self._t("window.search_library"))
        self._browser_dialog.setModal(False)
        self._browser_dialog.resize(860, 560)
        dialog_layout = QVBoxLayout(self._browser_dialog)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(self._browser_panel)
        self._browser_dialog.setStyleSheet(self.styleSheet())

    def _show_browser_panel(self) -> None:
        if self._browser_docked:
            if self._browser_host is not None:
                self._browser_host.show()
            return
        if self._browser_dialog is None:
            return
        self._browser_dialog.show()
        self._browser_dialog.raise_()
        self._browser_dialog.activateWindow()

    def _hide_browser_panel(self) -> None:
        if self._browser_docked:
            return
        if self._browser_dialog is not None:
            self._browser_dialog.hide()

    def _open_content_item(self, item: QListWidgetItem) -> None:
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return

        payload = browser_item.payload
        if browser_item.kind == "track" and isinstance(payload, Track):
            if browser_item.source_type == "station" and browser_item.source_id:
                self._controller.play_station(browser_item.source_id)
                return
            if (
                browser_item.source_tracks
                and browser_item.source_type
                and browser_item.source_id
                and browser_item.source_index is not None
            ):
                self._controller.play_tracks(
                    browser_item.source_tracks,
                    start_index=browser_item.source_index,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                )
                return
            self._controller.play_track(payload)
            return
        if browser_item.kind == "album" and isinstance(payload, Album):
            self._library_controller.open_album(payload)
            return
        if (
            browser_item.kind in {"playlist", "generated_playlist", "collection"}
            and isinstance(payload, Playlist)
        ):
            self._library_controller.open_playlist(payload)
            return
        if browser_item.kind == "station" and isinstance(payload, Station):
            self._library_controller.open_station(payload)
            return
        if browser_item.kind == "artist" and isinstance(payload, Artist):
            self._library_controller.open_artist(payload)
            return

    def _run_search(self) -> None:
        self._show_browser_panel()
        self._library_controller.search_tracks(self._search_input.text())

    def _show_search(self) -> None:
        self._show_browser_panel()
        self._library_controller.show_search_page()
        self._search_input.setFocus()

    def _change_browser_tab(self, index: int) -> None:
        if self._updating_browser_tabs:
            return
        if index < 0 or index >= len(self._browser_tab_ids):
            return
        self._library_controller.show_browser_tab(self._browser_tab_ids[index])

    def _apply_recent_search(self, index: int) -> None:
        if index <= 0:
            return
        query = self._recent_searches_combo.itemText(index)
        self._search_input.setText(query)
        self._show_browser_panel()
        self._library_controller.search_tracks(query)

    def _render_content(self, content: BrowserContent) -> None:
        if self._browser_auto_open_enabled:
            self._show_browser_panel()
        previous_content = self._current_browser_content
        scroll_bar = self._content_list.verticalScrollBar()
        previous_scroll_value = scroll_bar.value()
        preserve_scroll = bool(
            self._loading_more_content
            and previous_content is not None
            and previous_content.list_key
            and previous_content.list_key == content.list_key
            and len(content.items) >= len(previous_content.items)
        )
        self._current_browser_content = content
        self._loading_more_content = False
        self._browser_title_label.setText(content.title)
        self._browser_back_button.setEnabled(self._library_controller.can_go_back())
        self._render_browser_tabs(content.tabs, active_tab=content.active_tab)
        self._search_loading.setVisible(content.is_loading)
        self._search_button.setEnabled(not content.is_loading)
        if content.search_query is not None:
            self._search_input.setText(content.search_query)
        self._recent_searches_combo.blockSignals(True)
        self._recent_searches_combo.clear()
        self._recent_searches_combo.addItem(self._t("browser.placeholder.recent_searches"))
        for query in content.recent_searches:
            self._recent_searches_combo.addItem(query)
        self._recent_searches_combo.blockSignals(False)

        self._content_list.blockSignals(True)
        self._content_list.clear()
        if not content.items:
            label = self._t("browser.loading") if content.is_loading else self._t("browser.empty")
            empty_item = QListWidgetItem(label)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._content_list.addItem(empty_item)
        for browser_item in content.items:
            text = browser_item.title
            if browser_item.subtitle:
                text = f"{browser_item.title}\n{browser_item.subtitle}"
            widget_item = QListWidgetItem(text)
            widget_item.setData(Qt.ItemDataRole.UserRole, browser_item)
            if browser_item.kind == "section":
                widget_item.setFlags(widget_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            elif self._browser_item_uses_art(browser_item):
                widget = self._browser_art_row_widget(browser_item)
                widget_item.setSizeHint(widget.sizeHint())
                widget_item.setText("")
            self._content_list.addItem(widget_item)
            if browser_item.kind != "section" and self._browser_item_uses_art(browser_item):
                self._content_list.setItemWidget(widget_item, widget)
        self._content_list.blockSignals(False)
        if preserve_scroll:
            self._content_list.verticalScrollBar().setValue(previous_scroll_value)
        can_play_source = bool(
            content.source_type
            and content.source_id
            and (
                content.bulk_mode in {"load_all", "stream_pages"}
                or bool(content.source_tracks)
            )
        )
        self._play_all_button.setEnabled(can_play_source)
        self._append_all_button.setEnabled(can_play_source)

    def _browser_item_uses_art(self, item: BrowserItem) -> bool:
        return item.kind in {
            "album",
            "artist",
        }

    def _browser_art_row_widget(self, item: BrowserItem) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(9)
        artwork_ref = getattr(item.payload, "artwork_ref", None)
        layout.addWidget(self._art_thumb_label(artwork_ref, size=46))
        text_container = QWidget()
        text_container.setObjectName("browser-art-text")
        text_container.setMinimumWidth(0)
        text_container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title = QLabel(item.title)
        title.setObjectName("browser-art-title")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        subtitle = QLabel(item.subtitle or "")
        subtitle.setObjectName("browser-art-subtitle")
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addWidget(text_container, 1)
        return row

    def _art_thumb_label(self, artwork_ref: str | None, *, size: int) -> QLabel:
        label = QLabel()
        label.setObjectName("art-thumb")
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not artwork_ref:
            label.setText("♪")
            return label
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            label.setText("♪")
            return label
        pixmap = self._thumb_pixmap_for_url(artwork_url, size=size)
        if pixmap is None:
            label.setText("♪")
            cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
            self._queue_thumb_download(artwork_url, cache_path, label)
            return label
        label.setText("")
        label.setPixmap(pixmap)
        return label

    def _queue_thumb_download(
        self,
        artwork_url: str,
        cache_path: Path,
        label: QLabel | None = None,
        *,
        on_ready=None,
    ) -> None:
        labels = self._pending_thumb_labels.setdefault(artwork_url, [])
        if label is not None:
            labels.append(label)
        callbacks = self._pending_thumb_callbacks.setdefault(artwork_url, [])
        if on_ready is not None:
            callbacks.append(on_ready)
        if len(labels) + len(callbacks) > 1:
            return
        self._queued_thumb_downloads.append((artwork_url, cache_path))
        self._start_next_thumb_downloads()

    def _start_next_thumb_downloads(self) -> None:
        while (
            self._queued_thumb_downloads
            and self._active_thumb_downloads < self._max_active_thumb_downloads
        ):
            artwork_url, cache_path = self._queued_thumb_downloads.pop(0)
            self._start_thumb_download(artwork_url, cache_path)

    def _start_thumb_download(self, artwork_url: str, cache_path: Path) -> None:
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("thumb_artwork_url", artwork_url)
        reply.setProperty("cache_path", str(cache_path))
        self._active_thumb_downloads += 1

    def _set_thumb_pixmap(self, label: QLabel, pixmap: QPixmap) -> None:
        if not shiboken6.isValid(label):
            return
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _maybe_load_more_content(self, value: int) -> None:
        content = self._current_browser_content
        if self._loading_more_content or content is None:
            return
        if not content.list_key:
            return
        if not content.has_more or content.is_loading:
            return
        scroll_bar = self._content_list.verticalScrollBar()
        if value < scroll_bar.maximum() - 2:
            return
        self._loading_more_content = True
        self._library_controller.load_more_current_list()

    def _render_browser_tabs(
        self,
        tabs: tuple[BrowserTab, ...],
        *,
        active_tab: str | None = None,
    ) -> None:
        self._updating_browser_tabs = True
        self._browser_tabs.clear()
        self._browser_tab_ids = tuple(tab.id for tab in tabs)
        for tab in tabs:
            self._browser_tabs.addTab(QWidget(), tab.title)
        active_index = (
            self._browser_tab_ids.index(active_tab)
            if active_tab in self._browser_tab_ids
            else 0
        )
        if self._browser_tab_ids:
            self._browser_tabs.setCurrentIndex(active_index)
        self._browser_tabs.setVisible(bool(self._browser_tab_ids))
        self._updating_browser_tabs = False

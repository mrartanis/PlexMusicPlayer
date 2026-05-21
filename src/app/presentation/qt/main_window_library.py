from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime
from io import StringIO
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QPoint, QStandardPaths, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu

from app.application.error_presenter import user_facing_error_message
from app.domain import Album, Artist, Playlist, Station, Track
from app.domain.errors import DomainError
from app.domain.playback import QueueItem
from app.presentation.qt.library_controller import BrowserItem
from app.presentation.qt.track_display import display_track_title


class MainWindowLibraryMixin:
    def _render_library_error(self, message: str) -> None:
        self._status_label.setText(self._t("status.library_error", message=message))

    def _render_track_liked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = True
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(True)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(
            self._t("status.track.like", title=display_track_title(track))
        )

    def _render_track_unliked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = False
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(False)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(
            self._t("status.track.unlike", title=display_track_title(track))
        )

    def _render_album_liked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(self._t("status.album.like", title=album.title))

    def _render_album_unliked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(self._t("status.album.unlike", title=album.title))

    def _render_artist_liked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(self._t("status.artist.like", name=artist.name))

    def _render_artist_unliked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(self._t("status.artist.unlike", name=artist.name))

    def _render_playlist_liked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(self._t("status.playlist.like", title=playlist.title))

    def _render_playlist_unliked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(self._t("status.playlist.unlike", title=playlist.title))

    def _like_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText(self._t("status.library_select_track"))
            return
        self._library_controller.like_track(track)

    def _unlike_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText(self._t("status.library_select_track"))
            return
        self._library_controller.unlike_track(track)

    def _selected_or_current_track(self) -> Track | None:
        item = self._content_list.currentItem()
        if item is not None:
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(browser_item, BrowserItem) and isinstance(browser_item.payload, Track):
                return browser_item.payload
        return self._current_track

    def _play_current_source(self) -> None:
        self._cancel_paged_source_load()
        content = self._current_browser_content
        if content is not None and content.bulk_mode == "stream_pages":
            self._start_paged_source_load(mode="play")
            return
        bulk_request = self._resolve_current_source_bulk_request()
        if bulk_request is None:
            return
        tracks, source_type, source_id = bulk_request
        self._controller.play_tracks(
            tracks,
            start_index=0,
            source_type=source_type,
            source_id=source_id,
        )

    def _append_current_source(self) -> None:
        content = self._current_browser_content
        if content is not None and content.bulk_mode == "stream_pages":
            self._start_paged_source_load(mode="append")
            return
        bulk_request = self._resolve_current_source_bulk_request()
        if bulk_request is None:
            return
        tracks, source_type, source_id = bulk_request
        self._controller.append_tracks(
            tracks,
            source_type=source_type,
            source_id=source_id,
        )

    def _resolve_current_source_bulk_request(self) -> tuple[tuple[Track, ...], str, str] | None:
        content = self._current_browser_content
        if content is None or not content.source_type or not content.source_id:
            return None
        if content.bulk_mode == "load_all":
            self._status_label.setText(self._t("status.loading_full_source"))
            return self._library_controller.load_full_current_source_tracks()
        if not content.source_tracks:
            return None
        return content.source_tracks, content.source_type, content.source_id

    def _start_paged_source_load(self, *, mode: str) -> None:
        content = self._current_browser_content
        if content is None:
            return
        request = self._library_controller.resolve_current_source_paged_request(page_size=50)
        if request is None:
            self._status_label.setText(self._t("status.library_select_track"))
            return
        self._paged_source_request_id += 1
        request_id = self._paged_source_request_id
        self._paged_source_started = False
        self._paged_source_mode = mode
        self._paged_source_title = content.title
        self._container.logger.info(
            "Starting paged source load: mode=%s source_type=%s source_id=%s title=%s",
            mode,
            request.source_type,
            request.source_id,
            content.title,
        )
        self._status_label.setText(
            self._t("status.loading_source_start", title=content.title)
        )

        def _runner() -> None:
            offset = 0
            total = 0
            try:
                while True:
                    tracks = request.load_page(offset, request.page_size)
                    if request_id != self._paged_source_request_id:
                        return
                    if not tracks:
                        break
                    total += len(tracks)
                    self._container.logger.info(
                        "Paged source page ready: request_id=%s source_id=%s "
                        "page_tracks=%s total=%s",
                        request_id,
                        request.source_id,
                        len(tracks),
                        total,
                    )
                    self._paged_source_page_ready.emit(
                        request_id,
                        tracks,
                        request.source_type,
                        request.source_id,
                        total,
                    )
                    offset += len(tracks)
                    if len(tracks) < request.page_size:
                        break
            except DomainError as exc:
                self._paged_source_failed.emit(
                    request_id,
                    user_facing_error_message(exc),
                )
                return
            except Exception as exc:  # noqa: BLE001
                self._container.logger.exception(
                    "Paged source load crashed: request_id=%s source_id=%s",
                    request_id,
                    request.source_id,
                )
                self._paged_source_failed.emit(
                    request_id,
                    str(exc),
                )
                return
            self._paged_source_finished.emit(request_id, total)

        Thread(
            target=_runner,
            name=f"paged-source-{request_id}",
            daemon=True,
        ).start()

    def _cancel_paged_source_load(self) -> None:
        self._paged_source_request_id += 1
        self._paged_source_started = False
        self._paged_source_mode = "play"
        self._paged_source_title = ""

    def _clear_queue_and_cancel_paged_source(self) -> None:
        self._cancel_paged_source_load()
        self._controller.clear_queue()

    def _handle_paged_source_page_ready(
        self,
        request_id: int,
        tracks: tuple[Track, ...],
        source_type: str,
        source_id: str,
        total: int,
    ) -> None:
        if request_id != self._paged_source_request_id:
            return
        self._container.logger.info(
            "Applying paged source page: request_id=%s source_id=%s "
            "started=%s page_tracks=%s total=%s",
            request_id,
            source_id,
            self._paged_source_started,
            len(tracks),
            total,
        )
        if not self._paged_source_started:
            if self._paged_source_mode == "play":
                self._controller.play_tracks(
                    tracks,
                    start_index=0,
                    source_type=source_type,
                    source_id=source_id,
                )
            else:
                self._controller.append_tracks(
                    tracks,
                    source_type=source_type,
                    source_id=source_id,
                )
            self._paged_source_started = True
        else:
            self._controller.append_tracks(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )
        self._status_label.setText(
            self._t(
                "status.loading_source_progress",
                title=self._paged_source_title,
                count=total,
            )
        )

    def _handle_paged_source_failed(self, request_id: int, message: str) -> None:
        if request_id != self._paged_source_request_id:
            return
        self._status_label.setText(self._t("status.library_error", message=message))

    def _handle_paged_source_finished(self, request_id: int, total: int) -> None:
        if request_id != self._paged_source_request_id:
            return
        self._status_label.setText(
            self._t(
                "status.loading_source_complete",
                title=self._paged_source_title,
                count=total,
            )
        )

    def _replace_content_track(self, track: Track) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            if not isinstance(browser_item.payload, Track):
                continue
            if browser_item.payload.id != track.id:
                continue
            title = display_track_title(track)
            text = title
            subtitle = ", ".join(track.artists)
            if track.album_title:
                subtitle = f"{subtitle} | {track.album_title}" if subtitle else track.album_title
            if subtitle:
                text = f"{title}\n{subtitle}"
            item.setText(text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=title,
                    subtitle=subtitle,
                    payload=track,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _update_queue_track_like(self, track: Track) -> None:
        for index in range(self._queue_model.rowCount()):
            queue_item = self._queue_model.queue_item_at(index)
            if not isinstance(queue_item, QueueItem):
                continue
            if queue_item.track.id != track.id:
                continue
            self._queue_model.replace_queue_item(
                index,
                replace(queue_item, track=track),
            )

    def _replace_content_entity(self, entity: Album | Artist | Playlist) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            payload = browser_item.payload
            if type(payload) is not type(entity):
                continue
            if getattr(payload, "id", None) != getattr(entity, "id", None):
                continue
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=browser_item.title,
                    subtitle=browser_item.subtitle,
                    payload=entity,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _show_content_context_menu(self, position: QPoint) -> None:
        item = self._content_list.itemAt(position)
        if item is None:
            return
        self._content_list.setCurrentItem(item)
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return
        menu = QMenu(self)
        if not self._populate_browser_item_menu(menu, browser_item):
            return
        menu.exec(self._content_list.viewport().mapToGlobal(position))

    def _show_queue_context_menu(self, position: QPoint) -> None:
        index = self._queue_list.indexAt(position)
        if not index.isValid():
            return
        self._queue_list.setCurrentIndex(index)
        self._select_queue_highlight(index)
        queue_item = self._queue_model.queue_item_at(index.row())
        if not isinstance(queue_item, QueueItem):
            return
        menu = QMenu(self)
        if not self._populate_queue_item_menu(menu, queue_item, index.row()):
            return
        menu.exec(self._queue_list.viewport().mapToGlobal(position))

    def _show_clear_queue_context_menu(self, position: QPoint) -> None:
        if self._queue_model.rowCount() <= 0:
            return
        menu = QMenu(self)
        self._add_export_queue_action(menu)
        if menu.isEmpty():
            return
        menu.exec(self._clear_queue_button.mapToGlobal(position))

    def _populate_browser_item_menu(self, menu: QMenu, browser_item: BrowserItem) -> bool:
        payload = browser_item.payload
        if isinstance(payload, Track):
            return self._populate_track_menu(menu, payload)
        if isinstance(payload, Album):
            self._add_go_to_artist_actions(menu, payload.artist_ids, payload.artists)
            return not menu.isEmpty()
        if isinstance(payload, Artist):
            return not menu.isEmpty()
        if isinstance(payload, Playlist):
            return not menu.isEmpty()
        if isinstance(payload, Station):
            return not menu.isEmpty()
        return False

    def _populate_track_menu(
        self,
        menu: QMenu,
        track: Track,
        *,
        include_queue_actions: bool = True,
    ) -> bool:
        action_text = self._t("action.unlike") if track.is_liked else self._t("action.like")
        toggle_like = QAction(action_text, self)
        toggle_like.triggered.connect(
            lambda checked=False, selected_track=track: self._toggle_track_like(selected_track)
        )
        menu.addAction(toggle_like)
        if include_queue_actions:
            add_to_queue = QAction(self._t("action.add_to_queue"), self)
            add_to_queue.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.append_tracks(
                    (selected_track,),
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(add_to_queue)
            play_next = QAction(self._t("action.play_next"), self)
            play_next.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.play_track_next(
                    selected_track,
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(play_next)
        self._add_go_to_artist_actions(menu, track.artist_ids, track.artists)
        if track.album_id:
            go_to_album = QAction(self._t("action.go_to_album"), self)
            album_id = track.album_id
            go_to_album.triggered.connect(
                lambda checked=False, selected_album_id=album_id: (
                    self._library_controller.open_album_by_id(selected_album_id)
                )
            )
            menu.addAction(go_to_album)
        return not menu.isEmpty()

    def _populate_queue_item_menu(
        self,
        menu: QMenu,
        queue_item: QueueItem,
        queue_index: int,
    ) -> bool:
        self._populate_track_menu(menu, queue_item.track, include_queue_actions=False)
        play_next = QAction(self._t("action.play_next"), self)
        play_next.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.move_queue_item_next(index)
        )
        menu.addAction(play_next)
        remove_action = QAction(self._t("action.remove_from_queue"), self)
        remove_action.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.remove_queue_index(index)
        )
        menu.addAction(remove_action)
        return not menu.isEmpty()

    def _add_export_queue_action(self, menu: QMenu) -> None:
        if self._queue_model.rowCount() <= 0:
            return
        if not menu.isEmpty():
            menu.addSeparator()
        action = QAction(self._t("action.export_playlist"), self)
        action.triggered.connect(self._export_queue_playlist)
        menu.addAction(action)

    def _toggle_track_like(self, track: Track) -> None:
        if track.is_liked:
            self._library_controller.unlike_track(track)
            return
        self._library_controller.like_track(track)

    def _add_album_like_action(self, menu: QMenu, album: Album) -> None:
        action = QAction(
            self._t("action.unlike") if album.is_liked else self._t("action.like"),
            self,
        )
        action.triggered.connect(
            lambda checked=False, selected_album=album: self._toggle_album_like(selected_album)
        )
        menu.addAction(action)

    def _add_artist_like_action(self, menu: QMenu, artist: Artist) -> None:
        action = QAction(
            self._t("action.unlike") if artist.is_liked else self._t("action.like"),
            self,
        )
        action.triggered.connect(
            lambda checked=False, selected_artist=artist: self._toggle_artist_like(selected_artist)
        )
        menu.addAction(action)

    def _add_playlist_like_action(self, menu: QMenu, playlist: Playlist) -> None:
        action = QAction(
            self._t("action.unlike") if playlist.is_liked else self._t("action.like"),
            self,
        )
        action.triggered.connect(
            lambda checked=False, selected_playlist=playlist: self._toggle_playlist_like(
                selected_playlist
            )
        )
        menu.addAction(action)

    def _toggle_album_like(self, album: Album) -> None:
        if album.is_liked:
            self._library_controller.unlike_album(album)
            return
        self._library_controller.like_album(album)

    def _toggle_artist_like(self, artist: Artist) -> None:
        if artist.is_liked:
            self._library_controller.unlike_artist(artist)
            return
        self._library_controller.like_artist(artist)

    def _toggle_playlist_like(self, playlist: Playlist) -> None:
        if playlist.is_liked:
            self._library_controller.unlike_playlist(playlist)
            return
        self._library_controller.like_playlist(playlist)

    def _add_copy_share_link_action(self, menu: QMenu, link: str | None) -> None:
        if not link:
            return
        action = QAction(self._t("action.copy_share_link"), self)
        action.triggered.connect(
            lambda checked=False, share_link=link: self._copy_share_link(share_link)
        )
        menu.addAction(action)

    def _add_go_to_artist_actions(
        self,
        menu: QMenu,
        artist_ids: tuple[str, ...],
        artist_names: tuple[str, ...],
    ) -> None:
        artists = [
            Artist(id=artist_id, name=artist_name)
            for artist_id, artist_name in zip(artist_ids, artist_names, strict=False)
        ]
        if not artists:
            return
        if len(artists) == 1:
            artist = artists[0]
            action = QAction(self._t("action.go_to_artist"), self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            menu.addAction(action)
            return
        submenu = menu.addMenu(self._t("action.go_to_artist"))
        for artist in artists:
            action = QAction(artist.name, self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            submenu.addAction(action)

    def _copy_share_link(self, link: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(link)
        self._status_label.setText(self._t("status.copied_share_link", link=link))

    def _export_queue_playlist(self) -> None:
        queue_items = tuple(
            queue_item
            for row in range(self._queue_model.rowCount())
            if isinstance((queue_item := self._queue_model.queue_item_at(row)), QueueItem)
        )
        if not queue_items:
            self._status_label.setText(self._t("status.export_playlist.empty"))
            return

        path, export_format = self._choose_queue_export_path()
        if path is None or export_format is None:
            return

        try:
            payload = self._serialize_queue_export(queue_items, export_format)
            path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            self._container.logger.warning("Queue export failed: %s", exc)
            self._status_label.setText(self._t("status.export_playlist.error", message=str(exc)))
            return

        self._status_label.setText(
            self._t("status.export_playlist.saved", path=str(path))
        )

    def _choose_queue_export_path(self) -> tuple[Path | None, str | None]:
        documents_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        initial_dir = Path(documents_dir) if documents_dir else Path.home()
        default_name = f"plex-music-player-playlist-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        filters = [
            ("json", "JSON Files (*.json)"),
            ("csv", "CSV Files (*.csv)"),
            ("txt", "Text Files (*.txt)"),
        ]
        filter_string = ";;".join(label for _, label in filters)
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            self._t("dialog.export_playlist.title"),
            str(initial_dir / default_name),
            filter_string,
            filters[0][1],
        )
        if not path_str:
            return None, None
        chosen_format = next(
            (
                extension
                for extension, label in filters
                if label == selected_filter
            ),
            "json",
        )
        path = Path(path_str)
        if path.suffix.lower() != f".{chosen_format}":
            path = path.with_suffix(f".{chosen_format}")
        return path, chosen_format

    def _serialize_queue_export(
        self,
        queue_items: tuple[QueueItem, ...],
        export_format: str,
    ) -> str:
        rows = [
            {
                "artist": ", ".join(queue_item.track.artists),
                "album": queue_item.track.album_title or "",
                "track": display_track_title(queue_item.track),
                "link": self._track_share_link(queue_item.track) or "",
            }
            for queue_item in queue_items
        ]
        if export_format == "json":
            return json.dumps(rows, ensure_ascii=False, indent=2)
        if export_format == "csv":
            output = StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["artist", "album", "track", "link"],
            )
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()
        if export_format == "txt":
            header = "artist | album | track | link"
            lines = [
                " | ".join(
                    (
                        row["artist"],
                        row["album"],
                        row["track"],
                        row["link"],
                    )
                )
                for row in rows
            ]
            return "\n".join([header, *lines])
        raise ValueError(f"Unsupported export format: {export_format}")

    def _track_share_link(self, track: Track) -> str | None:
        del track
        return None

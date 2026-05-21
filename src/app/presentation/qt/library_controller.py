from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from app.application.error_presenter import user_facing_error_message
from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Album, Artist, CatalogSearchResults, Logger, Playlist, Station, Track
from app.domain.errors import DomainError
from app.presentation.qt.track_display import display_track_title


@dataclass(frozen=True, slots=True)
class BrowserTab:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class BrowserItem:
    kind: str
    title: str
    subtitle: str | None
    payload: object
    source_type: str | None = None
    source_id: str | None = None
    source_tracks: tuple[Track, ...] = ()
    source_index: int | None = None


@dataclass(frozen=True, slots=True)
class BrowserContent:
    title: str
    items: tuple[BrowserItem, ...]
    recent_searches: tuple[str, ...] = ()
    tabs: tuple[BrowserTab, ...] = ()
    active_tab: str | None = None
    search_query: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    source_tracks: tuple[Track, ...] = ()
    bulk_mode: str = "loaded_only"
    list_key: str | None = None
    has_more: bool = False
    is_loading: bool = False


@dataclass(frozen=True, slots=True)
class BrowserHistoryEntry:
    page: str
    payload: object | None = None
    active_tab: str | None = None
    search_query: str | None = None
    list_limit: int | None = None
    list_kind: str | None = None
    track_limit: int | None = None


@dataclass(frozen=True, slots=True)
class PagedSourceRequest:
    source_type: str
    source_id: str
    page_size: int
    load_page: Callable[[int, int], tuple[Track, ...]]


class _SearchWorker(QObject):
    search_ready = Signal(int, str, object)
    search_failed = Signal(int, str)

    def __init__(self, *, search_service: SearchService, logger: Logger) -> None:
        super().__init__()
        self._search_service = search_service
        self._logger = logger

    @Slot(int, str)
    def run_search(self, request_id: int, query: str) -> None:
        try:
            results = self._search_service.search_catalog(query)
        except DomainError as exc:
            self._logger.warning("Library search failed: %s", exc)
            self.search_failed.emit(request_id, user_facing_error_message(exc))
            return
        self.search_ready.emit(request_id, query, results)


class LibraryController(QObject):
    _BROWSER_PAGE_SIZE = 40

    content_changed = Signal(object)
    content_failed = Signal(str)
    track_liked = Signal(object)
    track_unliked = Signal(object)
    album_liked = Signal(object)
    album_unliked = Signal(object)
    artist_liked = Signal(object)
    artist_unliked = Signal(object)
    playlist_liked = Signal(object)
    playlist_unliked = Signal(object)
    _search_requested = Signal(int, str)
    _content_ready = Signal(int, object)
    _content_failed_async = Signal(int, str)

    def __init__(
        self,
        *,
        search_service: SearchService,
        library_service: LibraryService,
        logger: Logger,
        translate: Callable[..., str],
    ) -> None:
        super().__init__()
        self._search_service = search_service
        self._library_service = library_service
        self._logger = logger
        self._t = translate
        self._last_search_query: str | None = None
        self._last_search_results: CatalogSearchResults | None = None
        self._active_search_tab = "tracks"
        self._active_artist_tab = "top_tracks"
        self._active_page: tuple[str, object | None] = ("search", None)
        self._active_list_kind: str | None = None
        self._search_tracks_limit = 50
        self._source_tracks_limit = self._BROWSER_PAGE_SIZE
        self._liked_tracks_limit = self._BROWSER_PAGE_SIZE
        self._liked_albums_limit = self._BROWSER_PAGE_SIZE
        self._liked_artists_limit = self._BROWSER_PAGE_SIZE
        self._playlists_limit = self._BROWSER_PAGE_SIZE
        self._history: list[BrowserHistoryEntry] = []
        self._current_content: BrowserContent | None = None
        self._search_request_id = 0
        self._content_request_id = 0
        self._append_request_ids: set[int] = set()
        self._search_thread = QThread(self)
        self._search_worker = _SearchWorker(
            search_service=search_service,
            logger=logger,
        )
        self._search_worker.moveToThread(self._search_thread)
        self._search_requested.connect(
            self._search_worker.run_search,
            Qt.ConnectionType.QueuedConnection,
        )
        self._search_worker.search_ready.connect(self._handle_search_ready)
        self._search_worker.search_failed.connect(self._handle_search_failed)
        self._search_thread.finished.connect(self._search_worker.deleteLater)
        self._search_thread.start()
        self._content_ready.connect(self._handle_content_ready)
        self._content_failed_async.connect(self._handle_content_failed_async)

    def initialize(self) -> None:
        self._emit_content(self._empty_search_content(self._active_search_tab))

    def refresh_localized_content(self) -> None:
        page, payload = self._active_page
        if page == "search":
            if self._last_search_results is None or self._last_search_query is None:
                self._emit_content(self._empty_search_content(self._active_search_tab))
                return
            self._emit_content(
                self._search_content(
                    self._last_search_query,
                    tab=self._active_search_tab,
                    refresh=False,
                )
            )
            return
        if page == "artist" and isinstance(payload, Artist):
            self._dispatch_content_load(
                self._loading_artist_content(payload, tab=self._active_artist_tab),
                lambda: self._artist_content(payload, tab=self._active_artist_tab),
            )
            return
        if page == "source" and isinstance(payload, Playlist):
            self._dispatch_content_load(
                self._loading_source_content(title=payload.title),
                lambda: self._source_content(
                    title=payload.title,
                    source_type="playlist",
                    source_id=payload.id,
                    tracks=self._library_service.load_playlist_track_page(
                        payload.id,
                        owner_id=payload.owner_id,
                        offset=0,
                        limit=self._source_tracks_limit,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._source_tracks_limit,
                )
            )
            return
        if page == "source" and isinstance(payload, Album):
            self._dispatch_content_load(
                self._loading_source_content(title=payload.title),
                lambda: self._source_content(
                    title=payload.title,
                    source_type="album",
                    source_id=payload.id,
                    tracks=self._library_service.load_album_track_page(
                        payload.id,
                        offset=0,
                        limit=self._source_tracks_limit,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._source_tracks_limit,
                )
            )
            return
        if page == "source" and isinstance(payload, Station):
            self._dispatch_content_load(
                self._loading_source_content(title=self._station_title(payload)),
                lambda: self._source_content(
                    title=self._station_title(payload),
                    source_type="station",
                    source_id=payload.id,
                    tracks=self._library_service.load_station_tracks(payload.id),
                )
            )
            return
        if page == "list":
            if self._active_list_kind == "liked_tracks":
                self._execute(lambda: self._liked_tracks_content(limit=self._liked_tracks_limit))
                return
            if self._active_list_kind == "liked_albums":
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.my_albums"),
                        list_key="liked_albums",
                    ),
                    lambda: self._liked_albums_content(limit=self._liked_albums_limit),
                )
                return
            if self._active_list_kind == "liked_artists":
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.my_artists"),
                        list_key="liked_artists",
                    ),
                    lambda: self._liked_artists_content(limit=self._liked_artists_limit),
                )
                return
            if self._active_list_kind == "playlists":
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.playlists"),
                        list_key="playlists",
                    ),
                    lambda: BrowserContent(
                        title=self._t("library.list.playlists"),
                        items=(
                            *self._playlist_items(
                                self._library_service.load_generated_playlists(),
                                kind="generated_playlist",
                            ),
                            *self._playlist_items(
                                self._unique_playlists(
                                    self._library_service.load_liked_playlists(),
                                    self._library_service.load_user_playlists(),
                                ),
                                kind="playlist",
                            ),
                        ),
                        recent_searches=self.recent_searches(),
                        list_key="playlists",
                    )
                )

    def shutdown(self) -> None:
        self._search_thread.quit()
        self._search_thread.wait(3000)

    def recent_searches(self) -> tuple[str, ...]:
        return self._search_service.load_recent_searches()

    def load_full_current_source_tracks(self) -> tuple[tuple[Track, ...], str, str] | None:
        page, payload = self._active_page
        if page == "list" and self._active_list_kind == "liked_tracks":
            return (
                self._library_service.load_all_liked_tracks(),
                "collection",
                "liked_tracks",
            )
        if page == "list" and self._active_list_kind == "liked_albums":
            return (
                self._library_service.load_all_liked_album_tracks(),
                "collection",
                "liked_albums",
            )
        if page == "list" and self._active_list_kind == "liked_artists":
            return (
                self._library_service.load_all_liked_artist_album_tracks(),
                "collection",
                "liked_artists_albums",
            )
        if page == "source" and isinstance(payload, Playlist):
            return (
                self._library_service.load_all_playlist_tracks(
                    payload.id,
                    owner_id=payload.owner_id,
                ),
                "playlist",
                payload.id,
            )
        if page == "source" and isinstance(payload, Album):
            return (
                self._library_service.load_all_album_tracks(payload.id),
                "album",
                payload.id,
            )
        if (
            page == "artist"
            and isinstance(payload, Artist)
            and self._active_artist_tab == "top_tracks"
        ):
            return (
                self._library_service.load_all_artist_tracks(payload.id),
                "artist",
                payload.id,
            )
        if (
            page == "artist"
            and isinstance(payload, Artist)
            and self._active_artist_tab == "albums"
        ):
            return (
                self._library_service.load_artist_album_tracks(
                    payload.id,
                    release_type=None,
                ),
                "artist",
                payload.id,
            )
        return None

    def resolve_current_source_paged_request(
        self,
        *,
        page_size: int,
    ) -> PagedSourceRequest | None:
        page, payload = self._active_page
        if page == "search" and self._active_search_tab == "tracks" and self._last_search_query:
            return PagedSourceRequest(
                source_type="search",
                source_id=self._last_search_query,
                page_size=page_size,
                load_page=lambda offset, limit, query=self._last_search_query: (
                    self._search_service.search_track_page(
                        query,
                        offset=offset,
                        limit=limit,
                    )
                ),
            )
        if page == "list" and self._active_list_kind == "liked_albums":
            return PagedSourceRequest(
                source_type="collection",
                source_id="liked_albums",
                page_size=page_size,
                load_page=lambda offset, limit: self._library_service.load_library_track_page(
                    offset=offset,
                    limit=limit,
                ),
            )
        if page == "list" and self._active_list_kind == "liked_tracks":
            return PagedSourceRequest(
                source_type="collection",
                source_id="liked_tracks",
                page_size=page_size,
                load_page=lambda offset, limit: self._library_service.load_liked_track_page(
                    offset=offset,
                    limit=limit,
                ),
            )
        if page == "list" and self._active_list_kind == "liked_artists":
            return PagedSourceRequest(
                source_type="collection",
                source_id="liked_artists_albums",
                page_size=page_size,
                load_page=lambda offset, limit: self._library_service.load_library_track_page(
                    offset=offset,
                    limit=limit,
                ),
            )
        if page == "source" and isinstance(payload, Playlist):
            return PagedSourceRequest(
                source_type="playlist",
                source_id=payload.id,
                page_size=page_size,
                load_page=lambda offset, limit, playlist_id=payload.id, owner_id=payload.owner_id: (
                    self._library_service.load_playlist_track_page(
                        playlist_id,
                        owner_id=owner_id,
                        offset=offset,
                        limit=limit,
                    )
                ),
            )
        if page == "source" and isinstance(payload, Album):
            return PagedSourceRequest(
                source_type="album",
                source_id=payload.id,
                page_size=page_size,
                load_page=lambda offset, limit, album_id=payload.id: (
                    self._library_service.load_album_track_page(
                        album_id,
                        offset=offset,
                        limit=limit,
                    )
                ),
            )
        if (
            page == "artist"
            and isinstance(payload, Artist)
            and self._active_artist_tab == "albums"
        ):
            return PagedSourceRequest(
                source_type="artist",
                source_id=payload.id,
                page_size=page_size,
                load_page=lambda offset, limit, artist_id=payload.id: (
                    self._library_service.load_artist_track_page(
                        artist_id,
                        offset=offset,
                        limit=limit,
                    )
                ),
            )
        return None

    def show_search_page(self) -> None:
        if self._active_page != ("search", None):
            self._push_history()
        self._active_page = ("search", None)
        self._active_list_kind = None
        if self._last_search_results is None or self._last_search_query is None:
            self._emit_content(self._empty_search_content(self._active_search_tab))
            return
        self._execute(
            lambda: self._search_content(
                self._last_search_query or "",
                tab=self._active_search_tab,
                refresh=False,
            )
        )

    def search_tracks(self, query: str) -> None:
        normalized_query = query.strip()
        if self._active_page != ("search", None) or (
            self._last_search_query is not None
            and normalized_query
            and normalized_query != self._last_search_query
        ):
            self._push_history()
        if normalized_query != (self._last_search_query or ""):
            self._search_tracks_limit = 50
        self._active_page = ("search", None)
        self._active_list_kind = None
        self._dispatch_search(normalized_query)

    def show_browser_tab(self, tab: str) -> None:
        page, payload = self._active_page
        if page == "artist" and isinstance(payload, Artist):
            self._active_artist_tab = tab
            self._dispatch_content_load(
                self._loading_artist_content(payload, tab=tab),
                lambda: self._artist_content(payload, tab=tab),
            )
            return
        if page == "search":
            self._active_search_tab = tab
            if self._last_search_results is None or self._last_search_query is None:
                self._emit_content(self._empty_search_content(tab))
                return
            self._execute(
                lambda: self._search_content(
                    self._last_search_query or "",
                    tab=tab,
                    refresh=False,
                )
            )

    def load_liked_tracks(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_tracks"
        self._liked_tracks_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_list_content(
                title=self._t("library.list.my_tracks"),
                list_key="liked_tracks",
            ),
            lambda: self._liked_tracks_content(limit=self._liked_tracks_limit),
        )

    def load_more_current_list(self) -> None:
        page, payload = self._active_page
        if page == "search":
            if self._active_search_tab != "tracks" or not self._last_search_query:
                return
            offset = self._search_tracks_limit
            self._dispatch_content_append(
                lambda: self._search_content(
                    self._last_search_query or "",
                    tab=self._active_search_tab,
                    refresh=False,
                    offset=offset,
                    limit=50,
                    append=True,
                ),
            )
            self._search_tracks_limit += 50
            return
        if page == "source" and isinstance(payload, Playlist):
            offset = self._source_tracks_limit
            self._dispatch_content_append(
                lambda: self._source_content(
                    title=payload.title,
                    source_type="playlist",
                    source_id=payload.id,
                    tracks=self._library_service.load_playlist_track_page(
                        payload.id,
                        owner_id=payload.owner_id,
                        offset=offset,
                        limit=self._BROWSER_PAGE_SIZE,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._source_tracks_limit += self._BROWSER_PAGE_SIZE
            return
        if page == "source" and isinstance(payload, Album):
            offset = self._source_tracks_limit
            self._dispatch_content_append(
                lambda: self._source_content(
                    title=payload.title,
                    source_type="album",
                    source_id=payload.id,
                    tracks=self._library_service.load_album_track_page(
                        payload.id,
                        offset=offset,
                        limit=self._BROWSER_PAGE_SIZE,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._source_tracks_limit += self._BROWSER_PAGE_SIZE
            return
        if page != "list":
            return
        if self._active_list_kind == "liked_tracks":
            offset = self._liked_tracks_limit
            self._dispatch_content_append(
                lambda: self._liked_tracks_content(
                    offset=offset,
                    limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._liked_tracks_limit += self._BROWSER_PAGE_SIZE
            return
        if self._active_list_kind == "liked_albums":
            offset = self._liked_albums_limit
            self._dispatch_content_append(
                lambda: self._liked_albums_content(
                    offset=offset,
                    limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._liked_albums_limit += self._BROWSER_PAGE_SIZE
            return
        if self._active_list_kind == "liked_artists":
            offset = self._liked_artists_limit
            self._dispatch_content_append(
                lambda: self._liked_artists_content(
                    offset=offset,
                    limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._liked_artists_limit += self._BROWSER_PAGE_SIZE
            return
        if self._active_list_kind == "playlists":
            offset = self._playlists_limit
            self._dispatch_content_append(
                lambda: self._playlists_content(
                    offset=offset,
                    limit=self._BROWSER_PAGE_SIZE,
                ),
            )
            self._playlists_limit += self._BROWSER_PAGE_SIZE

    def load_liked_albums(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_albums"
        self._liked_albums_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_list_content(
                title=self._t("library.list.my_albums"),
                list_key="liked_albums",
            ),
            lambda: self._liked_albums_content(limit=self._liked_albums_limit),
        )

    def load_liked_artists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_artists"
        self._liked_artists_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_list_content(
                title=self._t("library.list.my_artists"),
                list_key="liked_artists",
            ),
            lambda: self._liked_artists_content(limit=self._liked_artists_limit),
        )

    def load_playlists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "playlists"
        self._playlists_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_list_content(
                title=self._t("library.list.playlists"),
                list_key="playlists",
            ),
            lambda: self._playlists_content(limit=self._playlists_limit),
        )

    def load_my_wave(self) -> None:
        self.open_station(Station(id="plex:random", title=self._t("nav.my_wave")))

    def open_playlist(self, playlist: Playlist) -> None:
        self._push_history()
        self._active_page = ("source", playlist)
        self._active_list_kind = None
        self._source_tracks_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_source_content(title=playlist.title, list_key="source_tracks"),
            lambda: self._source_content(
                title=playlist.title,
                source_type="playlist",
                source_id=playlist.id,
                tracks=self._library_service.load_playlist_track_page(
                    playlist.id,
                    owner_id=playlist.owner_id,
                    offset=0,
                    limit=self._source_tracks_limit,
                ),
                list_key="source_tracks",
                has_more=True,
                page_limit=self._source_tracks_limit,
            )
        )

    def open_album(self, album: Album) -> None:
        self._push_history()
        self._active_page = ("source", album)
        self._active_list_kind = None
        self._source_tracks_limit = self._BROWSER_PAGE_SIZE
        self._dispatch_content_load(
            self._loading_source_content(title=album.title, list_key="source_tracks"),
            lambda: self._source_content(
                title=album.title,
                source_type="album",
                source_id=album.id,
                tracks=self._library_service.load_album_track_page(
                    album.id,
                    offset=0,
                    limit=self._source_tracks_limit,
                ),
                list_key="source_tracks",
                has_more=True,
                page_limit=self._source_tracks_limit,
            )
        )

    def open_album_by_id(self, album_id: str) -> None:
        try:
            album = self._library_service.load_album(album_id)
        except DomainError as exc:
            self._logger.warning("Library operation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))
            return
        self.open_album(album)

    def open_station(self, station: Station) -> None:
        self._push_history()
        self._active_page = ("source", station)
        self._active_list_kind = None
        self._dispatch_content_load(
            self._loading_source_content(title=station.title),
            lambda: self._source_content(
                title=station.title,
                source_type="station",
                source_id=station.id,
                tracks=self._library_service.load_station_tracks(station.id),
            )
        )

    def open_artist(self, artist: Artist) -> None:
        self._push_history()
        self._active_page = ("artist", artist)
        self._active_artist_tab = "top_tracks"
        self._active_list_kind = None
        self._dispatch_content_load(
            self._loading_artist_content(artist, tab="top_tracks"),
            lambda: self._artist_content(artist, tab="top_tracks"),
        )

    def can_go_back(self) -> bool:
        return bool(self._history)

    def go_back(self) -> None:
        if not self._history:
            return
        entry = self._history.pop()
        self._restore_history_entry(entry)

    def like_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_liked.emit(self._library_service.like_track(track))
        )

    def unlike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_unliked.emit(self._library_service.unlike_track(track))
        )

    def like_album(self, album: Album) -> None:
        self._execute_mutation(
            lambda: self.album_liked.emit(self._library_service.like_album(album))
        )

    def unlike_album(self, album: Album) -> None:
        self._execute_mutation(
            lambda: self.album_unliked.emit(self._library_service.unlike_album(album))
        )

    def like_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self.artist_liked.emit(self._library_service.like_artist(artist))
        )

    def unlike_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self.artist_unliked.emit(self._library_service.unlike_artist(artist))
        )

    def like_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self.playlist_liked.emit(self._library_service.like_playlist(playlist))
        )

    def unlike_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self.playlist_unliked.emit(self._library_service.unlike_playlist(playlist))
        )

    def _execute(self, operation) -> None:
        try:
            self._emit_content(operation())
        except DomainError as exc:
            self._logger.warning("Library operation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))

    def _execute_mutation(self, operation) -> None:
        try:
            operation()
        except DomainError as exc:
            self._logger.warning("Library mutation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))

    def _emit_content(self, content: BrowserContent) -> None:
        self._current_content = content
        self.content_changed.emit(content)

    def _dispatch_content_load(self, loading_content: BrowserContent, operation) -> None:
        self._content_request_id += 1
        request_id = self._content_request_id
        self._emit_content(loading_content)

        def _runner() -> None:
            try:
                content = operation()
            except DomainError as exc:
                self._logger.warning("Library operation failed: %s", exc)
                self._content_failed_async.emit(
                    request_id,
                    user_facing_error_message(exc),
                )
                return
            self._content_ready.emit(request_id, content)

        threading.Thread(
            target=_runner,
            name=f"library-content-{request_id}",
            daemon=True,
        ).start()

    def _dispatch_content_append(self, operation) -> None:
        self._content_request_id += 1
        request_id = self._content_request_id
        self._append_request_ids.add(request_id)

        def _runner() -> None:
            try:
                content = operation()
            except DomainError as exc:
                self._logger.warning("Library operation failed: %s", exc)
                self._content_failed_async.emit(
                    request_id,
                    user_facing_error_message(exc),
                )
                return
            self._content_ready.emit(request_id, content)

        threading.Thread(
            target=_runner,
            name=f"library-content-append-{request_id}",
            daemon=True,
        ).start()

    def _push_history(self) -> None:
        entry = self._current_history_entry()
        if entry is None:
            return
        self._history.append(entry)

    def _current_history_entry(self) -> BrowserHistoryEntry | None:
        page, payload = self._active_page
        if page == "search":
            track_limit = (
                self._search_tracks_limit if self._active_search_tab == "tracks" else None
            )
            return BrowserHistoryEntry(
                page="search",
                active_tab=self._active_search_tab,
                search_query=self._last_search_query,
                track_limit=track_limit,
            )
        if page == "artist" and isinstance(payload, Artist):
            return BrowserHistoryEntry(
                page="artist",
                payload=payload,
                active_tab=self._active_artist_tab,
            )
        if page == "source" and isinstance(payload, (Album, Playlist, Station)):
            track_limit = (
                self._source_tracks_limit
                if isinstance(payload, (Album, Playlist))
                else None
            )
            return BrowserHistoryEntry(
                page="source",
                payload=payload,
                track_limit=track_limit,
            )
        if page == "list":
            list_limit = None
            if self._active_list_kind == "liked_tracks":
                list_limit = self._liked_tracks_limit
            if self._active_list_kind == "liked_albums":
                list_limit = self._liked_albums_limit
            if self._active_list_kind == "liked_artists":
                list_limit = self._liked_artists_limit
            if self._active_list_kind == "playlists":
                list_limit = self._playlists_limit
            return BrowserHistoryEntry(
                page="list",
                list_kind=self._active_list_kind,
                list_limit=list_limit,
            )
        return None

    def _restore_history_entry(self, entry: BrowserHistoryEntry) -> None:
        if entry.page == "search":
            self._active_page = ("search", None)
            self._active_list_kind = None
            self._active_search_tab = entry.active_tab or "tracks"
            self._search_tracks_limit = entry.track_limit or 50
            if entry.search_query:
                self._dispatch_search(entry.search_query or "")
                return
            self._emit_content(self._empty_search_content(self._active_search_tab))
            return
        if entry.page == "artist" and isinstance(entry.payload, Artist):
            self._active_page = ("artist", entry.payload)
            self._active_list_kind = None
            self._active_artist_tab = entry.active_tab or "top_tracks"
            self._dispatch_content_load(
                self._loading_artist_content(entry.payload, tab=self._active_artist_tab),
                lambda: self._artist_content(entry.payload, tab=self._active_artist_tab)
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Playlist):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._source_tracks_limit = entry.track_limit or self._BROWSER_PAGE_SIZE
            self._dispatch_content_load(
                self._loading_source_content(title=entry.payload.title, list_key="source_tracks"),
                lambda: self._source_content(
                    title=entry.payload.title,
                    source_type="playlist",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_playlist_track_page(
                        entry.payload.id,
                        owner_id=entry.payload.owner_id,
                        offset=0,
                        limit=self._source_tracks_limit,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._source_tracks_limit,
                )
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Album):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._source_tracks_limit = entry.track_limit or self._BROWSER_PAGE_SIZE
            self._dispatch_content_load(
                self._loading_source_content(title=entry.payload.title, list_key="source_tracks"),
                lambda: self._source_content(
                    title=entry.payload.title,
                    source_type="album",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_album_track_page(
                        entry.payload.id,
                        offset=0,
                        limit=self._source_tracks_limit,
                    ),
                    list_key="source_tracks",
                    has_more=True,
                    page_limit=self._source_tracks_limit,
                )
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Station):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._dispatch_content_load(
                self._loading_source_content(title=self._station_title(entry.payload)),
                lambda: self._source_content(
                    title=self._station_title(entry.payload),
                    source_type="station",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_station_tracks(entry.payload.id),
                )
            )
            return
        if entry.page == "list":
            self._active_page = ("list", None)
            self._active_list_kind = entry.list_kind
            if entry.list_kind == "liked_tracks":
                self._liked_tracks_limit = entry.list_limit or self._BROWSER_PAGE_SIZE
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.my_tracks"),
                        list_key="liked_tracks",
                    ),
                    lambda: self._liked_tracks_content(limit=self._liked_tracks_limit),
                )
                return
            if entry.list_kind == "liked_albums":
                self._liked_albums_limit = entry.list_limit or self._BROWSER_PAGE_SIZE
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.my_albums"),
                        list_key="liked_albums",
                    ),
                    lambda: self._liked_albums_content(limit=self._liked_albums_limit),
                )
                return
            if entry.list_kind == "liked_artists":
                self._liked_artists_limit = entry.list_limit or self._BROWSER_PAGE_SIZE
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.my_artists"),
                        list_key="liked_artists",
                    ),
                    lambda: self._liked_artists_content(limit=self._liked_artists_limit),
                )
                return
            if entry.list_kind == "playlists":
                self._playlists_limit = entry.list_limit or self._BROWSER_PAGE_SIZE
                self._dispatch_content_load(
                    self._loading_list_content(
                        title=self._t("library.list.playlists"),
                        list_key="playlists",
                    ),
                    lambda: self._playlists_content(limit=self._playlists_limit),
                )
                return

    def _search_content(
        self,
        query: str,
        *,
        tab: str,
        refresh: bool,
        offset: int = 0,
        limit: int | None = None,
        append: bool = False,
    ) -> BrowserContent:
        normalized_query = query.strip()
        if refresh or self._last_search_results is None:
            self._last_search_query = normalized_query
            self._last_search_results = self._search_service.search_catalog(normalized_query)

        results = self._last_search_results or CatalogSearchResults()
        is_track_tab = tab == "tracks"
        page_limit = limit or self._search_tracks_limit
        track_results = (
            self._search_service.search_track_page(
                normalized_query,
                offset=offset,
                limit=page_limit,
            )
            if is_track_tab and normalized_query
            else results.tracks
        )
        track_source_id = normalized_query or "search"
        title = (
            self._t("library.search_title", query=normalized_query)
            if normalized_query
            else self._t("library.search")
        )
        return BrowserContent(
            title=f"{title} | {self._search_tab_title(tab)}",
            items=self._search_tab_items(
                results,
                tab=tab,
                query=normalized_query,
                tracks=track_results,
            ),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=normalized_query,
            source_type="search" if is_track_tab and track_results else None,
            source_id=track_source_id if is_track_tab and track_results else None,
            source_tracks=track_results if is_track_tab else (),
            bulk_mode=(
                "loaded_only"
                if append
                else "stream_pages" if is_track_tab and normalized_query else "loaded_only"
            ),
            list_key="search_tracks" if is_track_tab and normalized_query else None,
            has_more=(
                len(track_results) >= page_limit
                if is_track_tab and normalized_query
                else False
            ),
        )

    def _empty_search_content(self, tab: str) -> BrowserContent:
        return BrowserContent(
            title=f"{self._t('library.search')} | {self._search_tab_title(tab)}",
            items=(),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=self._last_search_query,
            bulk_mode="loaded_only",
        )

    def _loading_search_content(self, query: str, tab: str) -> BrowserContent:
        normalized_query = query.strip()
        title = (
            self._t("library.search_title", query=normalized_query)
            if normalized_query
            else self._t("library.search")
        )
        return BrowserContent(
            title=f"{title} | {self._search_tab_title(tab)}",
            items=(),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=normalized_query,
            bulk_mode="loaded_only",
            is_loading=True,
        )

    def _dispatch_search(self, query: str) -> None:
        normalized_query = query.strip()
        self._search_request_id += 1
        request_id = self._search_request_id
        self._emit_content(
            self._loading_search_content(normalized_query, self._active_search_tab)
        )
        self._search_requested.emit(request_id, normalized_query)

    def _handle_search_ready(
        self,
        request_id: int,
        query: str,
        results: CatalogSearchResults,
    ) -> None:
        if request_id != self._search_request_id:
            return
        self._last_search_query = query
        self._last_search_results = results
        if self._active_page != ("search", None):
            return
        self._emit_content(
            self._search_content(
                query,
                tab=self._active_search_tab,
                refresh=False,
            )
        )

    def _handle_search_failed(self, request_id: int, message: str) -> None:
        if request_id != self._search_request_id:
            return
        self.content_failed.emit(message)

    def _handle_content_ready(self, request_id: int, content: BrowserContent) -> None:
        if request_id != self._content_request_id:
            return
        if request_id in self._append_request_ids:
            self._append_request_ids.discard(request_id)
            self._emit_content(self._merge_content(content))
            return
        self._emit_content(content)

    def _handle_content_failed_async(self, request_id: int, message: str) -> None:
        if request_id != self._content_request_id:
            return
        self._append_request_ids.discard(request_id)
        self.content_failed.emit(message)

    def _merge_content(self, new_content: BrowserContent) -> BrowserContent:
        current = self._current_content
        if current is None or current.list_key != new_content.list_key:
            return new_content
        return BrowserContent(
            title=new_content.title,
            items=(*current.items, *new_content.items),
            recent_searches=new_content.recent_searches,
            tabs=new_content.tabs,
            active_tab=new_content.active_tab,
            search_query=new_content.search_query,
            source_type=new_content.source_type or current.source_type,
            source_id=new_content.source_id or current.source_id,
            source_tracks=(*current.source_tracks, *new_content.source_tracks),
            bulk_mode=current.bulk_mode,
            list_key=new_content.list_key,
            has_more=new_content.has_more,
            is_loading=False,
        )

    def _artist_content(self, artist: Artist, *, tab: str) -> BrowserContent:
        if tab == "albums":
            albums = self._artist_albums(artist.id, release_type=None)
            return BrowserContent(
                title=self._t("library.artist_albums_title", name=artist.name),
                items=self._album_items(albums),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                source_type="artist",
                source_id=artist.id,
                bulk_mode="stream_pages",
            )
        if tab == "singles":
            return BrowserContent(
                title=self._t("library.artist_singles_title", name=artist.name),
                items=self._album_items(self._artist_albums(artist.id, release_type="single")),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        if tab == "compilations":
            return BrowserContent(
                title=self._t("library.artist_compilations_title", name=artist.name),
                items=self._album_items(
                    self._library_service.load_artist_compilation_albums(artist.id)
                ),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        tracks = self._library_service.load_artist_tracks(artist.id)
        return BrowserContent(
            title=self._t("library.artist_top_tracks_title", name=artist.name),
            items=self._track_items(
                tracks,
                source_type="artist",
                source_id=artist.id,
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            tabs=self._artist_tabs(),
            active_tab="top_tracks",
            source_type="artist",
            source_id=artist.id,
            source_tracks=tracks,
            bulk_mode="load_all",
        )

    def _source_content(
        self,
        *,
        title: str,
        source_type: str,
        source_id: str,
        tracks: tuple[Track, ...],
        list_key: str | None = None,
        has_more: bool = False,
        page_limit: int | None = None,
    ) -> BrowserContent:
        bulk_mode = (
            "loaded_only"
            if source_type == "station"
            else "stream_pages" if list_key == "source_tracks" else "load_all"
        )
        effective_page_limit = page_limit or self._source_tracks_limit
        return BrowserContent(
            title=title,
            items=self._track_items(
                tracks,
                source_type=source_type,
                source_id=source_id,
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            source_type=source_type,
            source_id=source_id,
            source_tracks=tracks,
            bulk_mode=bulk_mode,
            list_key=list_key,
            has_more=has_more and len(tracks) >= effective_page_limit,
        )

    def _liked_tracks_content(self, *, limit: int, offset: int = 0) -> BrowserContent:
        tracks = self._library_service.load_liked_track_page(offset=offset, limit=limit)
        return BrowserContent(
            title=self._t("library.list.my_tracks"),
            items=self._track_items(
                tracks,
                source_type="collection",
                source_id="liked_tracks",
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            source_type="collection",
            source_id="liked_tracks",
            source_tracks=tracks,
            bulk_mode="stream_pages",
            list_key="liked_tracks",
            has_more=len(tracks) >= limit,
        )

    def _liked_albums_content(self, *, limit: int, offset: int = 0) -> BrowserContent:
        albums = self._library_service.load_liked_album_page(offset=offset, limit=limit)
        return BrowserContent(
            title=self._t("library.list.my_albums"),
            items=self._album_items(albums),
            recent_searches=self.recent_searches(),
            source_type="collection",
            source_id="liked_albums",
            bulk_mode="stream_pages",
            list_key="liked_albums",
            has_more=len(albums) >= limit,
        )

    def _liked_artists_content(self, *, limit: int, offset: int = 0) -> BrowserContent:
        artists = self._library_service.load_liked_artist_page(offset=offset, limit=limit)
        return BrowserContent(
            title=self._t("library.list.my_artists"),
            items=self._artist_items(artists),
            recent_searches=self.recent_searches(),
            source_type="collection",
            source_id="liked_artists_albums",
            bulk_mode="stream_pages",
            list_key="liked_artists",
            has_more=len(artists) >= limit,
        )

    def _playlists_content(self, *, limit: int, offset: int = 0) -> BrowserContent:
        generated = self._library_service.load_generated_playlists()
        playlists = self._library_service.load_liked_playlist_page(offset=offset, limit=limit)
        return BrowserContent(
            title=self._t("library.list.playlists"),
            items=(
                *self._playlist_items(generated if offset == 0 else (), kind="generated_playlist"),
                *self._playlist_items(playlists, kind="playlist"),
            ),
            recent_searches=self.recent_searches(),
            list_key="playlists",
            has_more=len(playlists) >= limit,
        )

    def _loading_list_content(self, *, title: str, list_key: str) -> BrowserContent:
        return BrowserContent(
            title=title,
            items=(),
            recent_searches=self.recent_searches(),
            list_key=list_key,
            is_loading=True,
        )

    def _loading_source_content(self, *, title: str, list_key: str | None = None) -> BrowserContent:
        return BrowserContent(
            title=title,
            items=(),
            recent_searches=self.recent_searches(),
            list_key=list_key,
            is_loading=True,
        )

    def _loading_artist_content(self, artist: Artist, *, tab: str) -> BrowserContent:
        return BrowserContent(
            title=self._t("library.artist_top_tracks_title", name=artist.name),
            items=(),
            recent_searches=self.recent_searches(),
            tabs=self._artist_tabs(),
            active_tab=tab,
            is_loading=True,
        )

    def _track_items(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        source_tracks: tuple[Track, ...] = (),
    ) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="track",
                title=display_track_title(track),
                subtitle=self._track_subtitle(track, source_type=source_type),
                payload=track,
                source_type=source_type,
                source_id=source_id,
                source_tracks=source_tracks,
                source_index=index if source_tracks else None,
            )
            for index, track in enumerate(tracks)
        )

    def _search_tab_items(
        self,
        results: CatalogSearchResults,
        *,
        tab: str,
        query: str,
        tracks: tuple[Track, ...] | None = None,
    ) -> tuple[BrowserItem, ...]:
        if tab == "albums":
            return self._album_items(results.albums)
        if tab == "playlists":
            return self._playlist_items(results.playlists, kind="playlist")
        if tab == "artists":
            return self._artist_items(results.artists)
        track_items = tracks if tracks is not None else results.tracks
        return self._track_items(
            track_items,
            source_type="search",
            source_id=query or "search",
            source_tracks=track_items,
        )

    def _search_tab_title(self, tab: str) -> str:
        return {
            "albums": self._t("library.tab.albums"),
            "playlists": self._t("library.tab.playlists"),
            "artists": self._t("library.tab.artists"),
            "tracks": self._t("library.tab.tracks"),
        }.get(tab, self._t("library.tab.tracks"))

    def _search_tabs(self) -> tuple[BrowserTab, ...]:
        return (
            BrowserTab("tracks", self._t("library.tab.tracks")),
            BrowserTab("playlists", self._t("library.tab.playlists")),
            BrowserTab("albums", self._t("library.tab.albums")),
            BrowserTab("artists", self._t("library.tab.artists")),
        )

    def _artist_tabs(self) -> tuple[BrowserTab, ...]:
        return (
            BrowserTab("top_tracks", self._t("library.tab.top_tracks")),
            BrowserTab("albums", self._t("library.tab.albums")),
        )

    def _artist_albums(self, artist_id: str, *, release_type: str | None) -> tuple[Album, ...]:
        albums = self._library_service.load_artist_direct_albums(artist_id)
        if release_type is None:
            return tuple(album for album in albums if album.release_type != "single")
        return tuple(album for album in albums if album.release_type == release_type)

    def _album_items(self, albums: tuple[Album, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="album",
                title=album.title,
                subtitle=self._album_subtitle(album),
                payload=album,
            )
            for album in albums
        )

    def _artist_items(self, artists: tuple[Artist, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="artist",
                title=artist.name,
                subtitle=self._t("library.artist"),
                payload=artist,
            )
            for artist in artists
        )

    def _playlist_items(
        self,
        playlists: tuple[Playlist, ...],
        *,
        kind: str,
    ) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind=kind,
                title=playlist.title,
                subtitle=playlist.description or playlist.owner_name,
                payload=playlist,
            )
            for playlist in playlists
        )

    def _unique_playlists(self, *playlist_groups: tuple[Playlist, ...]) -> tuple[Playlist, ...]:
        seen: set[tuple[str | None, str]] = set()
        playlists: list[Playlist] = []
        for group in playlist_groups:
            for playlist in group:
                key = (playlist.owner_id, playlist.id)
                if key in seen:
                    continue
                seen.add(key)
                playlists.append(playlist)
        return tuple(playlists)

    def _station_items(self, stations: tuple[Station, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="station",
                title=station.title,
                subtitle=station.description,
                payload=station,
            )
            for station in stations
        )

    def _station_title(self, station: Station) -> str:
        if station.id == "plex:random":
            return self._t("nav.my_wave")
        return station.title

    def _track_subtitle(self, track: Track, *, source_type: str | None) -> str:
        parts: list[str] = []
        artists = ", ".join(track.artists)
        if artists:
            parts.append(artists)
        if track.album_title:
            parts.append(track.album_title)
        elif source_type == "station":
            parts.append(self._t("nav.my_wave"))
        return " | ".join(parts) or self._t("library.track")

    def _album_subtitle(self, album: Album) -> str | None:
        parts = [", ".join(album.artists)]
        if album.year is not None:
            parts.append(str(album.year))
        if album.track_count is not None:
            parts.append(self._t("library.track_count", count=album.track_count))
        return " | ".join(part for part in parts if part) or None

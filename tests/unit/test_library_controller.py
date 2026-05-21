from __future__ import annotations

from app.domain import Album, Artist, CatalogSearchResults, Playlist, Track
from app.presentation.qt.library_controller import LibraryController


class StubLogger:
    def debug(self, message: str, *args: object) -> None:
        return None

    def info(self, message: str, *args: object) -> None:
        return None

    def warning(self, message: str, *args: object) -> None:
        return None

    def error(self, message: str, *args: object) -> None:
        return None

    def exception(self, message: str, *args: object) -> None:
        return None


class StubSearchService:
    def load_recent_searches(self) -> tuple[str, ...]:
        return ()

    def search_catalog(self, query: str) -> CatalogSearchResults:
        return CatalogSearchResults()

    def search_track_page(self, query: str, *, offset: int, limit: int) -> tuple[Track, ...]:
        return (
            Track(
                id=f"search-{query or 'empty'}-{offset}-{limit}",
                title="Search Track",
                artists=(),
            ),
        )


class StubLibraryService:
    def __init__(self) -> None:
        self.all_liked_tracks = (
            Track(id="liked-1", title="Liked 1", artists=()),
            Track(id="liked-2", title="Liked 2", artists=()),
        )
        self.all_liked_album_tracks = (
            Track(id="liked-album-track-1", title="Liked Album Track 1", artists=()),
        )
        self.all_liked_artist_album_tracks = (
            Track(id="liked-artist-album-track-1", title="Liked Artist Album Track 1", artists=()),
        )
        self.full_playlist_tracks = (Track(id="playlist-1", title="Playlist 1", artists=()),)
        self.full_album_tracks = (Track(id="album-1", title="Album 1", artists=()),)
        self.full_artist_tracks = (Track(id="artist-1", title="Artist 1", artists=()),)
        self.artist_album_tracks = (
            Track(id="artist-album-track-1", title="Artist Album Track 1", artists=()),
        )

    def load_liked_tracks(self, *, limit: int = 100) -> tuple[Track, ...]:
        return self.all_liked_tracks[:limit]

    def load_liked_track_page(self, *, offset: int, limit: int) -> tuple[Track, ...]:
        return tuple(
            Track(id=f"liked-{index}", title=f"Liked {index}", artists=())
            for index in range(offset, offset + min(limit, 2))
        )

    def load_all_liked_tracks(self) -> tuple[Track, ...]:
        return self.all_liked_tracks

    def load_all_liked_album_tracks(self) -> tuple[Track, ...]:
        return self.all_liked_album_tracks

    def load_all_liked_artist_album_tracks(self) -> tuple[Track, ...]:
        return self.all_liked_artist_album_tracks

    def load_all_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        return self.full_playlist_tracks

    def load_all_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        return self.full_album_tracks

    def load_playlist_track_page(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        return (
            Track(id=f"{playlist_id}-{offset}-{limit}", title="Playlist Page Track", artists=()),
        )

    def load_album_track_page(
        self,
        album_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        return (
            Track(id=f"{album_id}-{offset}-{limit}", title="Album Page Track", artists=()),
        )

    def load_all_artist_tracks(self, artist_id: str) -> tuple[Track, ...]:
        return self.full_artist_tracks

    def load_artist_album_tracks(
        self,
        artist_id: str,
        *,
        release_type: str | None,
    ) -> tuple[Track, ...]:
        return self.artist_album_tracks

    def load_liked_albums(self, *, limit: int = 100):
        return ()

    def load_liked_album_page(self, *, offset: int, limit: int):
        return (Album(id=f"liked-album-{offset}-{limit}", title="Liked Album"),)

    def load_liked_artists(self, *, limit: int = 100):
        return ()

    def load_liked_artist_page(self, *, offset: int, limit: int):
        return (Artist(id=f"liked-artist-{offset}-{limit}", name="Liked Artist"),)

    def load_liked_playlist_page(self, *, offset: int, limit: int):
        return (
            Playlist(
                id=f"liked-playlist-{offset}-{limit}",
                title="Liked Playlist",
                owner_id="owner",
            ),
        )

    def load_library_track_page(self, *, offset: int, limit: int) -> tuple[Track, ...]:
        return (Track(id=f"library-{offset}-{limit}", title="Library Track", artists=()),)

    def load_artist_track_page(
        self,
        artist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        return (
            Track(
                id=f"{artist_id}-{offset}-{limit}",
                title="Artist Page Track",
                artists=(),
            ),
        )

    def load_artist_tracks(self, artist_id: str, *, limit: int = 50) -> tuple[Track, ...]:
        return self.full_artist_tracks[:limit]


def _translate(key: str, **params: object) -> str:
    return key.format(**params) if params else key


def test_liked_tracks_content_uses_stream_pages_bulk_mode() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    try:
        content = controller._liked_tracks_content(limit=1)
    finally:
        controller.shutdown()

    assert content.bulk_mode == "stream_pages"
    assert content.source_type == "collection"
    assert content.source_id == "liked_tracks"
    assert len(content.source_tracks) == 1


def test_liked_albums_content_uses_stream_pages_bulk_mode() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    try:
        content = controller._liked_albums_content(limit=1)
    finally:
        controller.shutdown()

    assert content.bulk_mode == "stream_pages"
    assert content.source_type == "collection"
    assert content.source_id == "liked_albums"


def test_search_tracks_content_uses_stream_pages_bulk_mode() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    controller._last_search_results = CatalogSearchResults()
    try:
        content = controller._search_content("query", tab="tracks", refresh=False)
    finally:
        controller.shutdown()

    assert content.bulk_mode == "stream_pages"
    assert content.source_type == "search"
    assert content.source_id == "query"
    assert len(content.source_tracks) == 1
    assert content.list_key == "search_tracks"


def test_source_content_marks_station_as_loaded_only() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    tracks = (Track(id="station-1", title="Station 1", artists=()),)
    try:
        content = controller._source_content(
            title="Station",
            source_type="station",
            source_id="station-id",
            tracks=tracks,
        )
    finally:
        controller.shutdown()

    assert content.bulk_mode == "loaded_only"
    assert content.source_tracks == tracks


def test_load_full_current_source_tracks_for_liked_tracks() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    controller._active_page = ("list", None)
    controller._active_list_kind = "liked_tracks"
    try:
        request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert request == (
        (
            Track(id="liked-1", title="Liked 1", artists=()),
            Track(id="liked-2", title="Liked 2", artists=()),
        ),
        "collection",
        "liked_tracks",
    )


def test_load_full_current_source_tracks_for_liked_albums_and_artists() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    try:
        controller._active_page = ("list", None)
        controller._active_list_kind = "liked_albums"
        liked_albums_request = controller.load_full_current_source_tracks()
        controller._active_list_kind = "liked_artists"
        liked_artists_request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert liked_albums_request == (
        (Track(id="liked-album-track-1", title="Liked Album Track 1", artists=()),),
        "collection",
        "liked_albums",
    )
    assert liked_artists_request == (
        (
            Track(
                id="liked-artist-album-track-1",
                title="Liked Artist Album Track 1",
                artists=(),
            ),
        ),
        "collection",
        "liked_artists_albums",
    )


def test_load_full_current_source_tracks_for_playlist_and_artist() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    playlist = Playlist(id="playlist-id", title="Playlist", owner_id="owner")
    artist = Artist(id="artist-id", name="Artist")
    try:
        controller._active_page = ("source", playlist)
        playlist_request = controller.load_full_current_source_tracks()
        controller._active_page = ("artist", artist)
        controller._active_artist_tab = "top_tracks"
        artist_request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert playlist_request == (
        (Track(id="playlist-1", title="Playlist 1", artists=()),),
        "playlist",
        "playlist-id",
    )
    assert artist_request == (
        (Track(id="artist-1", title="Artist 1", artists=()),),
        "artist",
        "artist-id",
    )


def test_load_full_current_source_tracks_for_artist_albums_tab() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    artist = Artist(id="artist-id", name="Artist")
    try:
        controller._active_page = ("artist", artist)
        controller._active_artist_tab = "albums"
        request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert request == (
        (Track(id="artist-album-track-1", title="Artist Album Track 1", artists=()),),
        "artist",
        "artist-id",
    )


def test_resolve_current_source_paged_request_for_track_heavy_sources() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    artist = Artist(id="artist-id", name="Artist")
    playlist = Playlist(id="playlist-id", title="Playlist", owner_id="owner")
    album = Album(id="album-id", title="Album")
    try:
        controller._active_page = ("list", None)
        controller._active_list_kind = "liked_tracks"
        liked_tracks_request = controller.resolve_current_source_paged_request(page_size=50)
        controller._active_list_kind = "liked_albums"
        liked_albums_request = controller.resolve_current_source_paged_request(page_size=50)
        controller._active_list_kind = "liked_artists"
        liked_artists_request = controller.resolve_current_source_paged_request(page_size=50)
        controller._active_page = ("source", playlist)
        playlist_request = controller.resolve_current_source_paged_request(page_size=50)
        controller._active_page = ("source", album)
        album_request = controller.resolve_current_source_paged_request(page_size=50)
        controller._active_page = ("artist", artist)
        controller._active_artist_tab = "albums"
        artist_request = controller.resolve_current_source_paged_request(page_size=50)
    finally:
        controller.shutdown()

    assert liked_tracks_request is not None
    assert liked_tracks_request.source_type == "collection"
    assert liked_tracks_request.source_id == "liked_tracks"
    assert liked_tracks_request.load_page(0, 50) == (
        Track(id="liked-0", title="Liked 0", artists=()),
        Track(id="liked-1", title="Liked 1", artists=()),
    )

    assert liked_albums_request is not None
    assert liked_albums_request.source_type == "collection"
    assert liked_albums_request.source_id == "liked_albums"
    assert liked_albums_request.load_page(0, 50) == (
        Track(id="library-0-50", title="Library Track", artists=()),
    )

    assert liked_artists_request is not None
    assert liked_artists_request.source_type == "collection"
    assert liked_artists_request.source_id == "liked_artists_albums"
    assert liked_artists_request.load_page(0, 50) == (
        Track(id="library-0-50", title="Library Track", artists=()),
    )

    assert playlist_request is not None
    assert playlist_request.source_type == "playlist"
    assert playlist_request.source_id == "playlist-id"
    assert playlist_request.load_page(0, 50) == (
        Track(id="playlist-id-0-50", title="Playlist Page Track", artists=()),
    )

    assert album_request is not None
    assert album_request.source_type == "album"
    assert album_request.source_id == "album-id"
    assert album_request.load_page(0, 50) == (
        Track(id="album-id-0-50", title="Album Page Track", artists=()),
    )

    assert artist_request is not None
    assert artist_request.source_type == "artist"
    assert artist_request.source_id == "artist-id"
    assert artist_request.load_page(50, 50) == (
        Track(id="artist-id-50-50", title="Artist Page Track", artists=()),
    )

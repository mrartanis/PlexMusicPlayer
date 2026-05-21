from __future__ import annotations

from app.application.track_metadata import merge_cached_liked_states
from app.domain import CatalogSearchResults, LibraryCacheRepo, Logger, MusicService, Track


class SearchService:
    def __init__(
        self,
        *,
        music_service: MusicService,
        library_cache_repo: LibraryCacheRepo,
        logger: Logger,
    ) -> None:
        self._music_service = music_service
        self._library_cache_repo = library_cache_repo
        self._logger = logger

    def search_tracks(self, query: str, *, limit: int = 25) -> tuple[Track, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            return ()

        tracks = merge_cached_liked_states(
            tuple(self._music_service.search_tracks(normalized_query, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._remember_recent_search(normalized_query)
        self._logger.info("Search returned %s tracks for query %s", len(tracks), normalized_query)
        return tracks

    def search_track_page(
        self,
        query: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            return ()

        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.search_track_page(
                    normalized_query,
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._remember_recent_search(normalized_query)
        self._logger.info(
            "Search returned %s track-page items for query %s at offset=%s limit=%s",
            len(tracks),
            normalized_query,
            offset,
            limit,
        )
        return tracks

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults:
        normalized_query = query.strip()
        if not normalized_query:
            return CatalogSearchResults()

        cached_results = self._library_cache_repo.load_catalog_search(normalized_query)
        cache_hit = cached_results is not None
        results = cached_results
        if results is None:
            results = self._music_service.search_catalog(normalized_query, limit=limit)
            results = self._with_artist_albums(results, limit=limit)
            self._library_cache_repo.save_catalog_search(normalized_query, results)
        results = CatalogSearchResults(
            tracks=merge_cached_liked_states(
                results.tracks,
                self._library_cache_repo,
                user_id=self._current_user_id(),
            ),
            albums=results.albums,
            singles=results.singles,
            compilations=results.compilations,
            artists=results.artists,
            playlists=results.playlists,
        )
        self._cache_tracks(results.tracks)
        self._remember_recent_search(normalized_query)
        self._logger.info(
            (
                "Search (%s) returned %s tracks, %s albums, %s singles, %s compilations, "
                "%s artists, %s playlists for query %s"
            ),
            "cache" if cache_hit else "remote",
            len(results.tracks),
            len(results.albums),
            len(results.singles),
            len(results.compilations),
            len(results.artists),
            len(results.playlists),
            normalized_query,
        )
        return results

    def _current_user_id(self) -> str | None:
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None

    def _with_artist_albums(
        self,
        results: CatalogSearchResults,
        *,
        limit: int,
    ) -> CatalogSearchResults:
        albums_by_id = {album.id: album for album in results.albums}
        singles_by_id = {album.id: album for album in results.singles}
        compilations_by_id = {album.id: album for album in results.compilations}
        for artist in results.artists[:3]:
            for album in self._music_service.get_artist_direct_albums(artist.id, limit=limit):
                self._add_album_to_bucket(
                    album,
                    albums_by_id=albums_by_id,
                    singles_by_id=singles_by_id,
                    compilations_by_id=compilations_by_id,
                )
            for album in self._music_service.get_artist_compilation_albums(
                artist.id,
                limit=limit,
            ):
                compilations_by_id.setdefault(album.id, album)
        return CatalogSearchResults(
            tracks=results.tracks,
            albums=tuple(albums_by_id.values()),
            singles=tuple(singles_by_id.values()),
            compilations=tuple(compilations_by_id.values()),
            artists=results.artists,
            playlists=results.playlists,
        )

    def _add_album_to_bucket(
        self,
        album,
        *,
        albums_by_id,
        singles_by_id,
        compilations_by_id,
    ) -> None:
        if album.release_type == "single":
            singles_by_id.setdefault(album.id, album)
            return
        if album.release_type == "compilation":
            compilations_by_id.setdefault(album.id, album)
            return
        albums_by_id.setdefault(album.id, album)

    def load_recent_searches(self) -> tuple[str, ...]:
        return tuple(self._library_cache_repo.load_recent_searches())

    def _remember_recent_search(self, query: str) -> None:
        current = [
            item for item in self._library_cache_repo.load_recent_searches() if item != query
        ]
        current.insert(0, query)
        self._library_cache_repo.save_recent_searches(tuple(current[:10]))

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            self._library_cache_repo.save_track_metadata(track)
            if track.artwork_ref:
                self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)

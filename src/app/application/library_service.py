from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.application.track_metadata import merge_cached_liked_states
from app.domain import (
    Album,
    Artist,
    LibraryCacheRepo,
    LikedTrackSnapshot,
    Logger,
    MusicService,
    Playlist,
    Station,
    Track,
)


class LibraryService:
    _BULK_LIKED_TRACK_LIMIT = 100_000
    _BULK_LIBRARY_TRACK_LIMIT = 100_000
    _BULK_ARTIST_TRACK_LIMIT = 1_000
    _BULK_LIBRARY_ENTITY_LIMIT = 10_000
    _BULK_FETCH_WORKERS = 8

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

    def load_liked_tracks(self, *, limit: int = 100) -> tuple[Track, ...]:
        user_id = self._current_user_id()
        cached_snapshot = (
            self._library_cache_repo.load_liked_track_snapshot(user_id)
            if user_id is not None
            else None
        )
        cached_tracks = cached_snapshot.tracks[:limit] if cached_snapshot is not None else ()
        current_revision = cached_snapshot.revision if cached_snapshot is not None else 0
        cached_liked_ids = (
            self._library_cache_repo.load_liked_track_ids(user_id)
            if user_id is not None
            else None
        )
        total_cached_tracks = len(cached_snapshot.tracks) if cached_snapshot is not None else 0
        total_known_tracks = (
            len(cached_liked_ids.track_ids) if cached_liked_ids is not None else total_cached_tracks
        )
        if user_id is None:
            tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
            self._cache_tracks(tracks)
            self._logger.info("Loaded %s liked tracks", len(tracks))
            return tracks

        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=current_revision
        )
        if (
            liked_tracks is None
            and cached_tracks
            and total_cached_tracks >= min(limit, total_known_tracks)
        ):
            self._logger.info(
                "Loaded %s liked tracks from cache at revision %s",
                len(cached_tracks),
                current_revision,
            )
            return cached_tracks

        tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
        self._cache_tracks(tracks)
        snapshot_revision = (
            liked_tracks.revision if liked_tracks is not None else current_revision
        )
        self._library_cache_repo.save_liked_track_snapshot(
            LikedTrackSnapshot(
                user_id=user_id,
                revision=snapshot_revision,
                tracks=tracks,
            )
        )
        if liked_tracks is not None:
            self._library_cache_repo.save_liked_track_ids(liked_tracks)
        self._logger.info("Loaded %s liked tracks", len(tracks))
        return tracks

    def load_all_liked_tracks(self) -> tuple[Track, ...]:
        user_id = self._current_user_id()
        cached_snapshot = (
            self._library_cache_repo.load_liked_track_snapshot(user_id)
            if user_id is not None
            else None
        )
        cached_liked_ids = (
            self._library_cache_repo.load_liked_track_ids(user_id)
            if user_id is not None
            else None
        )
        current_revision = cached_snapshot.revision if cached_snapshot is not None else 0

        if user_id is None:
            tracks = tuple(self._music_service.get_liked_tracks(limit=self._BULK_LIKED_TRACK_LIMIT))
            self._cache_tracks(tracks)
            self._logger.info("Loaded %s liked tracks for bulk playback", len(tracks))
            return tracks

        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=current_revision
        )
        if (
            liked_tracks is None
            and cached_snapshot is not None
            and cached_liked_ids is not None
            and len(cached_snapshot.tracks) >= len(cached_liked_ids.track_ids)
        ):
            self._logger.info(
                "Loaded %s liked tracks from cache for bulk playback at revision %s",
                len(cached_snapshot.tracks),
                current_revision,
            )
            return cached_snapshot.tracks

        total_tracks = len(liked_tracks.track_ids) if liked_tracks is not None else 0
        tracks = tuple(
            self._music_service.get_liked_tracks(
                limit=max(total_tracks, self._BULK_LIKED_TRACK_LIMIT),
            )
        )
        self._cache_tracks(tracks)
        snapshot_revision = liked_tracks.revision if liked_tracks is not None else current_revision
        self._library_cache_repo.save_liked_track_snapshot(
            LikedTrackSnapshot(
                user_id=user_id,
                revision=snapshot_revision,
                tracks=tracks,
            )
        )
        if liked_tracks is not None:
            self._library_cache_repo.save_liked_track_ids(liked_tracks)
        self._logger.info("Loaded %s liked tracks for bulk playback", len(tracks))
        return tracks

    def load_liked_track_page(self, *, offset: int, limit: int) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_liked_track_page(
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s liked tracks for page offset=%s limit=%s",
            len(tracks),
            offset,
            limit,
        )
        return tracks

    def load_all_library_tracks(self) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_library_tracks(
                    limit=self._BULK_LIBRARY_TRACK_LIMIT,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s library tracks for bulk playback", len(tracks))
        return tracks

    def load_library_track_page(self, *, offset: int, limit: int) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_library_track_page(
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s library tracks for page offset=%s limit=%s",
            len(tracks),
            offset,
            limit,
        )
        return tracks

    def refresh_liked_track_index(self, *, force: bool = False) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        cached_likes = self._library_cache_repo.load_liked_track_ids(user_id)
        revision = 0 if force or cached_likes is None else cached_likes.revision
        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=revision
        )
        if liked_tracks is None:
            self._logger.info("Liked track index is up to date at revision %s", revision)
            return
        self._library_cache_repo.save_liked_track_ids(liked_tracks)
        self._logger.info(
            "Refreshed liked track index: %s ids at revision %s",
            len(liked_tracks.track_ids),
            liked_tracks.revision,
        )

    def load_liked_albums(self, *, limit: int = 100) -> tuple[Album, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_liked_album_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached and len(cached) >= limit:
            return cached[:limit]
        albums = tuple(self._music_service.get_liked_albums(limit=limit))
        if user_id is not None:
            self._library_cache_repo.save_liked_album_snapshot(user_id, albums)
        self._logger.info("Loaded %s liked albums", len(albums))
        return albums

    def load_liked_album_page(self, *, offset: int, limit: int) -> tuple[Album, ...]:
        albums = tuple(
            self._music_service.get_liked_album_page(
                offset=offset,
                limit=limit,
            )
        )
        self._logger.info(
            "Loaded %s liked albums for page offset=%s limit=%s",
            len(albums),
            offset,
            limit,
        )
        return albums

    def load_liked_artists(self, *, limit: int = 100) -> tuple[Artist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_liked_artist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached and len(cached) >= limit:
            return cached[:limit]
        artists = tuple(self._music_service.get_liked_artists(limit=limit))
        if user_id is not None:
            self._library_cache_repo.save_liked_artist_snapshot(user_id, artists)
        self._logger.info("Loaded %s liked artists", len(artists))
        return artists

    def load_liked_artist_page(self, *, offset: int, limit: int) -> tuple[Artist, ...]:
        artists = tuple(
            self._music_service.get_liked_artist_page(
                offset=offset,
                limit=limit,
            )
        )
        self._logger.info(
            "Loaded %s liked artists for page offset=%s limit=%s",
            len(artists),
            offset,
            limit,
        )
        return artists

    def load_liked_playlists(self, *, limit: int = 100) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_liked_playlist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached and len(cached) >= limit:
            return cached[:limit]
        playlists = tuple(self._music_service.get_liked_playlists(limit=limit))
        if user_id is not None:
            self._library_cache_repo.save_liked_playlist_snapshot(user_id, playlists)
        self._logger.info("Loaded %s liked playlists", len(playlists))
        return playlists

    def load_liked_playlist_page(self, *, offset: int, limit: int) -> tuple[Playlist, ...]:
        playlists = tuple(
            self._music_service.get_liked_playlist_page(
                offset=offset,
                limit=limit,
            )
        )
        self._logger.info(
            "Loaded %s liked playlists for page offset=%s limit=%s",
            len(playlists),
            offset,
            limit,
        )
        return playlists

    def load_user_playlists(self) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_user_playlist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached:
            return cached
        playlists = tuple(self._music_service.get_user_playlists())
        if user_id is not None:
            self._library_cache_repo.save_user_playlist_snapshot(user_id, playlists)
        self._logger.info("Loaded %s user playlists", len(playlists))
        return playlists

    def load_generated_playlists(self) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cache_user_id = user_id or "__anonymous__"
        cached = tuple(
            self._library_cache_repo.load_generated_playlist_snapshot(cache_user_id) or ()
        )
        if cached:
            return cached
        playlists = tuple(self._music_service.get_generated_playlists())
        self._library_cache_repo.save_generated_playlist_snapshot(cache_user_id, playlists)
        self._logger.info("Loaded %s generated playlists", len(playlists))
        return playlists

    def load_stations(self) -> tuple[Station, ...]:
        stations = tuple(self._music_service.get_stations())
        self._logger.info("Loaded %s stations", len(stations))
        return stations

    def load_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_playlist_tracks(playlist_id, owner_id=owner_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for playlist %s", len(tracks), playlist_id)
        return tracks

    def load_playlist_track_page(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_playlist_track_page(
                    playlist_id,
                    owner_id=owner_id,
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s playlist tracks for %s at page offset=%s limit=%s",
            len(tracks),
            playlist_id,
            offset,
            limit,
        )
        return tracks

    def load_all_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        return self.load_playlist_tracks(playlist_id, owner_id=owner_id)

    def load_album(self, album_id: str) -> Album:
        album = self._music_service.get_album(album_id)
        self._logger.info("Loaded album %s", album_id)
        return album

    def load_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_album_tracks(album_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for album %s", len(tracks), album_id)
        return tracks

    def load_album_track_page(
        self,
        album_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_album_track_page(
                    album_id,
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s album tracks for %s at page offset=%s limit=%s",
            len(tracks),
            album_id,
            offset,
            limit,
        )
        return tracks

    def load_all_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        return self.load_album_tracks(album_id)

    def load_station_tracks(self, station_id: str, *, limit: int = 25) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_station_tracks(station_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s station tracks for %s", len(tracks), station_id)
        return tracks

    def load_artist_tracks(self, artist_id: str, *, limit: int = 50) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_artist_tracks(artist_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s artist tracks for %s", len(tracks), artist_id)
        return tracks

    def load_all_artist_tracks(self, artist_id: str) -> tuple[Track, ...]:
        return self.load_artist_tracks(artist_id, limit=self._BULK_ARTIST_TRACK_LIMIT)

    def load_artist_track_page(
        self,
        artist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_artist_track_page(
                    artist_id,
                    offset=offset,
                    limit=limit,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s artist tracks for %s at page offset=%s limit=%s",
            len(tracks),
            artist_id,
            offset,
            limit,
        )
        return tracks

    def load_all_liked_album_tracks(self) -> tuple[Track, ...]:
        albums = self.load_liked_albums(limit=self._BULK_LIBRARY_ENTITY_LIMIT)
        return self._load_tracks_for_albums(albums)

    def load_all_liked_artist_album_tracks(self) -> tuple[Track, ...]:
        return self.load_all_library_tracks()

    def load_artist_direct_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Album, ...]:
        albums = tuple(self._music_service.get_artist_direct_albums(artist_id, limit=limit))
        self._logger.info("Loaded %s direct artist albums for %s", len(albums), artist_id)
        return albums

    def load_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Album, ...]:
        albums = tuple(self._music_service.get_artist_compilation_albums(artist_id, limit=limit))
        self._logger.info("Loaded %s artist compilation albums for %s", len(albums), artist_id)
        return albums

    def load_artist_album_tracks(
        self,
        artist_id: str,
        *,
        release_type: str | None,
    ) -> tuple[Track, ...]:
        if release_type is None:
            return self.load_all_artist_tracks(artist_id)
        albums = self._artist_albums_for_bulk(artist_id, release_type=release_type)
        return self._load_tracks_for_albums(albums)

    def load_artist_playlists(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Playlist, ...]:
        playlists = tuple(self._music_service.get_artist_playlists(artist_id, limit=limit))
        self._logger.info("Loaded %s artist playlists for %s", len(playlists), artist_id)
        return playlists

    def like_track(self, track: Track) -> Track:
        self._music_service.like_track(track.id)
        liked_track = Track(
            id=track.id,
            title=track.title,
            artists=track.artists,
            version=track.version,
            artist_ids=track.artist_ids,
            album_id=track.album_id,
            album_title=track.album_title,
            album_year=track.album_year,
            duration_ms=track.duration_ms,
            stream_ref=track.stream_ref,
            stream_ref_cached_at=track.stream_ref_cached_at,
            artwork_ref=track.artwork_ref,
            accent_color=track.accent_color,
            available=track.available,
            is_liked=True,
        )
        self._cache_tracks((liked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_liked(user_id, track.id)
        self._logger.info("Liked track %s", track.id)
        return liked_track

    def unlike_track(self, track: Track) -> Track:
        self._music_service.unlike_track(track.id)
        unliked_track = Track(
            id=track.id,
            title=track.title,
            artists=track.artists,
            version=track.version,
            artist_ids=track.artist_ids,
            album_id=track.album_id,
            album_title=track.album_title,
            album_year=track.album_year,
            duration_ms=track.duration_ms,
            stream_ref=track.stream_ref,
            stream_ref_cached_at=track.stream_ref_cached_at,
            artwork_ref=track.artwork_ref,
            accent_color=track.accent_color,
            available=track.available,
            is_liked=False,
        )
        self._cache_tracks((unliked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_unliked(user_id, track.id)
        self._logger.info("Unliked track %s", track.id)
        return unliked_track

    def like_album(self, album: Album) -> Album:
        self._music_service.like_album(album.id)
        liked_album = Album(
            id=album.id,
            title=album.title,
            artists=album.artists,
            artist_ids=album.artist_ids,
            is_liked=True,
            release_type=album.release_type,
            year=album.year,
            track_count=album.track_count,
            artwork_ref=album.artwork_ref,
        )
        self._logger.info("Liked album %s", album.id)
        return liked_album

    def unlike_album(self, album: Album) -> Album:
        self._music_service.unlike_album(album.id)
        unliked_album = Album(
            id=album.id,
            title=album.title,
            artists=album.artists,
            artist_ids=album.artist_ids,
            is_liked=False,
            release_type=album.release_type,
            year=album.year,
            track_count=album.track_count,
            artwork_ref=album.artwork_ref,
        )
        self._logger.info("Unliked album %s", album.id)
        return unliked_album

    def like_artist(self, artist: Artist) -> Artist:
        self._music_service.like_artist(artist.id)
        liked_artist = Artist(
            id=artist.id,
            name=artist.name,
            artwork_ref=artist.artwork_ref,
            is_liked=True,
        )
        self._logger.info("Liked artist %s", artist.id)
        return liked_artist

    def unlike_artist(self, artist: Artist) -> Artist:
        self._music_service.unlike_artist(artist.id)
        unliked_artist = Artist(
            id=artist.id,
            name=artist.name,
            artwork_ref=artist.artwork_ref,
            is_liked=False,
        )
        self._logger.info("Unliked artist %s", artist.id)
        return unliked_artist

    def like_playlist(self, playlist: Playlist) -> Playlist:
        self._music_service.like_playlist(playlist.id, owner_id=playlist.owner_id)
        liked_playlist = Playlist(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            owner_name=playlist.owner_name,
            description=playlist.description,
            track_count=playlist.track_count,
            artwork_ref=playlist.artwork_ref,
            is_generated=playlist.is_generated,
            is_liked=True,
        )
        self._logger.info("Liked playlist %s", playlist.id)
        return liked_playlist

    def unlike_playlist(self, playlist: Playlist) -> Playlist:
        self._music_service.unlike_playlist(playlist.id, owner_id=playlist.owner_id)
        unliked_playlist = Playlist(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            owner_name=playlist.owner_name,
            description=playlist.description,
            track_count=playlist.track_count,
            artwork_ref=playlist.artwork_ref,
            is_generated=playlist.is_generated,
            is_liked=False,
        )
        self._logger.info("Unliked playlist %s", playlist.id)
        return unliked_playlist

    def cached_track(self, track_id: str) -> Track | None:
        return self._library_cache_repo.load_track_metadata(track_id)

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            self._library_cache_repo.save_track_metadata(track)
            if track.artwork_ref:
                self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)

    def _current_user_id(self) -> str | None:
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None

    def _artist_albums_for_bulk(
        self,
        artist_id: str,
        *,
        release_type: str | None,
    ) -> tuple[Album, ...]:
        albums = self.load_artist_direct_albums(
            artist_id,
            limit=self._BULK_LIBRARY_ENTITY_LIMIT,
        )
        if release_type is None:
            return tuple(album for album in albums if album.release_type != "single")
        return tuple(album for album in albums if album.release_type == release_type)

    def _load_tracks_for_albums(self, albums: tuple[Album, ...]) -> tuple[Track, ...]:
        with ThreadPoolExecutor(
            max_workers=self._BULK_FETCH_WORKERS,
            thread_name_prefix="library-bulk-albums",
        ) as executor:
            album_track_batches = tuple(
                executor.map(
                    lambda album: tuple(self._music_service.get_album_tracks(album.id)),
                    albums,
                )
            )
        raw_tracks: list[Track] = []
        for album_tracks in album_track_batches:
            raw_tracks.extend(album_tracks)
        tracks = merge_cached_liked_states(
            tuple(raw_tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info(
            "Loaded %s tracks across %s albums for bulk playback",
            len(tracks),
            len(albums),
        )
        return tracks

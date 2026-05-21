from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain import (
    Album,
    Artist,
    AudioQuality,
    AuthSession,
    CatalogSearchResults,
    LikedTrackIds,
    MusicService,
    PlayEventReport,
    Playlist,
    RadioFeedbackType,
    RadioSession,
    Station,
    StationTrackBatch,
    Track,
)
from app.domain.errors import AuthError, NetworkError, StreamResolveError, TrackUnavailableError


class PlexMusicService(MusicService):
    _RANDOM_STATION_ID = "plex:random"

    def __init__(
        self,
        *,
        session: AuthSession | None = None,
        logger: Any | None = None,
    ) -> None:
        self._session = session
        self._logger = logger
        self._audio_quality = AudioQuality.HQ
        self._server = None
        self._music_section = None
        self._track_total_size: int | None = None
        self._random = random.Random()

    def get_auth_session(self) -> AuthSession | None:
        return self._session

    def clear_auth_session(self) -> None:
        self._session = None
        self._server = None
        self._music_section = None
        self._track_total_size = None

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        return AuthSession(
            user_id="plex",
            token=token,
            expires_at=expires_at,
            display_name="Plex",
        )

    def apply_auth_session(self, session: AuthSession) -> None:
        self._session = session
        self._track_total_size = None
        self._connect_from_session(session)

    def available_music_sections(
        self,
        *,
        server_url: str,
        server_token: str,
    ) -> tuple[dict[str, str], ...]:
        server = self._connect(server_url, server_token)
        sections = []
        for section in server.library.sections():
            if getattr(section, "type", None) not in {"artist", "music"}:
                continue
            section_id = str(getattr(section, "key", getattr(section, "id", "")))
            sections.append({"id": section_id, "title": section.title})
        return tuple(sections)

    def build_authenticated_session(
        self,
        *,
        token: str,
        server_name: str,
        server_url: str,
        server_access_token: str,
        music_section_id: str,
        music_section_title: str,
    ) -> AuthSession:
        display_name = "Plex"
        try:
            from plexapi.myplex import MyPlexAccount

            account = MyPlexAccount(token=token)
            display_name = getattr(account, "username", None) or getattr(
                account, "title", "Plex"
            )
            user_id = str(getattr(account, "id", display_name))
        except Exception:  # noqa: BLE001
            user_id = "plex"

        session = AuthSession(
            user_id=user_id,
            token=token,
            display_name=display_name,
            server_name=server_name,
            server_url=server_url,
            server_access_token=server_access_token,
            music_section_id=music_section_id,
            music_section_title=music_section_title,
        )
        self.apply_auth_session(session)
        return session

    def get_track(self, track_id: str) -> Track:
        raw_track = self._fetch_item(track_id)
        return self._map_track(raw_track)

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return self.search_catalog(query, limit=limit).tracks

    def search_track_page(
        self,
        query: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        section = self._require_section()
        try:
            raw_tracks = section.search(
                query,
                libtype="track",
                container_start=offset,
                container_size=limit,
                maxresults=limit,
            )
        except Exception as exc:
            raise NetworkError(f"Failed to page Plex search for {query!r}") from exc
        return tuple(self._map_track(item) for item in raw_tracks)

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults:
        section = self._require_section()
        try:
            tracks = tuple(
                self._map_track(item)
                for item in section.search(query, libtype="track", limit=limit)
            )
            albums = tuple(
                self._map_album(item)
                for item in section.search(query, libtype="album", limit=limit)
            )
            artists = tuple(
                self._map_artist(item)
                for item in section.search(query, libtype="artist", limit=limit)
            )
            playlists = self.get_user_playlists()
        except Exception as exc:
            raise NetworkError(f"Failed to search Plex catalog for {query!r}") from exc
        filtered_playlists = tuple(
            playlist for playlist in playlists if query.lower() in playlist.title.lower()
        )[:limit]
        return CatalogSearchResults(
            tracks=tracks,
            albums=albums,
            artists=artists,
            playlists=filtered_playlists,
        )

    def get_library_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        return self._all_tracks(limit=limit)

    def get_library_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        section = self._require_section()
        raw_tracks = section.search(
            libtype="track",
            container_start=offset,
            container_size=limit,
            maxresults=limit,
        )
        return tuple(self._map_track(item) for item in raw_tracks)

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        tracks = [track for track in self._all_tracks(limit=0) if track.is_liked]
        return tuple(tracks[:limit])

    def get_liked_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        section = self._require_section()
        try:
            raw_tracks = section.search(
                libtype="track",
                container_start=offset,
                container_size=limit,
                maxresults=limit,
                filters={"userRating": 10},
            )
        except Exception as exc:
            raise NetworkError("Failed to page liked Plex tracks") from exc
        return tuple(self._map_track(item) for item in raw_tracks)

    def get_liked_track_ids(
        self,
        *,
        if_modified_since_revision: int = 0,
    ) -> LikedTrackIds | None:
        del if_modified_since_revision
        session = self._require_session()
        track_ids = frozenset(track.id for track in self.get_liked_tracks(limit=100_000))
        return LikedTrackIds(
            user_id=session.user_id,
            revision=len(track_ids),
            track_ids=track_ids,
        )

    def get_liked_albums(self, *, limit: int = 100) -> Sequence[Album]:
        section = self._require_section()
        return tuple(
            self._map_album(item) for item in section.search(libtype="album", limit=limit)
        )

    def get_liked_album_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Album]:
        section = self._require_section()
        return tuple(
            self._map_album(item)
            for item in section.search(
                libtype="album",
                container_start=offset,
                container_size=limit,
                maxresults=limit,
            )
        )

    def get_liked_artists(self, *, limit: int = 100) -> Sequence[Artist]:
        section = self._require_section()
        return tuple(
            self._map_artist(item) for item in section.search(libtype="artist", limit=limit)
        )

    def get_liked_artist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Artist]:
        section = self._require_section()
        return tuple(
            self._map_artist(item)
            for item in section.search(
                libtype="artist",
                container_start=offset,
                container_size=limit,
                maxresults=limit,
            )
        )

    def get_liked_playlists(self, *, limit: int = 100) -> Sequence[Playlist]:
        return self.get_user_playlists()[:limit]

    def get_liked_playlist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Playlist]:
        return self.get_user_playlists()[offset : offset + limit]

    def like_track(self, track_id: str) -> None:
        self._rate_track(track_id, 10)

    def unlike_track(self, track_id: str) -> None:
        self._rate_track(track_id, 0)

    def like_album(self, album_id: str) -> None:
        del album_id

    def unlike_album(self, album_id: str) -> None:
        del album_id

    def like_artist(self, artist_id: str) -> None:
        del artist_id

    def unlike_artist(self, artist_id: str) -> None:
        del artist_id

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        del playlist_id, owner_id

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        del playlist_id, owner_id

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self._audio_quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return self._audio_quality

    def get_user_playlists(self) -> Sequence[Playlist]:
        server = self._require_server()
        try:
            raw_playlists = server.playlists()
        except Exception as exc:
            raise NetworkError("Failed to load Plex playlists") from exc
        playlists = []
        for playlist in raw_playlists:
            if getattr(playlist, "playlistType", None) not in {None, "audio"}:
                continue
            playlists.append(self._map_playlist(playlist))
        return tuple(playlists)

    def get_generated_playlists(self) -> Sequence[Playlist]:
        return ()

    def get_stations(self) -> Sequence[Station]:
        return (Station(id=self._RANDOM_STATION_ID, title="Random Mix"),)

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]:
        return self.start_radio_session(station_id, limit=limit).tracks

    def get_station_track_batch(
        self,
        station_id: str,
        *,
        limit: int = 25,
        queue_track_id: str | None = None,
    ) -> StationTrackBatch:
        del queue_track_id
        session = self.start_radio_session(station_id, limit=limit)
        return StationTrackBatch(
            station_id=station_id,
            batch_id=session.batch_id,
            tracks=session.tracks,
        )

    def start_radio_session(
        self,
        station_id: str,
        *,
        limit: int = 25,
    ) -> RadioSession:
        if station_id != self._RANDOM_STATION_ID:
            raise TrackUnavailableError(f"Unsupported Plex station {station_id}")
        tracks = self._random_track_window(limit=limit)
        return RadioSession(
            station_id=station_id,
            session_id=f"{station_id}-session",
            batch_id=f"{station_id}-{datetime.now(tz=UTC).timestamp()}",
            feedback_from="plex-random-mix",
            queue_anchor_track_id=tracks[0].id if tracks else None,
            tracks=tracks,
        )

    def get_radio_session_tracks(
        self,
        session: RadioSession,
        *,
        limit: int = 25,
    ) -> RadioSession:
        tracks = self._random_track_window(limit=limit)
        return RadioSession(
            station_id=session.station_id,
            session_id=session.session_id,
            batch_id=f"{session.station_id}-{datetime.now(tz=UTC).timestamp()}",
            feedback_from=session.feedback_from,
            queue_anchor_track_id=tracks[0].id if tracks else session.queue_anchor_track_id,
            tracks=tracks,
        )

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> Playlist:
        del owner_id
        for playlist in self.get_user_playlists():
            if playlist.id == playlist_id:
                return playlist
        raise TrackUnavailableError(f"Playlist {playlist_id} is unavailable")

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> Sequence[Track]:
        del owner_id
        playlist = self._fetch_playlist(playlist_id)
        try:
            return tuple(self._map_track(item) for item in playlist.items())
        except Exception as exc:
            raise NetworkError(f"Failed to load playlist {playlist_id}") from exc

    def get_playlist_track_page(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        del owner_id
        playlist = self._fetch_playlist(playlist_id)
        try:
            raw_tracks = playlist.fetchItems(
                f"{playlist.key}/items",
                container_start=offset,
                container_size=limit,
                maxresults=limit,
            )
        except Exception as exc:
            raise NetworkError(f"Failed to page playlist {playlist_id}") from exc
        return tuple(self._map_track(item) for item in raw_tracks)

    def get_album(self, album_id: str) -> Album:
        return self._map_album(self._fetch_item(album_id))

    def get_album_tracks(self, album_id: str) -> Sequence[Track]:
        album = self._fetch_item(album_id)
        try:
            return tuple(self._map_track(item) for item in album.tracks())
        except Exception as exc:
            raise NetworkError(f"Failed to load album {album_id}") from exc

    def get_album_track_page(
        self,
        album_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        album = self._fetch_item(album_id)
        try:
            raw_tracks = album.tracks(
                container_start=offset,
                container_size=limit,
                maxresults=limit,
            )
        except Exception as exc:
            raise NetworkError(f"Failed to page album {album_id}") from exc
        return tuple(self._map_track(item) for item in raw_tracks)

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50) -> Sequence[Album]:
        artist = self._fetch_item(artist_id)
        try:
            albums = artist.albums()
        except Exception as exc:
            raise NetworkError(f"Failed to load artist albums {artist_id}") from exc
        return tuple(self._map_album(item) for item in albums[:limit])

    def get_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[Album]:
        del artist_id, limit
        return ()

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50) -> Sequence[Playlist]:
        del artist_id, limit
        return ()

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50) -> Sequence[Track]:
        return self.get_artist_track_page(artist_id, offset=0, limit=limit)

    def get_artist_track_page(
        self,
        artist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        section = self._require_section()
        try:
            return tuple(
                self._map_track(item)
                for item in section.search(
                    libtype="track",
                    container_start=offset,
                    container_size=limit,
                    maxresults=limit,
                    filters={"artist.id": int(artist_id)},
                )
            )
        except Exception as exc:
            if self._logger is not None:
                self._logger.warning(
                    "Direct Plex artist track search failed for %s; "
                    "falling back to album traversal: %s",
                    artist_id,
                    exc,
                )
        fallback_limit = offset + limit
        return self._get_artist_tracks_via_albums(
            artist_id,
            limit=fallback_limit,
        )[offset:offset + limit]

    def resolve_stream_ref(self, track: Track) -> str:
        server = self._require_server()
        raw_track = self._fetch_item(track.id)
        media = getattr(raw_track, "media", None) or ()
        if not media:
            raise StreamResolveError(f"Track {track.id} has no media payload")
        parts = getattr(media[0], "parts", None) or ()
        if not parts:
            raise StreamResolveError(f"Track {track.id} has no media parts")
        part_key = getattr(parts[0], "key", None)
        if not part_key:
            raise StreamResolveError(f"Track {track.id} has no playable part key")
        return server.url(part_key, includeToken=True)

    def report_play_audio(
        self,
        *,
        track: Track,
        from_: str,
        play_id: str,
        track_length_seconds: int,
        total_played_seconds: int,
        end_position_seconds: int,
        playlist_id: str | None = None,
        timestamp: str | None = None,
        client_now: str | None = None,
    ) -> None:
        del track, from_, play_id, track_length_seconds, total_played_seconds, end_position_seconds
        del playlist_id, timestamp, client_now

    def report_plays(
        self,
        events: Sequence[PlayEventReport],
        *,
        client_now: str,
    ) -> None:
        del events, client_now

    def report_station_radio_started(
        self,
        *,
        station_id: str,
        from_: str,
        batch_id: str,
    ) -> None:
        del station_id, from_, batch_id

    def report_station_track_started(
        self,
        *,
        station_id: str,
        track_id: str,
        batch_id: str,
    ) -> None:
        del station_id, track_id, batch_id

    def report_station_track_finished(
        self,
        *,
        station_id: str,
        track_id: str,
        total_played_seconds: float,
        batch_id: str,
    ) -> None:
        del station_id, track_id, total_played_seconds, batch_id

    def report_station_track_skipped(
        self,
        *,
        station_id: str,
        track_id: str,
        total_played_seconds: float,
        batch_id: str,
    ) -> None:
        del station_id, track_id, total_played_seconds, batch_id

    def report_radio_session_feedback(
        self,
        session: RadioSession,
        feedback_type: RadioFeedbackType,
        *,
        track_id: str | None = None,
        total_played_seconds: float | None = None,
    ) -> None:
        del session, feedback_type, track_id, total_played_seconds

    def _require_session(self) -> AuthSession:
        if self._session is None:
            raise AuthError("Plex authentication is required")
        return self._session

    def _require_server(self):
        if self._server is None:
            session = self._require_session()
            self._connect_from_session(session)
        if self._server is None:
            raise AuthError("Plex server connection is not configured")
        return self._server

    def _require_section(self):
        if self._music_section is None:
            session = self._require_session()
            self._connect_from_session(session)
        if self._music_section is None:
            raise AuthError("Plex music library is not configured")
        return self._music_section

    def _connect_from_session(self, session: AuthSession) -> None:
        if not session.server_url or not session.server_access_token:
            raise AuthError("Plex server details are missing from the saved session")
        server = self._connect(session.server_url, session.server_access_token)
        section = None
        if session.music_section_id is not None:
            section = server.library.sectionByID(int(session.music_section_id))
        if section is None:
            raise AuthError("Saved Plex music library could not be restored")
        self._server = server
        self._music_section = section

    def _connect(self, server_url: str, server_token: str):
        try:
            from plexapi.server import PlexServer
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise AuthError("plexapi is not installed") from exc
        try:
            server = PlexServer(server_url, server_token, timeout=5)
            server.library.sections()
        except Exception as exc:
            raise AuthError(f"Failed to connect to Plex server {server_url}") from exc
        return server

    def _fetch_item(self, item_id: str):
        server = self._require_server()
        try:
            return server.fetchItem(int(item_id) if str(item_id).isdigit() else item_id)
        except Exception as exc:
            raise TrackUnavailableError(f"Plex item {item_id} is unavailable") from exc

    def _fetch_playlist(self, playlist_id: str):
        for playlist in self._require_server().playlists():
            if str(getattr(playlist, "ratingKey", "")) == str(playlist_id):
                return playlist
        raise TrackUnavailableError(f"Playlist {playlist_id} is unavailable")

    def _rate_track(self, track_id: str, rating: int) -> None:
        track = self._fetch_item(track_id)
        try:
            track.rate(rating)
        except Exception as exc:
            raise NetworkError(f"Failed to update Plex rating for track {track_id}") from exc

    def _all_tracks(self, *, limit: int) -> tuple[Track, ...]:
        section = self._require_section()
        if limit > 0:
            raw_tracks = section.search(
                libtype="track",
                limit=limit,
                maxresults=limit,
            )
            return tuple(self._map_track(item) for item in raw_tracks)
        raw_tracks = section.search(libtype="track")
        return tuple(self._map_track(item) for item in raw_tracks)

    def _all_albums(self):
        return self._require_section().search(libtype="album")

    def _all_artists(self):
        return self._require_section().search(libtype="artist")

    def _random_track_window(self, *, limit: int) -> tuple[Track, ...]:
        if limit <= 0:
            return ()
        total_size = self._track_library_size()
        if total_size <= 0:
            return ()
        sample_size = min(limit, total_size)
        seen_offsets: set[int] = set()
        seen_track_ids: set[str] = set()
        tracks: list[Track] = []
        max_attempts = max(sample_size * 6, 12)

        for _attempt in range(max_attempts):
            if len(tracks) >= sample_size or len(seen_offsets) >= total_size:
                break
            offset = self._random.randrange(total_size)
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            page = self.get_library_track_page(offset=offset, limit=1)
            if not page:
                continue
            track = page[0]
            if track.id in seen_track_ids:
                continue
            seen_track_ids.add(track.id)
            tracks.append(track)

        if len(tracks) < sample_size:
            for offset in range(total_size):
                if len(tracks) >= sample_size:
                    break
                if offset in seen_offsets:
                    continue
                page = self.get_library_track_page(offset=offset, limit=1)
                if not page:
                    continue
                track = page[0]
                if track.id in seen_track_ids:
                    continue
                seen_track_ids.add(track.id)
                tracks.append(track)
        return tuple(tracks)

    def _track_library_size(self) -> int:
        if self._track_total_size is not None:
            return self._track_total_size
        section = self._require_section()
        try:
            result = section.search(
                libtype="track",
                container_start=0,
                container_size=1,
                maxresults=1,
            )
        except Exception as exc:
            raise NetworkError("Failed to count Plex library tracks") from exc
        total_size = int(getattr(result, "totalSize", 0) or len(result))
        self._track_total_size = total_size
        return total_size

    def _get_artist_tracks_via_albums(self, artist_id: str, *, limit: int) -> tuple[Track, ...]:
        artist = self._fetch_item(artist_id)
        seen: set[str] = set()
        tracks = []
        try:
            albums = artist.albums()
        except Exception as exc:
            raise NetworkError(f"Failed to load artist tracks {artist_id}") from exc
        for album in albums:
            for track in album.tracks():
                track_id = str(getattr(track, "ratingKey", ""))
                if not track_id or track_id in seen:
                    continue
                seen.add(track_id)
                tracks.append(self._map_track(track))
                if len(tracks) >= limit:
                    return tuple(tracks)
        return tuple(tracks)

    def _map_track(self, raw_track: Any) -> Track:
        title = str(getattr(raw_track, "title", "Unknown Track"))
        artist = getattr(raw_track, "grandparentTitle", None) or getattr(
            raw_track, "originalTitle", None
        )
        artist_name = str(artist or "Unknown Artist")
        album_title = getattr(raw_track, "parentTitle", None)
        album_id = getattr(raw_track, "parentRatingKey", None)
        artist_id = getattr(raw_track, "grandparentRatingKey", None)
        artwork_ref = getattr(raw_track, "parentThumb", None) or getattr(raw_track, "thumb", None)
        if artwork_ref and self._server is not None:
            artwork_ref = self._server.url(artwork_ref, includeToken=True)
        user_rating = getattr(raw_track, "userRating", None) or 0
        return Track(
            id=str(raw_track.ratingKey),
            title=title,
            artists=(artist_name,),
            artist_ids=(str(artist_id),) if artist_id is not None else (),
            album_id=str(album_id) if album_id is not None else None,
            album_title=str(album_title) if album_title else None,
            album_year=getattr(raw_track, "year", None),
            duration_ms=getattr(raw_track, "duration", None),
            artwork_ref=artwork_ref,
            available=True,
            is_liked=int(user_rating or 0) >= 10,
        )

    def _map_album(self, raw_album: Any) -> Album:
        artist_name = getattr(raw_album, "parentTitle", None) or getattr(raw_album, "title", "")
        artist_id = getattr(raw_album, "parentRatingKey", None)
        artwork_ref = getattr(raw_album, "thumb", None)
        if artwork_ref and self._server is not None:
            artwork_ref = self._server.url(artwork_ref, includeToken=True)
        return Album(
            id=str(raw_album.ratingKey),
            title=str(getattr(raw_album, "title", "Unknown Album")),
            artists=(str(artist_name),) if artist_name else (),
            artist_ids=(str(artist_id),) if artist_id is not None else (),
            year=getattr(raw_album, "year", None),
            track_count=getattr(raw_album, "leafCount", None),
            artwork_ref=artwork_ref,
        )

    def _map_artist(self, raw_artist: Any) -> Artist:
        artwork_ref = getattr(raw_artist, "thumb", None)
        if artwork_ref and self._server is not None:
            artwork_ref = self._server.url(artwork_ref, includeToken=True)
        return Artist(
            id=str(raw_artist.ratingKey),
            name=str(getattr(raw_artist, "title", "Unknown Artist")),
            artwork_ref=artwork_ref,
        )

    def _map_playlist(self, raw_playlist: Any) -> Playlist:
        artwork_ref = getattr(raw_playlist, "thumb", None)
        if artwork_ref and self._server is not None:
            artwork_ref = self._server.url(artwork_ref, includeToken=True)
        return Playlist(
            id=str(raw_playlist.ratingKey),
            title=str(getattr(raw_playlist, "title", "Playlist")),
            owner_name=raw_playlist.title,
            description=getattr(raw_playlist, "summary", None),
            track_count=getattr(raw_playlist, "leafCount", None),
            artwork_ref=artwork_ref,
        )

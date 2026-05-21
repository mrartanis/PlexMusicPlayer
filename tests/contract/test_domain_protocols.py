from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain import (
    Album,
    Artist,
    AudioQuality,
    AuthRepo,
    AuthSession,
    CatalogSearchResults,
    Clock,
    LibraryCacheRepo,
    LikedTrackIds,
    LikedTrackSnapshot,
    Logger,
    MusicService,
    PlaybackEngine,
    PlaybackState,
    PlaybackStateRepo,
    PlaybackStatus,
    PlayEventReport,
    Playlist,
    QueueItem,
    RadioFeedbackType,
    RadioSession,
    SavedPlaybackQueue,
    SettingsRepo,
    Station,
    StationTrackBatch,
    Track,
)


class FakeMusicService:
    def get_auth_session(self) -> AuthSession | None:
        return AuthSession(user_id="user-1", token="token")

    def clear_auth_session(self) -> None:
        self.cleared_session = True

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        return AuthSession(
            user_id="user-1",
            token=token,
            expires_at=expires_at,
            display_name="listener",
        )

    def get_track(self, track_id: str) -> Track:
        return Track(id=track_id, title=f"Track {track_id}", artists=("Artist",))

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return [Track(id=f"{query}-{limit}", title=query, artists=("Artist",))]

    def search_track_page(
        self,
        query: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        return [Track(id=f"{query}-{offset}-{limit}", title=query, artists=("Artist",))]

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults:
        return CatalogSearchResults(
            tracks=tuple(self.search_tracks(query, limit=limit)),
            albums=(Album(id=f"album-{query}", title=f"Album {query}"),),
        )

    def get_library_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        return [Track(id=f"library-{limit}", title="Library", artists=("Artist",))]

    def get_library_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        return [Track(id=f"library-{offset}-{limit}", title="Library", artists=("Artist",))]

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        return [Track(id=f"liked-{limit}", title="Liked", artists=("Artist",))]

    def get_liked_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        return [Track(id=f"liked-{offset}-{limit}", title="Liked", artists=("Artist",))]

    def get_liked_track_ids(
        self,
        *,
        if_modified_since_revision: int = 0,
    ) -> LikedTrackIds | None:
        del if_modified_since_revision
        return LikedTrackIds(
            user_id="user-1",
            revision=1,
            track_ids=frozenset({"liked-100"}),
        )

    def get_liked_albums(self, *, limit: int = 100) -> Sequence[Album]:
        return [Album(id=f"liked-album-{limit}", title="Liked Album")]

    def get_liked_album_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Album]:
        return [Album(id=f"liked-album-{offset}-{limit}", title="Liked Album")]

    def get_liked_artists(self, *, limit: int = 100) -> Sequence[Artist]:
        return [Artist(id=f"liked-artist-{limit}", name="Liked Artist")]

    def get_liked_artist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Artist]:
        return [Artist(id=f"liked-artist-{offset}-{limit}", name="Liked Artist")]

    def get_liked_playlists(self, *, limit: int = 100) -> Sequence[Playlist]:
        return [Playlist(id=f"liked-playlist-{limit}", title="Liked Playlist", is_liked=True)]

    def get_liked_playlist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Playlist]:
        return [
            Playlist(
                id=f"liked-playlist-{offset}-{limit}",
                title="Liked Playlist",
                is_liked=True,
            )
        ]

    def like_track(self, track_id: str) -> None:
        self.liked_track_id = track_id

    def unlike_track(self, track_id: str) -> None:
        self.unliked_track_id = track_id

    def like_album(self, album_id: str) -> None:
        self.liked_album_id = album_id

    def unlike_album(self, album_id: str) -> None:
        self.unliked_album_id = album_id

    def like_artist(self, artist_id: str) -> None:
        self.liked_artist_id = artist_id

    def unlike_artist(self, artist_id: str) -> None:
        self.unliked_artist_id = artist_id

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self.liked_playlist = (playlist_id, owner_id)

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self.unliked_playlist = (playlist_id, owner_id)

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self.quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return getattr(self, "quality", AudioQuality.HQ)

    def get_user_playlists(self) -> Sequence[Playlist]:
        return [Playlist(id="playlist-1", title="Playlist")]

    def get_playlist_track_page(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        del owner_id
        return [Track(id=f"{playlist_id}-{offset}-{limit}", title="Playlist", artists=("Artist",))]

    def get_generated_playlists(self) -> Sequence[Playlist]:
        return [Playlist(id="generated-1", title="Playlist of the day")]

    def get_album_track_page(
        self,
        album_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        return [Track(id=f"{album_id}-{offset}-{limit}", title="Album", artists=("Artist",))]

    def get_stations(self) -> Sequence[Station]:
        return [Station(id="plex:random", title="Random Mix")]

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]:
        return [Track(id=f"{station_id}-{limit}", title="Wave Track", artists=("Artist",))]

    def get_station_track_batch(
        self,
        station_id: str,
        *,
        limit: int = 25,
        queue_track_id: str | None = None,
    ) -> StationTrackBatch:
        del queue_track_id
        return StationTrackBatch(
            station_id=station_id,
            batch_id="batch-1",
            tracks=tuple(self.get_station_tracks(station_id, limit=limit)),
        )

    def start_radio_session(
        self,
        station_id: str,
        *,
        limit: int = 25,
    ) -> RadioSession:
        batch = self.get_station_track_batch(station_id, limit=limit)
        return RadioSession(
            station_id=station_id,
            session_id=f"{station_id}-session",
            batch_id=batch.batch_id,
            feedback_from=f"radio-mobile-{station_id.replace(':', '-')}-default",
            queue_anchor_track_id=batch.tracks[0].id if batch.tracks else None,
            tracks=batch.tracks,
        )

    def get_radio_session_tracks(
        self,
        session: RadioSession,
        *,
        limit: int = 25,
    ) -> RadioSession:
        batch = self.get_station_track_batch(
            session.station_id,
            limit=limit,
            queue_track_id=session.queue_anchor_track_id,
        )
        next_anchor_track_id = (
            batch.tracks[0].id if batch.tracks else session.queue_anchor_track_id
        )
        return RadioSession(
            station_id=session.station_id,
            session_id=session.session_id,
            batch_id=batch.batch_id,
            feedback_from=session.feedback_from,
            queue_anchor_track_id=next_anchor_track_id,
            tracks=batch.tracks,
        )

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> Playlist:
        del owner_id
        return Playlist(id=playlist_id, title="Playlist")

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> Sequence[Track]:
        del owner_id
        return [Track(id=f"{playlist_id}-track", title="Playlist Track", artists=("Artist",))]

    def get_album(self, album_id: str) -> Album:
        return Album(id=album_id, title="Album")

    def get_album_tracks(self, album_id: str) -> Sequence[Track]:
        return [Track(id=f"{album_id}-track", title="Album Track", artists=("Artist",))]

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50) -> Sequence[Album]:
        del limit
        return [Album(id=f"{artist_id}-album", title="Artist Album")]

    def get_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[Album]:
        del limit
        return [Album(id=f"{artist_id}-compilation", title="Artist Compilation")]

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50) -> Sequence[Playlist]:
        del limit
        return [Playlist(id=f"{artist_id}-playlist", title="Artist Playlist")]

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50) -> Sequence[Track]:
        return [Track(id=f"{artist_id}-track-{limit}", title="Artist Track", artists=("Artist",))]

    def get_artist_track_page(
        self,
        artist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]:
        return [
            Track(
                id=f"{artist_id}-track-{offset}-{limit}",
                title="Artist Track",
                artists=("Artist",),
            )
        ]

    def resolve_stream_ref(self, track: Track) -> str:
        return track.stream_ref or f"stream:{track.id}"

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
        del (
            track,
            from_,
            play_id,
            track_length_seconds,
            total_played_seconds,
            end_position_seconds,
            playlist_id,
            timestamp,
            client_now,
        )

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


class FakePlaybackEngine:
    def __init__(self) -> None:
        self._state = PlaybackState()

    def load(self, queue_item: Track, *, stream_ref: str) -> None:
        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            active_index=0,
            duration_ms=queue_item.duration_ms,
        )

    def play(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.PLAYING)

    def pause(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.PAUSED)

    def stop(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.STOPPED)

    def seek(self, position_ms: int) -> None:
        self._state = PlaybackState(status=self._state.status, position_ms=position_ms)

    def set_volume(self, volume: int) -> None:
        self._state = PlaybackState(status=self._state.status, volume=volume)

    def get_state(self) -> PlaybackState:
        return self._state

    def on_ready_for_seek(self, callback: Any) -> None:
        self.ready_for_seek_callback = callback


class FakeSettingsRepo:
    def load_settings(self) -> Mapping[str, Any]:
        return {"volume": 70}

    def save_settings(self, settings: Mapping[str, Any]) -> None:
        self.settings = dict(settings)


class FakeLibraryCacheRepo:
    def __init__(self) -> None:
        self.catalog_search = CatalogSearchResults(
            tracks=(Track(id="catalog-track-1", title="Cached Track", artists=("Artist",)),),
        )
        self.liked_tracks = LikedTrackIds(
            user_id="user-1",
            revision=1,
            track_ids=frozenset({"track-1"}),
        )
        self.liked_track_snapshot = LikedTrackSnapshot(
            user_id="user-1",
            revision=1,
            tracks=(Track(id="track-1", title="Track", artists=("Artist",)),),
        )
        self.liked_album_snapshot = (Album(id="album-1", title="Album"),)
        self.liked_artist_snapshot = (Artist(id="artist-1", name="Artist"),)
        self.liked_playlist_snapshot = (Playlist(id="playlist-1", title="Playlist"),)
        self.user_playlist_snapshot = (Playlist(id="playlist-1", title="Playlist"),)
        self.generated_playlist_snapshot = (Playlist(id="generated-1", title="Generated"),)

    def load_recent_searches(self) -> Sequence[str]:
        return ["ambient", "jazz"]

    def save_recent_searches(self, searches: Sequence[str]) -> None:
        self.searches = list(searches)

    def load_catalog_search(self, query: str) -> CatalogSearchResults | None:
        del query
        return self.catalog_search

    def save_catalog_search(self, query: str, results: CatalogSearchResults) -> None:
        del query
        self.catalog_search = results

    def load_track_metadata(self, track_id: str) -> Track | None:
        return Track(id=track_id, title="Cached", artists=("Artist",))

    def save_track_metadata(self, track: Track) -> None:
        self.track = track

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None:
        if user_id != self.liked_tracks.user_id:
            return None
        return self.liked_tracks

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None:
        self.liked_tracks = liked_tracks

    def load_liked_track_snapshot(self, user_id: str) -> LikedTrackSnapshot | None:
        if user_id != self.liked_track_snapshot.user_id:
            return None
        return self.liked_track_snapshot

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot) -> None:
        self.liked_track_snapshot = snapshot

    def load_liked_album_snapshot(self, user_id: str) -> Sequence[Album] | None:
        del user_id
        return self.liked_album_snapshot

    def save_liked_album_snapshot(self, user_id: str, albums: Sequence[Album]) -> None:
        del user_id
        self.liked_album_snapshot = tuple(albums)

    def load_liked_artist_snapshot(self, user_id: str) -> Sequence[Artist] | None:
        del user_id
        return self.liked_artist_snapshot

    def save_liked_artist_snapshot(self, user_id: str, artists: Sequence[Artist]) -> None:
        del user_id
        self.liked_artist_snapshot = tuple(artists)

    def load_liked_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None:
        del user_id
        return self.liked_playlist_snapshot

    def save_liked_playlist_snapshot(self, user_id: str, playlists: Sequence[Playlist]) -> None:
        del user_id
        self.liked_playlist_snapshot = tuple(playlists)

    def load_user_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None:
        del user_id
        return self.user_playlist_snapshot

    def save_user_playlist_snapshot(self, user_id: str, playlists: Sequence[Playlist]) -> None:
        del user_id
        self.user_playlist_snapshot = tuple(playlists)

    def load_generated_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None:
        del user_id
        return self.generated_playlist_snapshot

    def save_generated_playlist_snapshot(
        self,
        user_id: str,
        playlists: Sequence[Playlist],
    ) -> None:
        del user_id
        self.generated_playlist_snapshot = tuple(playlists)

    def mark_track_liked(self, user_id: str, track_id: str) -> None:
        self.liked_tracks = LikedTrackIds(
            user_id=user_id,
            revision=self.liked_tracks.revision,
            track_ids=self.liked_tracks.track_ids | {track_id},
        )

    def mark_track_unliked(self, user_id: str, track_id: str) -> None:
        self.liked_tracks = LikedTrackIds(
            user_id=user_id,
            revision=self.liked_tracks.revision,
            track_ids=self.liked_tracks.track_ids - {track_id},
        )

    def load_artwork_ref(self, item_id: str) -> str | None:
        return f"art:{item_id}"

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        self.artwork = (item_id, artwork_ref)


class FakePlaybackStateRepo:
    def load_playback_queue(self) -> SavedPlaybackQueue | None:
        return SavedPlaybackQueue(
            queue=(QueueItem(track=Track(id="track-1", title="Track", artists=("Artist",))),),
            active_index=0,
        )

    def save_playback_queue(
        self,
        queue: Sequence[QueueItem],
        *,
        active_index: int | None,
        position_ms: int = 0,
    ) -> None:
        self.saved_queue = SavedPlaybackQueue(
            queue=tuple(queue),
            active_index=active_index,
            position_ms=position_ms,
        )

    def clear_playback_queue(self) -> None:
        self.saved_queue = None


class FakeAuthRepo:
    def load_session(self) -> AuthSession | None:
        return AuthSession(user_id="user-2", token="token-2")

    def save_session(self, session: AuthSession) -> None:
        self.session = session

    def clear_session(self) -> None:
        self.session = None


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 4, 19, tzinfo=UTC)


def test_fakes_satisfy_runtime_checkable_protocols() -> None:
    assert isinstance(FakeMusicService(), MusicService)
    assert isinstance(FakePlaybackEngine(), PlaybackEngine)
    assert isinstance(FakePlaybackStateRepo(), PlaybackStateRepo)
    assert isinstance(FakeSettingsRepo(), SettingsRepo)
    assert isinstance(FakeLibraryCacheRepo(), LibraryCacheRepo)
    assert isinstance(FakeAuthRepo(), AuthRepo)
    assert isinstance(FakeClock(), Clock)
    assert isinstance(logging.getLogger("yaymp-test"), Logger)


def test_protocol_shaped_fakes_expose_expected_behavior() -> None:
    music_service = FakeMusicService()
    playback_engine = FakePlaybackEngine()

    track = music_service.search_tracks("signal")[0]
    stream_ref = music_service.resolve_stream_ref(track)
    playback_engine.load(track, stream_ref=stream_ref)
    playback_engine.play()

    assert stream_ref == f"stream:{track.id}"
    assert playback_engine.get_state().status is PlaybackStatus.PLAYING

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.audio_quality import AudioQuality
from app.domain.auth import AuthSession
from app.domain.catalog import Album, Artist, CatalogSearchResults
from app.domain.playback import PlaybackState, PlayEventReport, QueueItem, SavedPlaybackQueue
from app.domain.playlist import Playlist
from app.domain.station import RadioFeedbackType, RadioSession, Station, StationTrackBatch
from app.domain.track import LikedTrackIds, LikedTrackSnapshot, Track


@runtime_checkable
class MusicService(Protocol):
    def get_auth_session(self) -> AuthSession | None: ...

    def clear_auth_session(self) -> None: ...

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession: ...

    def get_track(self, track_id: str) -> Track: ...

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]: ...

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults: ...

    def search_track_page(
        self,
        query: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def get_library_tracks(self, *, limit: int = 100) -> Sequence[Track]: ...

    def get_library_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]: ...

    def get_liked_track_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def get_liked_track_ids(
        self,
        *,
        if_modified_since_revision: int = 0,
    ) -> LikedTrackIds | None: ...

    def get_liked_albums(self, *, limit: int = 100) -> Sequence[Album]: ...

    def get_liked_album_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Album]: ...

    def get_liked_artists(self, *, limit: int = 100) -> Sequence[Artist]: ...

    def get_liked_artist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Artist]: ...

    def get_liked_playlists(self, *, limit: int = 100) -> Sequence[Playlist]: ...

    def get_liked_playlist_page(
        self,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Playlist]: ...

    def like_track(self, track_id: str) -> None: ...

    def unlike_track(self, track_id: str) -> None: ...

    def like_album(self, album_id: str) -> None: ...

    def unlike_album(self, album_id: str) -> None: ...

    def like_artist(self, artist_id: str) -> None: ...

    def unlike_artist(self, artist_id: str) -> None: ...

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None: ...

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None: ...

    def set_audio_quality(self, quality: AudioQuality) -> None: ...

    def get_audio_quality(self) -> AudioQuality: ...

    def get_user_playlists(self) -> Sequence[Playlist]: ...

    def get_generated_playlists(self) -> Sequence[Playlist]: ...

    def get_stations(self) -> Sequence[Station]: ...

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]: ...

    def get_station_track_batch(
        self,
        station_id: str,
        *,
        limit: int = 25,
        queue_track_id: str | None = None,
    ) -> StationTrackBatch: ...

    def start_radio_session(
        self,
        station_id: str,
        *,
        limit: int = 25,
    ) -> RadioSession: ...

    def get_radio_session_tracks(
        self,
        session: RadioSession,
        *,
        limit: int = 25,
    ) -> RadioSession: ...

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> Playlist: ...

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> Sequence[Track]: ...

    def get_playlist_track_page(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def get_album(self, album_id: str) -> Album: ...

    def get_album_tracks(self, album_id: str) -> Sequence[Track]: ...

    def get_album_track_page(
        self,
        album_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50) -> Sequence[Album]: ...

    def get_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[Album]: ...

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50) -> Sequence[Playlist]: ...

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50) -> Sequence[Track]: ...

    def get_artist_track_page(
        self,
        artist_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Track]: ...

    def resolve_stream_ref(self, track: Track) -> str: ...

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
    ) -> None: ...

    def report_plays(
        self,
        events: Sequence[PlayEventReport],
        *,
        client_now: str,
    ) -> None: ...

    def report_station_radio_started(
        self,
        *,
        station_id: str,
        from_: str,
        batch_id: str,
    ) -> None: ...

    def report_station_track_started(
        self,
        *,
        station_id: str,
        track_id: str,
        batch_id: str,
    ) -> None: ...

    def report_station_track_finished(
        self,
        *,
        station_id: str,
        track_id: str,
        total_played_seconds: float,
        batch_id: str,
    ) -> None: ...

    def report_station_track_skipped(
        self,
        *,
        station_id: str,
        track_id: str,
        total_played_seconds: float,
        batch_id: str,
    ) -> None: ...

    def report_radio_session_feedback(
        self,
        session: RadioSession,
        feedback_type: RadioFeedbackType,
        *,
        track_id: str | None = None,
        total_played_seconds: float | None = None,
    ) -> None: ...


@runtime_checkable
class PlaybackEngine(Protocol):
    def load(self, track: Track, *, stream_ref: str) -> None: ...

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def seek(self, position_ms: int) -> None: ...

    def set_volume(self, volume: int) -> None: ...

    def get_state(self) -> PlaybackState: ...

    def on_ready_for_seek(self, callback: Any) -> None: ...


@runtime_checkable
class PlaybackStateRepo(Protocol):
    def load_playback_queue(self) -> SavedPlaybackQueue | None: ...

    def save_playback_queue(
        self,
        queue: Sequence[QueueItem],
        *,
        active_index: int | None,
        position_ms: int = 0,
    ) -> None: ...

    def clear_playback_queue(self) -> None: ...


@runtime_checkable
class SettingsRepo(Protocol):
    def load_settings(self) -> Mapping[str, Any]: ...

    def save_settings(self, settings: Mapping[str, Any]) -> None: ...


@runtime_checkable
class LibraryCacheRepo(Protocol):
    def load_recent_searches(self) -> Sequence[str]: ...

    def save_recent_searches(self, searches: Sequence[str]) -> None: ...

    def load_catalog_search(self, query: str) -> CatalogSearchResults | None: ...

    def save_catalog_search(self, query: str, results: CatalogSearchResults) -> None: ...

    def load_track_metadata(self, track_id: str) -> Track | None: ...

    def save_track_metadata(self, track: Track) -> None: ...

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None: ...

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None: ...

    def load_liked_track_snapshot(self, user_id: str) -> LikedTrackSnapshot | None: ...

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot) -> None: ...

    def load_liked_album_snapshot(self, user_id: str) -> Sequence[Album] | None: ...

    def save_liked_album_snapshot(self, user_id: str, albums: Sequence[Album]) -> None: ...

    def load_liked_artist_snapshot(self, user_id: str) -> Sequence[Artist] | None: ...

    def save_liked_artist_snapshot(self, user_id: str, artists: Sequence[Artist]) -> None: ...

    def load_liked_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None: ...

    def save_liked_playlist_snapshot(
        self,
        user_id: str,
        playlists: Sequence[Playlist],
    ) -> None: ...

    def load_user_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None: ...

    def save_user_playlist_snapshot(
        self,
        user_id: str,
        playlists: Sequence[Playlist],
    ) -> None: ...

    def load_generated_playlist_snapshot(self, user_id: str) -> Sequence[Playlist] | None: ...

    def save_generated_playlist_snapshot(
        self,
        user_id: str,
        playlists: Sequence[Playlist],
    ) -> None: ...

    def mark_track_liked(self, user_id: str, track_id: str) -> None: ...

    def mark_track_unliked(self, user_id: str, track_id: str) -> None: ...

    def load_artwork_ref(self, item_id: str) -> str | None: ...

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None: ...


@runtime_checkable
class AuthRepo(Protocol):
    def load_session(self) -> AuthSession | None: ...

    def save_session(self, session: AuthSession) -> None: ...

    def clear_session(self) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class Logger(Protocol):
    def debug(self, message: str, *args: object) -> None: ...

    def info(self, message: str, *args: object) -> None: ...

    def warning(self, message: str, *args: object) -> None: ...

    def error(self, message: str, *args: object) -> None: ...

    def exception(self, message: str, *args: object) -> None: ...

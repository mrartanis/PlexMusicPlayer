"""Domain layer exports."""

from app.domain.audio_quality import AudioQuality
from app.domain.auth import AuthSession
from app.domain.catalog import Album, Artist, CatalogSearchResults
from app.domain.errors import (
    AuthError,
    NetworkError,
    PlaybackBackendError,
    StorageError,
    StreamResolveError,
    TrackUnavailableError,
)
from app.domain.playback import (
    PlaybackState,
    PlaybackStatus,
    PlayEventReport,
    QueueItem,
    RepeatMode,
    SavedPlaybackQueue,
    WaveformState,
)
from app.domain.playlist import Playlist
from app.domain.protocols import (
    AuthRepo,
    Clock,
    LibraryCacheRepo,
    Logger,
    MusicService,
    PlaybackEngine,
    PlaybackStateRepo,
    SettingsRepo,
)
from app.domain.station import RadioFeedbackType, RadioSession, Station, StationTrackBatch
from app.domain.track import LikedTrackIds, LikedTrackSnapshot, Track

__all__ = [
    "AuthError",
    "AuthRepo",
    "AuthSession",
    "AudioQuality",
    "Album",
    "Artist",
    "CatalogSearchResults",
    "Clock",
    "LibraryCacheRepo",
    "LikedTrackIds",
    "LikedTrackSnapshot",
    "Logger",
    "MusicService",
    "NetworkError",
    "PlayEventReport",
    "PlaybackBackendError",
    "PlaybackEngine",
    "PlaybackState",
    "PlaybackStateRepo",
    "PlaybackStatus",
    "Playlist",
    "QueueItem",
    "RepeatMode",
    "RadioFeedbackType",
    "RadioSession",
    "SavedPlaybackQueue",
    "SettingsRepo",
    "Station",
    "StationTrackBatch",
    "StorageError",
    "StreamResolveError",
    "Track",
    "TrackUnavailableError",
    "WaveformState",
]

from __future__ import annotations

from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import (
    Album,
    Artist,
    AudioQuality,
    CatalogSearchResults,
    LikedTrackIds,
    LikedTrackSnapshot,
    PlayEventReport,
    Playlist,
    RadioFeedbackType,
    RadioSession,
    Station,
    StationTrackBatch,
    Track,
)


class TestLogger:
    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        del message, args

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class InMemoryLibraryCacheRepo:
    def __init__(self) -> None:
        self.searches: tuple[str, ...] = ()
        self.catalog_search: dict[str, CatalogSearchResults] = {}
        self.tracks: dict[str, Track] = {}
        self.artwork: dict[str, str] = {}
        self.liked_tracks: dict[str, LikedTrackIds] = {}
        self.liked_track_snapshots: dict[str, LikedTrackSnapshot] = {}
        self.liked_album_snapshots: dict[str, tuple[Album, ...]] = {}
        self.liked_artist_snapshots: dict[str, tuple[Artist, ...]] = {}
        self.liked_playlist_snapshots: dict[str, tuple[Playlist, ...]] = {}
        self.user_playlist_snapshots: dict[str, tuple[Playlist, ...]] = {}
        self.generated_playlist_snapshots: dict[str, tuple[Playlist, ...]] = {}

    def load_recent_searches(self):
        return self.searches

    def save_recent_searches(self, searches):
        self.searches = tuple(searches)

    def load_catalog_search(self, query: str):
        return self.catalog_search.get(query.strip().casefold())

    def save_catalog_search(self, query: str, results: CatalogSearchResults):
        self.catalog_search[query.strip().casefold()] = results

    def load_track_metadata(self, track_id: str):
        return self.tracks.get(track_id)

    def save_track_metadata(self, track: Track):
        self.tracks[track.id] = track

    def load_liked_track_ids(self, user_id: str):
        return self.liked_tracks.get(user_id)

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds):
        self.liked_tracks[liked_tracks.user_id] = liked_tracks

    def load_liked_track_snapshot(self, user_id: str):
        return self.liked_track_snapshots.get(user_id)

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot):
        self.liked_track_snapshots[snapshot.user_id] = snapshot

    def load_liked_album_snapshot(self, user_id: str):
        return self.liked_album_snapshots.get(user_id)

    def save_liked_album_snapshot(self, user_id: str, albums):
        self.liked_album_snapshots[user_id] = tuple(albums)

    def load_liked_artist_snapshot(self, user_id: str):
        return self.liked_artist_snapshots.get(user_id)

    def save_liked_artist_snapshot(self, user_id: str, artists):
        self.liked_artist_snapshots[user_id] = tuple(artists)

    def load_liked_playlist_snapshot(self, user_id: str):
        return self.liked_playlist_snapshots.get(user_id)

    def save_liked_playlist_snapshot(self, user_id: str, playlists):
        self.liked_playlist_snapshots[user_id] = tuple(playlists)

    def load_user_playlist_snapshot(self, user_id: str):
        return self.user_playlist_snapshots.get(user_id)

    def save_user_playlist_snapshot(self, user_id: str, playlists):
        self.user_playlist_snapshots[user_id] = tuple(playlists)

    def load_generated_playlist_snapshot(self, user_id: str):
        return self.generated_playlist_snapshots.get(user_id)

    def save_generated_playlist_snapshot(self, user_id: str, playlists):
        self.generated_playlist_snapshots[user_id] = tuple(playlists)

    def mark_track_liked(self, user_id: str, track_id: str):
        current = self.liked_tracks.get(
            user_id,
            LikedTrackIds(user_id=user_id, revision=0, track_ids=frozenset()),
        )
        self.liked_tracks[user_id] = LikedTrackIds(
            user_id=user_id,
            revision=current.revision,
            track_ids=current.track_ids | {track_id},
        )

    def mark_track_unliked(self, user_id: str, track_id: str):
        current = self.liked_tracks.get(user_id)
        if current is None:
            return
        self.liked_tracks[user_id] = LikedTrackIds(
            user_id=user_id,
            revision=current.revision,
            track_ids=current.track_ids - {track_id},
        )

    def load_artwork_ref(self, item_id: str):
        return self.artwork.get(item_id)

    def save_artwork_ref(self, item_id: str, artwork_ref: str):
        self.artwork[item_id] = artwork_ref


class FakeMusicService:
    def __init__(self) -> None:
        self.liked_tracks_calls = 0
        self.liked_track_ids_revision = 7
        self.catalog_search_calls = 0

    def get_auth_session(self):
        from app.domain import AuthSession

        return AuthSession(user_id="user-1", token="token")

    def clear_auth_session(self):
        self.session = None

    def set_auth_session(self, session):
        self.session = session

    def build_auth_session(self, token: str, *, expires_at=None):
        from app.domain import AuthSession

        return AuthSession(user_id="user-1", token=token, expires_at=expires_at)

    def get_track(self, track_id: str):
        return Track(id=track_id, title=f"Track {track_id}", artists=("Artist",), stream_ref=f"s://{track_id}")

    def search_tracks(self, query: str, *, limit: int = 25):
        return (Track(id=f"{query}-{limit}", title=query, artists=("Artist",)),)

    def search_catalog(self, query: str, *, limit: int = 25):
        self.catalog_search_calls += 1
        return CatalogSearchResults(
            tracks=(Track(id=f"{query}-{limit}", title=query, artists=("Artist",)),),
            albums=(Album(id=f"album-{query}", title=f"Album {query}", artists=("Artist",)),),
            singles=(
                Album(
                    id=f"single-{query}",
                    title=f"Single {query}",
                    artists=("Artist",),
                    release_type="single",
                ),
            ),
            artists=(Artist(id=f"artist-{query}", name=f"Artist {query}"),),
            playlists=(Playlist(id=f"playlist-{query}", title=f"Playlist {query}"),),
        )

    def get_library_tracks(self, *, limit: int = 100):
        self.library_tracks_calls = getattr(self, "library_tracks_calls", 0) + 1
        return (Track(id=f"library-{limit}", title="Library", artists=("Artist",)),)

    def get_library_track_page(self, *, offset: int, limit: int):
        self.library_track_page_calls = getattr(self, "library_track_page_calls", [])
        self.library_track_page_calls.append((offset, limit))
        return (Track(id=f"library-{offset}-{limit}", title="Library", artists=("Artist",)),)

    def get_liked_tracks(self, *, limit: int = 100):
        self.liked_tracks_calls += 1
        return (
            Track(
                id=f"liked-{limit}",
                title="Liked",
                artists=("Artist",),
                artwork_ref="liked-cover",
                is_liked=True,
            ),
        )

    def get_liked_track_ids(self, *, if_modified_since_revision: int = 0):
        if if_modified_since_revision == self.liked_track_ids_revision:
            return None
        return LikedTrackIds(
            user_id="user-1",
            revision=self.liked_track_ids_revision,
            track_ids=frozenset({"liked-100"}),
        )

    def get_liked_albums(self, *, limit: int = 100):
        self.liked_albums_calls = getattr(self, "liked_albums_calls", 0) + 1
        return (
            Album(
                id=f"liked-album-{limit}",
                title="Liked Album",
                artists=("Artist",),
            ),
        )

    def get_liked_album_page(self, *, offset: int, limit: int):
        return (
            Album(
                id=f"liked-album-{offset}-{limit}",
                title="Liked Album",
                artists=("Artist",),
            ),
        )

    def get_liked_artists(self, *, limit: int = 100):
        self.liked_artists_calls = getattr(self, "liked_artists_calls", 0) + 1
        return (Artist(id=f"liked-artist-{limit}", name="Liked Artist"),)

    def get_liked_artist_page(self, *, offset: int, limit: int):
        return (Artist(id=f"liked-artist-{offset}-{limit}", name="Liked Artist"),)

    def get_liked_playlists(self, *, limit: int = 100):
        self.liked_playlists_calls = getattr(self, "liked_playlists_calls", 0) + 1
        return (Playlist(id=f"liked-playlist-{limit}", title="Liked Playlist", is_liked=True),)

    def get_liked_playlist_page(self, *, offset: int, limit: int):
        return (
            Playlist(
                id=f"liked-playlist-{offset}-{limit}",
                title="Liked Playlist",
                is_liked=True,
            ),
        )

    def like_track(self, track_id: str):
        self.liked_track_id = track_id

    def unlike_track(self, track_id: str):
        self.unliked_track_id = track_id

    def like_album(self, album_id: str):
        self.liked_album_id = album_id

    def unlike_album(self, album_id: str):
        self.unliked_album_id = album_id

    def like_artist(self, artist_id: str):
        self.liked_artist_id = artist_id

    def unlike_artist(self, artist_id: str):
        self.unliked_artist_id = artist_id

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None):
        self.liked_playlist = (playlist_id, owner_id)

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None):
        self.unliked_playlist = (playlist_id, owner_id)

    def set_audio_quality(self, quality: AudioQuality):
        self.quality = quality

    def get_audio_quality(self):
        return getattr(self, "quality", AudioQuality.HQ)

    def get_user_playlists(self):
        self.user_playlists_calls = getattr(self, "user_playlists_calls", 0) + 1
        return (Playlist(id="playlist-1", title="Playlist 1"),)

    def get_generated_playlists(self):
        self.generated_playlists_calls = getattr(self, "generated_playlists_calls", 0) + 1
        return (Playlist(id="generated-1", title="Playlist of the Day"),)

    def get_stations(self):
        return (Station(id="plex:random", title="Random Mix"),)

    def get_station_tracks(self, station_id: str, *, limit: int = 25):
        return (Track(id=f"{station_id}-{limit}", title="Wave", artists=("Artist",)),)

    def get_station_track_batch(
        self,
        station_id: str,
        *,
        limit: int = 25,
        queue_track_id: str | None = None,
    ):
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
    ):
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
    ):
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

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None):
        del owner_id
        return Playlist(id=playlist_id, title=f"Playlist {playlist_id}")

    def get_playlist_tracks(self, playlist_id: str, *, owner_id: str | None = None):
        del owner_id
        return (Track(id=f"{playlist_id}-track", title="Playlist Track", artists=("Artist",)),)

    def get_album(self, album_id: str):
        return Album(id=album_id, title=f"Album {album_id}", artists=("Artist",))

    def get_album_tracks(self, album_id: str):
        return (Track(id=f"{album_id}-track", title="Album Track", artists=("Artist",)),)

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50):
        del limit
        return (
            Album(id=f"{artist_id}-direct", title="Direct Album", artists=("Artist",)),
            Album(
                id=f"{artist_id}-single",
                title="Direct Single",
                artists=("Artist",),
                release_type="single",
            ),
        )

    def get_artist_compilation_albums(self, artist_id: str, *, limit: int = 50):
        del limit
        return (
            Album(
                id=f"{artist_id}-also",
                title="Also Album",
                artists=("Various",),
                release_type="compilation",
            ),
        )

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50):
        del limit
        return (Playlist(id=f"{artist_id}-playlist", title="Artist Playlist"),)

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50):
        return (
            Track(
                id=f"{artist_id}-top-{limit}",
                title="Top Track",
                artists=("Artist",),
            ),
        )

    def get_artist_track_page(self, artist_id: str, *, offset: int, limit: int):
        self.artist_track_page_calls = getattr(self, "artist_track_page_calls", [])
        self.artist_track_page_calls.append((artist_id, offset, limit))
        return (
            Track(
                id=f"{artist_id}-page-{offset}-{limit}",
                title="Top Track",
                artists=("Artist",),
            ),
        )

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
        events: tuple[PlayEventReport, ...],
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


def test_search_service_updates_recent_searches() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    service = SearchService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.search_tracks("ambient")
    service.search_tracks("jazz")
    service.search_tracks("ambient")

    assert [track.id for track in tracks] == ["ambient-25"]
    assert service.load_recent_searches() == ("ambient", "jazz")
    assert cache_repo.load_track_metadata("ambient-25") == tracks[0]


def test_search_service_preserves_cached_liked_state() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_track_metadata(
        Track(id="ambient-25", title="Liked Ambient", artists=("Artist",), is_liked=True)
    )
    cache_repo.save_liked_track_ids(
        LikedTrackIds(user_id="user-1", revision=7, track_ids=frozenset({"ambient-25"}))
    )
    service = SearchService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.search_tracks("ambient")
    catalog = service.search_catalog("ambient")

    assert tracks[0].is_liked is True
    assert catalog.tracks[0].is_liked is True
    assert cache_repo.load_track_metadata("ambient-25").is_liked is True


def test_search_service_returns_grouped_catalog_results() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    music_service = FakeMusicService()
    service = SearchService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    results = service.search_catalog("ambient")

    assert [track.id for track in results.tracks] == ["ambient-25"]
    assert [album.id for album in results.albums] == [
        "album-ambient",
        "artist-ambient-direct",
    ]
    assert [album.id for album in results.singles] == [
        "single-ambient",
        "artist-ambient-single",
    ]
    assert [album.id for album in results.compilations] == ["artist-ambient-also"]
    assert [artist.id for artist in results.artists] == ["artist-ambient"]
    assert [playlist.id for playlist in results.playlists] == ["playlist-ambient"]
    assert cache_repo.load_track_metadata("ambient-25") == results.tracks[0]
    assert music_service.catalog_search_calls == 1


def test_search_service_uses_cached_catalog_results() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    music_service = FakeMusicService()
    service = SearchService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    first = service.search_catalog("ambient")
    second = service.search_catalog("Ambient")

    assert first == second
    assert music_service.catalog_search_calls == 1


def test_library_service_exposes_playlists_and_stations() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    service = LibraryService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    assert [item.id for item in service.load_liked_tracks()] == ["liked-100"]
    assert [item.id for item in service.load_liked_albums()] == ["liked-album-100"]
    assert [item.id for item in service.load_liked_artists()] == ["liked-artist-100"]
    assert [item.id for item in service.load_liked_playlists()] == ["liked-playlist-100"]
    assert [item.id for item in service.load_user_playlists()] == ["playlist-1"]
    assert [item.id for item in service.load_generated_playlists()] == ["generated-1"]
    assert [item.id for item in service.load_stations()] == ["plex:random"]
    assert [item.id for item in service.load_station_tracks("plex:random")] == [
        "plex:random-25"
    ]
    assert [item.id for item in service.load_album_tracks("album-1")] == ["album-1-track"]
    assert [item.id for item in service.load_artist_playlists("artist-1")] == ["artist-1-playlist"]
    assert [item.id for item in service.load_artist_tracks("artist-1")] == ["artist-1-top-50"]
    assert cache_repo.load_artwork_ref("liked-100") == "liked-cover"


def test_library_service_preserves_cached_liked_state_for_loaded_tracks() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_track_metadata(
        Track(id="plex:random-25", title="Liked Wave", artists=("Artist",), is_liked=True)
    )
    cache_repo.save_liked_track_ids(
        LikedTrackIds(
            user_id="user-1",
            revision=7,
            track_ids=frozenset({"plex:random-25"}),
        )
    )
    service = LibraryService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.load_station_tracks("plex:random")

    assert tracks[0].is_liked is True
    assert cache_repo.load_track_metadata("plex:random-25").is_liked is True


def test_library_service_likes_and_unlikes_tracks() -> None:
    music_service = FakeMusicService()
    cache_repo = InMemoryLibraryCacheRepo()
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )
    track = Track(id="track-1", title="Track", artists=("Artist",))

    liked = service.like_track(track)
    unliked = service.unlike_track(liked)

    assert music_service.liked_track_id == "track-1"
    assert music_service.unliked_track_id == "track-1"
    assert liked.is_liked is True
    assert unliked.is_liked is False
    assert cache_repo.load_track_metadata("track-1") == unliked
    assert cache_repo.load_liked_track_ids("user-1").track_ids == frozenset()


def test_library_service_uses_cached_liked_tracks_when_revision_is_unchanged() -> None:
    music_service = FakeMusicService()
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_liked_track_snapshot(
        LikedTrackSnapshot(
            user_id="user-1",
            revision=7,
            tracks=(
                Track(id="cached-1", title="Cached", artists=("Artist",), is_liked=True),
            ),
        )
    )
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.load_liked_tracks()

    assert [track.id for track in tracks] == ["cached-1"]
    assert music_service.liked_tracks_calls == 0


def test_library_service_refreshes_liked_tracks_snapshot_when_revision_changes() -> None:
    music_service = FakeMusicService()
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_liked_track_snapshot(
        LikedTrackSnapshot(
            user_id="user-1",
            revision=6,
            tracks=(
                Track(id="cached-1", title="Cached", artists=("Artist",), is_liked=True),
            ),
        )
    )
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.load_liked_tracks()
    snapshot = cache_repo.load_liked_track_snapshot("user-1")

    assert [track.id for track in tracks] == ["liked-100"]
    assert music_service.liked_tracks_calls == 1
    assert snapshot is not None
    assert snapshot.revision == 7
    assert [track.id for track in snapshot.tracks] == ["liked-100"]


def test_library_service_uses_cached_album_artist_and_playlist_lists() -> None:
    music_service = FakeMusicService()
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_liked_album_snapshot("user-1", (Album(id="cached-album", title="Cached"),))
    cache_repo.save_liked_artist_snapshot("user-1", (Artist(id="cached-artist", name="Cached"),))
    cache_repo.save_liked_playlist_snapshot(
        "user-1",
        (Playlist(id="cached-liked-playlist", title="Cached"),),
    )
    cache_repo.save_user_playlist_snapshot(
        "user-1",
        (Playlist(id="cached-user-playlist", title="Cached"),),
    )
    cache_repo.save_generated_playlist_snapshot(
        "user-1",
        (Playlist(id="cached-generated-playlist", title="Cached", is_generated=True),),
    )
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    assert [item.id for item in service.load_liked_albums(limit=1)] == ["cached-album"]
    assert [item.id for item in service.load_liked_artists(limit=1)] == ["cached-artist"]
    assert [item.id for item in service.load_liked_playlists(limit=1)] == [
        "cached-liked-playlist"
    ]
    assert [item.id for item in service.load_user_playlists()] == ["cached-user-playlist"]
    assert [item.id for item in service.load_generated_playlists()] == ["cached-generated-playlist"]
    assert getattr(music_service, "liked_albums_calls", 0) == 0
    assert getattr(music_service, "liked_artists_calls", 0) == 0
    assert getattr(music_service, "liked_playlists_calls", 0) == 0
    assert getattr(music_service, "user_playlists_calls", 0) == 0
    assert getattr(music_service, "generated_playlists_calls", 0) == 0


def test_library_service_refreshes_cached_lists_when_snapshot_is_smaller_than_limit() -> None:
    music_service = FakeMusicService()
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_liked_album_snapshot("user-1", (Album(id="cached-album", title="Cached"),))
    cache_repo.save_liked_artist_snapshot("user-1", (Artist(id="cached-artist", name="Cached"),))
    cache_repo.save_liked_playlist_snapshot(
        "user-1",
        (Playlist(id="cached-liked-playlist", title="Cached"),),
    )
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    assert [item.id for item in service.load_liked_albums(limit=100)] == ["liked-album-100"]
    assert [item.id for item in service.load_liked_artists(limit=100)] == ["liked-artist-100"]
    assert [item.id for item in service.load_liked_playlists(limit=100)] == [
        "liked-playlist-100"
    ]
    assert getattr(music_service, "liked_albums_calls", 0) == 1
    assert getattr(music_service, "liked_artists_calls", 0) == 1
    assert getattr(music_service, "liked_playlists_calls", 0) == 1


def test_library_service_likes_and_unlikes_album_artist_and_playlist() -> None:
    music_service = FakeMusicService()
    service = LibraryService(
        music_service=music_service,
        library_cache_repo=InMemoryLibraryCacheRepo(),
        logger=TestLogger(),
    )

    liked_album = service.like_album(Album(id="album-1", title="Album"))
    unliked_album = service.unlike_album(liked_album)
    liked_artist = service.like_artist(Artist(id="artist-1", name="Artist"))
    unliked_artist = service.unlike_artist(liked_artist)
    liked_playlist = service.like_playlist(
        Playlist(id="playlist-1", title="Playlist", owner_id="7")
    )
    unliked_playlist = service.unlike_playlist(liked_playlist)

    assert music_service.liked_album_id == "album-1"
    assert music_service.unliked_album_id == "album-1"
    assert music_service.liked_artist_id == "artist-1"
    assert music_service.unliked_artist_id == "artist-1"
    assert music_service.liked_playlist == ("playlist-1", "7")
    assert music_service.unliked_playlist == ("playlist-1", "7")
    assert liked_album.is_liked is True and unliked_album.is_liked is False
    assert liked_artist.is_liked is True and unliked_artist.is_liked is False
    assert liked_playlist.is_liked is True and unliked_playlist.is_liked is False


def test_library_service_refreshes_liked_track_index() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    service = LibraryService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    service.refresh_liked_track_index()
    service.refresh_liked_track_index()

    assert cache_repo.load_liked_track_ids("user-1") == LikedTrackIds(
        user_id="user-1",
        revision=7,
        track_ids=frozenset({"liked-100"}),
    )

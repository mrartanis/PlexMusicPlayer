from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import ClassInfo, Property, QObject, Slot
from PySide6.QtWidgets import QWidget

from app.application.playback_service import PlaybackSnapshot
from app.domain import Logger, PlaybackStatus, RepeatMode
from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.playback_controller import PlaybackController
from app.presentation.qt.track_display import display_track_title

try:
    from PySide6.QtDBus import (
        QDBusAbstractAdaptor,
        QDBusConnection,
        QDBusMessage,
    )
except ImportError:  # pragma: no cover
    QDBusAbstractAdaptor = None
    QDBusConnection = None
    QDBusMessage = None


class SystemMediaIntegration:
    def initialize(self) -> None:
        pass

    def update_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        del snapshot

    def shutdown(self) -> None:
        pass


class NoopSystemMediaIntegration(SystemMediaIntegration):
    pass


def build_system_media_integration(
    *,
    playback_controller: PlaybackController,
    artwork_cache: FileArtworkCache,
    window: QWidget,
    logger: Logger,
) -> SystemMediaIntegration:
    if sys.platform == "darwin":
        return MacOSSystemMediaIntegration(
            playback_controller=playback_controller,
            artwork_cache=artwork_cache,
            logger=logger,
        )
    if sys.platform.startswith("linux"):
        return LinuxMprisIntegration(
            playback_controller=playback_controller,
            artwork_cache=artwork_cache,
            window=window,
            logger=logger,
        )
    if sys.platform == "win32":
        return WindowsSystemMediaIntegration(
            playback_controller=playback_controller,
            artwork_cache=artwork_cache,
            window=window,
            logger=logger,
        )
    return NoopSystemMediaIntegration()


class MacOSSystemMediaIntegration(SystemMediaIntegration):
    def __init__(
        self,
        *,
        playback_controller: PlaybackController,
        artwork_cache: FileArtworkCache,
        logger: Logger,
    ) -> None:
        self._controller = playback_controller
        self._artwork_cache = artwork_cache
        self._logger = logger
        self._snapshot: PlaybackSnapshot | None = None
        self._initialized = False
        self._delegate: Any | None = None
        self._media_player: Any | None = None
        self._foundation: Any | None = None
        self._ns_image: Any | None = None

    def initialize(self) -> None:
        try:
            import MediaPlayer
            import objc
            try:
                from Cocoa import NSImage, NSObject
                from Foundation import NSMutableDictionary
            except ImportError:
                from AppKit import NSImage
                from Foundation import NSMutableDictionary, NSObject
        except ImportError:
            self._logger.info("macOS media integration unavailable: PyObjC frameworks are missing")
            return

        integration = self

        class MediaCenterDelegate(NSObject):
            def init(self):
                self = objc.super(MediaCenterDelegate, self).init()
                if self is None:
                    return None
                command_center = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
                play_command = command_center.playCommand()
                pause_command = command_center.pauseCommand()
                toggle_command = command_center.togglePlayPauseCommand()
                next_command = command_center.nextTrackCommand()
                previous_command = command_center.previousTrackCommand()
                seek_command = command_center.changePlaybackPositionCommand()
                for command in (
                    play_command,
                    pause_command,
                    toggle_command,
                    next_command,
                    previous_command,
                    seek_command,
                ):
                    command.setEnabled_(True)
                play_command.addTargetWithHandler_(self.handlePlayCommand_)
                pause_command.addTargetWithHandler_(self.handlePauseCommand_)
                toggle_command.addTargetWithHandler_(self.handleTogglePlayPauseCommand_)
                next_command.addTargetWithHandler_(self.handleNextTrackCommand_)
                previous_command.addTargetWithHandler_(self.handlePreviousTrackCommand_)
                seek_command.addTargetWithHandler_(self.handleSeekCommand_)
                return self

            def handlePlayCommand_(self, event):
                integration._controller.play()
                return 1

            def handlePauseCommand_(self, event):
                integration._controller.pause()
                return 1

            def handleTogglePlayPauseCommand_(self, event):
                snapshot = integration._snapshot
                if (
                    snapshot is not None
                    and snapshot.state.status == PlaybackStatus.PLAYING
                ):
                    integration._controller.pause()
                else:
                    integration._controller.play()
                return 1

            def handleNextTrackCommand_(self, event):
                integration._controller.next()
                return 1

            def handlePreviousTrackCommand_(self, event):
                integration._controller.previous()
                return 1

            def handleSeekCommand_(self, event):
                integration._controller.seek(int(event.positionTime() * 1000))
                return 1

        self._delegate = MediaCenterDelegate.alloc().init()
        self._media_player = MediaPlayer
        self._foundation = NSMutableDictionary
        self._ns_image = NSImage
        self._initialized = True

    def update_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        self._snapshot = snapshot
        if not self._initialized or self._media_player is None or self._foundation is None:
            return
        current_item = snapshot.current_item
        if current_item is None:
            self.shutdown()
            return

        info = self._foundation.alloc().init()
        track = current_item.track
        info.setObject_forKey_(
            display_track_title(track),
            self._media_player.MPMediaItemPropertyTitle,
        )
        info.setObject_forKey_(
            ", ".join(track.artists),
            self._media_player.MPMediaItemPropertyArtist,
        )
        if track.album_title:
            info.setObject_forKey_(
                track.album_title,
                self._media_player.MPMediaItemPropertyAlbumTitle,
            )
        if track.duration_ms is not None:
            info.setObject_forKey_(
                track.duration_ms / 1000.0,
                self._media_player.MPMediaItemPropertyPlaybackDuration,
            )
        info.setObject_forKey_(
            snapshot.state.position_ms / 1000.0,
            self._media_player.MPNowPlayingInfoPropertyElapsedPlaybackTime,
        )
        playback_rate = 1.0 if snapshot.state.status == PlaybackStatus.PLAYING else 0.0
        info.setObject_forKey_(
            playback_rate,
            self._media_player.MPNowPlayingInfoPropertyPlaybackRate,
        )
        artwork = self._artwork_for_track(track.artwork_ref)
        if artwork is not None:
            info.setObject_forKey_(
                artwork,
                self._media_player.MPMediaItemPropertyArtwork,
            )
        self._media_player.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(info)

    def shutdown(self) -> None:
        if self._media_player is None:
            return
        self._media_player.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)

    def _artwork_for_track(self, artwork_ref: str | None) -> Any | None:
        if self._media_player is None or self._ns_image is None or not artwork_ref:
            return None
        artwork_url = self._artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return None
        cache_path = self._artwork_cache.cache_path_for_url(artwork_url)
        if not cache_path.exists():
            return None
        image = self._ns_image.alloc().initWithContentsOfFile_(str(cache_path))
        if image is None:
            return None
        size = image.size()
        if hasattr(self._media_player.MPMediaItemArtwork, "alloc"):
            try:
                artwork = self._media_player.MPMediaItemArtwork.alloc()
                return artwork.initWithBoundsSize_requestHandler_(
                    size,
                    lambda requested_size, ns_image=image: ns_image,
                )
            except Exception:
                pass
            try:
                return self._media_player.MPMediaItemArtwork.alloc().initWithImage_(image)
            except Exception:
                return None
        return None


class WindowsSystemMediaIntegration(SystemMediaIntegration):
    _APP_ID = "PlexMusicPlayer.PlexMusicPlayer"

    def __init__(
        self,
        *,
        playback_controller: PlaybackController,
        artwork_cache: FileArtworkCache,
        window: QWidget,
        logger: Logger,
    ) -> None:
        self._controller = playback_controller
        self._artwork_cache = artwork_cache
        self._window = window
        self._logger = logger
        self._snapshot: PlaybackSnapshot | None = None
        self._initialized = False
        self._media_player: Any | None = None
        self._smtc: Any | None = None
        self._display_updater: Any | None = None
        self._button_token: Any | None = None
        self._position_token: Any | None = None
        self._shuffle_token: Any | None = None
        self._repeat_token: Any | None = None
        self._media_playback_status: Any | None = None
        self._media_playback_type: Any | None = None
        self._media_repeat_mode: Any | None = None
        self._button_enum: Any | None = None
        self._timeline_properties_cls: Any | None = None
        self._toaster: Any | None = None
        self._toast_cls: Any | None = None
        self._toast_image_cls: Any | None = None
        self._toast_display_image_cls: Any | None = None

    def initialize(self) -> None:
        self._initialize_smtc()
        self._initialize_toasts()
        self._initialized = self._smtc is not None or self._toaster is not None
        if self._snapshot is not None:
            self.update_snapshot(self._snapshot)

    def _initialize_smtc(self) -> None:
        try:
            from winrt.windows.media import (
                MediaPlaybackAutoRepeatMode,
                MediaPlaybackStatus,
                MediaPlaybackType,
                SystemMediaTransportControlsButton,
                SystemMediaTransportControlsTimelineProperties,
            )
            from winrt.windows.media.playback import MediaPlayer
        except ImportError:
            self._logger.info(
                "Windows media integration unavailable: WinRT media bindings are missing"
            )
            return

        try:
            media_player = MediaPlayer()
            media_player.command_manager.is_enabled = False
            smtc = media_player.system_media_transport_controls
            smtc.is_enabled = True
            smtc.is_play_enabled = True
            smtc.is_pause_enabled = True
            smtc.is_next_enabled = True
            smtc.is_previous_enabled = True
            smtc.is_stop_enabled = False
            self._button_token = smtc.add_button_pressed(self._on_button_pressed)
            self._position_token = smtc.add_playback_position_change_requested(
                self._on_playback_position_change_requested
            )
            self._shuffle_token = smtc.add_shuffle_enabled_change_requested(
                self._on_shuffle_enabled_change_requested
            )
            self._repeat_token = smtc.add_auto_repeat_mode_change_requested(
                self._on_auto_repeat_mode_change_requested
            )
        except Exception as exc:  # pragma: no cover - depends on WinRT runtime context
            self._logger.info("Windows media integration unavailable: %s", exc)
            return

        self._media_player = media_player
        self._smtc = smtc
        self._display_updater = smtc.display_updater
        self._media_playback_status = MediaPlaybackStatus
        self._media_playback_type = MediaPlaybackType
        self._media_repeat_mode = MediaPlaybackAutoRepeatMode
        self._button_enum = SystemMediaTransportControlsButton
        self._timeline_properties_cls = SystemMediaTransportControlsTimelineProperties

    def _initialize_toasts(self) -> None:
        try:
            from windows_toasts import Toast, ToastDisplayImage, ToastImage, WindowsToaster
        except ImportError:
            self._logger.info("Windows toast integration unavailable: windows-toasts is missing")
            return

        try:
            self._toaster = WindowsToaster(self._APP_ID)
        except Exception as exc:  # pragma: no cover - depends on Windows notification setup
            self._logger.info("Windows toast integration unavailable: %s", exc)
            return

        self._toast_cls = Toast
        self._toast_image_cls = ToastImage
        self._toast_display_image_cls = ToastDisplayImage

    def update_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        previous_track_id = _snapshot_track_id(self._snapshot)
        self._snapshot = snapshot
        current_item = snapshot.current_item
        if current_item is None:
            self._clear_smtc()
            return

        if self._smtc is not None:
            self._update_smtc(snapshot)

        if previous_track_id and previous_track_id != current_item.track.id:
            self._show_track_toast(current_item.track)

    def _update_smtc(self, snapshot: PlaybackSnapshot) -> None:
        if (
            self._smtc is None
            or self._display_updater is None
            or self._media_playback_status is None
            or self._media_playback_type is None
            or self._media_repeat_mode is None
            or self._timeline_properties_cls is None
        ):
            return

        current_item = snapshot.current_item
        if current_item is None:
            self._clear_smtc()
            return

        track = current_item.track
        try:
            self._smtc.playback_status = _windows_playback_status(
                snapshot.state.status,
                self._media_playback_status,
            )
            self._smtc.shuffle_enabled = snapshot.state.shuffle_enabled
            self._smtc.auto_repeat_mode = _windows_repeat_mode(
                snapshot.state.repeat_mode,
                self._media_repeat_mode,
            )
            self._display_updater.type = self._media_playback_type.MUSIC
            self._display_updater.app_media_id = track.id
            music = self._display_updater.music_properties
            music.title = display_track_title(track)
            music.artist = ", ".join(track.artists)
            music.album_title = track.album_title or ""
            self._display_updater.update()

            timeline = self._timeline_properties_cls()
            timeline.start_time = timedelta(0)
            timeline.position = timedelta(milliseconds=max(0, snapshot.state.position_ms))
            if track.duration_ms is not None:
                duration = timedelta(milliseconds=max(0, track.duration_ms))
                timeline.end_time = duration
                timeline.max_seek_time = duration
            self._smtc.update_timeline_properties(timeline)
        except Exception as exc:  # pragma: no cover - depends on WinRT runtime context
            self._logger.debug("Windows media integration update failed: %s", exc)

    def _clear_smtc(self) -> None:
        if (
            self._display_updater is None
            or self._smtc is None
            or self._media_playback_status is None
        ):
            return
        try:
            self._display_updater.clear_all()
            self._display_updater.update()
            self._smtc.playback_status = self._media_playback_status.STOPPED
        except Exception as exc:  # pragma: no cover - depends on WinRT runtime context
            self._logger.debug("Windows media integration clear failed: %s", exc)

    def _show_track_toast(self, track) -> None:
        if (
            self._toaster is None
            or self._toast_cls is None
            or self._toast_image_cls is None
            or self._toast_display_image_cls is None
        ):
            return

        try:
            images = []
            artwork_path = self._artwork_path(track.artwork_ref)
            if artwork_path is not None:
                images.append(
                    self._toast_display_image_cls(self._toast_image_cls(str(artwork_path)))
                )
            toast = self._toast_cls(
                text_fields=[display_track_title(track), ", ".join(track.artists)],
                attribution_text="Plex Music Player",
                images=images,
            )
            self._toaster.show_toast(toast)
        except Exception as exc:  # pragma: no cover - depends on Windows notification setup
            self._logger.debug("Windows toast update failed: %s", exc)

    def _artwork_path(self, artwork_ref: str | None) -> Path | None:
        if not artwork_ref:
            return None
        artwork_url = self._artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return None
        cache_path = self._artwork_cache.cache_path_for_url(artwork_url)
        if cache_path.exists():
            return cache_path
        return None

    def _on_button_pressed(self, sender: Any, args: Any) -> None:
        del sender
        if self._button_enum is None:
            return
        button = args.button
        if button == self._button_enum.PLAY:
            self._controller.play()
        elif button == self._button_enum.PAUSE:
            self._controller.pause()
        elif button == self._button_enum.NEXT:
            self._controller.next()
        elif button == self._button_enum.PREVIOUS:
            self._controller.previous()
        elif button == self._button_enum.STOP:
            self._controller.pause()

    def _on_playback_position_change_requested(self, sender: Any, args: Any) -> None:
        del sender
        requested_position = getattr(args, "requested_playback_position", None)
        if requested_position is None:
            return
        self._controller.seek(_timedelta_like_to_milliseconds(requested_position))

    def _on_shuffle_enabled_change_requested(self, sender: Any, args: Any) -> None:
        del sender
        requested = getattr(args, "requested_shuffle_enabled", None)
        if requested is None:
            return
        self._controller.set_shuffle_enabled(bool(requested))

    def _on_auto_repeat_mode_change_requested(self, sender: Any, args: Any) -> None:
        del sender
        if self._media_repeat_mode is None:
            return
        requested = getattr(args, "requested_auto_repeat_mode", None)
        self._controller.set_repeat_mode(
            _repeat_mode_from_windows(requested, self._media_repeat_mode)
        )

    def shutdown(self) -> None:
        if self._smtc is not None:
            try:
                if self._button_token is not None:
                    self._smtc.remove_button_pressed(self._button_token)
                if self._position_token is not None:
                    self._smtc.remove_playback_position_change_requested(self._position_token)
                if self._shuffle_token is not None:
                    self._smtc.remove_shuffle_enabled_change_requested(self._shuffle_token)
                if self._repeat_token is not None:
                    self._smtc.remove_auto_repeat_mode_change_requested(self._repeat_token)
                self._clear_smtc()
                self._smtc.is_enabled = False
            except Exception as exc:  # pragma: no cover - depends on WinRT runtime context
                self._logger.debug("Windows media integration shutdown failed: %s", exc)
        if self._media_player is not None and hasattr(self._media_player, "close"):
            try:
                self._media_player.close()
            except Exception:
                pass


@dataclass(slots=True)
class _MprisState:
    playback_status: str = "Stopped"
    metadata: dict[str, Any] | None = None
    position_us: int = 0
    volume: float = 1.0
    shuffle: bool = False
    loop_status: str = "None"
    current_track_id: str | None = None


class LinuxMprisIntegration(SystemMediaIntegration):
    _BUS_NAME = "org.mpris.MediaPlayer2.plexmusicplayer"
    _OBJECT_PATH = "/org/mpris/MediaPlayer2"

    def __init__(
        self,
        *,
        playback_controller: PlaybackController,
        artwork_cache: FileArtworkCache,
        window: QWidget,
        logger: Logger,
    ) -> None:
        self._controller = playback_controller
        self._artwork_cache = artwork_cache
        self._window = window
        self._logger = logger
        self._state = _MprisState(metadata={})
        self._root_object: QObject | None = None
        self._connection: QDBusConnection | None = None
        self._registered = False
        self._root_adaptor: _MprisRootAdaptor | None = None
        self._player_adaptor: _MprisPlayerAdaptor | None = None

    def initialize(self) -> None:
        if QDBusConnection is None:
            self._logger.info("Linux media integration unavailable: QtDBus is missing")
            return
        connection = QDBusConnection.sessionBus()
        if not connection.isConnected():
            self._logger.info("Linux media integration unavailable: no D-Bus session bus")
            return
        if not connection.registerService(self._BUS_NAME):
            self._logger.info(
                "Linux media integration unavailable: could not register MPRIS bus name"
            )
            return
        self._connection = connection
        self._root_object = QObject()
        self._root_adaptor = _MprisRootAdaptor(self)
        self._player_adaptor = _MprisPlayerAdaptor(self)
        self._registered = connection.registerObject(
            self._OBJECT_PATH,
            self._root_object,
            QDBusConnection.RegisterOption.ExportAdaptors,
        )
        if not self._registered:
            connection.unregisterService(self._BUS_NAME)
            self._logger.info(
                "Linux media integration unavailable: could not register MPRIS object"
            )

    def update_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        current_item = snapshot.current_item
        if current_item is None:
            self._state = _MprisState(metadata={})
            self._emit_properties_changed()
            return
        self._state = _MprisState(
            playback_status=_mpris_playback_status(snapshot.state.status),
            metadata=self._metadata_for_snapshot(snapshot, current_item.track),
            position_us=snapshot.state.position_ms * 1000,
            volume=max(0.0, min(1.0, snapshot.state.volume / 100.0)),
            shuffle=snapshot.state.shuffle_enabled,
            loop_status=_mpris_loop_status(snapshot.state.repeat_mode),
            current_track_id=current_item.track.id,
        )
        self._emit_properties_changed()

    def shutdown(self) -> None:
        if self._connection is None:
            return
        self._connection.unregisterObject(self._OBJECT_PATH)
        self._connection.unregisterService(self._BUS_NAME)

    def _emit_properties_changed(self) -> None:
        if self._connection is None:
            return
        message = QDBusMessage.createSignal(
            self._OBJECT_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
        )
        message.setArguments(
            [
                "org.mpris.MediaPlayer2.Player",
                {
                    "PlaybackStatus": self._state.playback_status,
                    "Metadata": self._state.metadata or {},
                    "Position": self._state.position_us,
                    "Volume": self._state.volume,
                    "Shuffle": self._state.shuffle,
                    "LoopStatus": self._state.loop_status,
                },
                [],
            ]
        )
        self._connection.send(message)

    def _metadata_for_snapshot(self, snapshot: PlaybackSnapshot, track) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "mpris:trackid": self._track_object_path(track.id),
            "xesam:title": display_track_title(track),
            "xesam:artist": list(track.artists),
        }
        if track.album_title:
            metadata["xesam:album"] = track.album_title
        if track.duration_ms is not None:
            metadata["mpris:length"] = track.duration_ms * 1000
        art_url = self._art_url_for_track(track.artwork_ref)
        if art_url:
            metadata["mpris:artUrl"] = art_url
        return metadata

    def _art_url_for_track(self, artwork_ref: str | None) -> str | None:
        if not artwork_ref:
            return None
        artwork_url = self._artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return None
        cache_path = self._artwork_cache.cache_path_for_url(artwork_url)
        if cache_path.exists():
            return Path(cache_path).as_uri()
        return artwork_url

    def _track_object_path(self, track_id: str):
        encoded_id = quote(track_id, safe="")
        from PySide6.QtDBus import QDBusObjectPath

        return QDBusObjectPath(f"/app/plexmusicplayer/track/{encoded_id}")

    def raise_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def quit_window(self) -> None:
        self._window.close()


@ClassInfo({"D-Bus Interface": "org.mpris.MediaPlayer2"})
class _MprisRootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, integration: LinuxMprisIntegration) -> None:
        assert integration._root_object is not None
        super().__init__(integration._root_object)
        self._integration = integration

    @Slot()
    def Raise(self) -> None:
        self._integration.raise_window()

    @Slot()
    def Quit(self) -> None:
        self._integration.quit_window()

    @Property(bool, constant=True)
    def CanQuit(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanRaise(self) -> bool:
        return True

    @Property(bool, constant=True)
    def HasTrackList(self) -> bool:
        return False

    @Property(str, constant=True)
    def Identity(self) -> str:
        return "PlexMusicPlayer"

    @Property(str, constant=True)
    def DesktopEntry(self) -> str:
        return "plex-music-player"

    @Property(list, constant=True)
    def SupportedUriSchemes(self) -> list[str]:
        return []

    @Property(list, constant=True)
    def SupportedMimeTypes(self) -> list[str]:
        return []


@ClassInfo({"D-Bus Interface": "org.mpris.MediaPlayer2.Player"})
class _MprisPlayerAdaptor(QDBusAbstractAdaptor):
    def __init__(self, integration: LinuxMprisIntegration) -> None:
        assert integration._root_object is not None
        super().__init__(integration._root_object)
        self._integration = integration

    @Slot()
    def Next(self) -> None:
        self._integration._controller.next()

    @Slot()
    def Previous(self) -> None:
        self._integration._controller.previous()

    @Slot()
    def Pause(self) -> None:
        self._integration._controller.pause()

    @Slot()
    def PlayPause(self) -> None:
        if self.PlaybackStatus == "Playing":
            self._integration._controller.pause()
            return
        self._integration._controller.play()

    @Slot()
    def Stop(self) -> None:
        self._integration._controller.pause()

    @Slot()
    def Play(self) -> None:
        self._integration._controller.play()

    @Slot(int)
    def Seek(self, offset_us: int) -> None:
        position_ms = max(0, (self._integration._state.position_us + offset_us) // 1000)
        self._integration._controller.seek(int(position_ms))

    @Slot(str, int)
    def SetPosition(self, track_id: str, position_us: int) -> None:
        if track_id and self.Metadata.get("mpris:trackid") and track_id != str(
            self.Metadata["mpris:trackid"].path()
        ):
            return
        self._integration._controller.seek(max(0, position_us // 1000))

    @Slot(str)
    def OpenUri(self, uri: str) -> None:
        del uri

    @Property(str)
    def PlaybackStatus(self) -> str:
        return self._integration._state.playback_status

    @Property(str)
    def LoopStatus(self) -> str:
        return self._integration._state.loop_status

    @Property(float, constant=True)
    def Rate(self) -> float:
        return 1.0

    @Property(bool)
    def Shuffle(self) -> bool:
        return self._integration._state.shuffle

    @Property(dict)
    def Metadata(self) -> dict[str, Any]:
        return self._integration._state.metadata or {}

    @Property(float)
    def Volume(self) -> float:
        return self._integration._state.volume

    @Property(int)
    def Position(self) -> int:
        return self._integration._state.position_us

    @Property(float, constant=True)
    def MinimumRate(self) -> float:
        return 1.0

    @Property(float, constant=True)
    def MaximumRate(self) -> float:
        return 1.0

    @Property(bool, constant=True)
    def CanGoNext(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanGoPrevious(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanPlay(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanPause(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanSeek(self) -> bool:
        return True

    @Property(bool, constant=True)
    def CanControl(self) -> bool:
        return True


def _mpris_playback_status(status: PlaybackStatus) -> str:
    if status == PlaybackStatus.PLAYING:
        return "Playing"
    if status == PlaybackStatus.PAUSED:
        return "Paused"
    return "Stopped"


def _mpris_loop_status(mode: RepeatMode) -> str:
    if mode == RepeatMode.ONE:
        return "Track"
    if mode == RepeatMode.ALL:
        return "Playlist"
    return "None"


def _windows_playback_status(status: PlaybackStatus, media_playback_status: Any) -> Any:
    if status == PlaybackStatus.PLAYING:
        return media_playback_status.PLAYING
    if status == PlaybackStatus.PAUSED:
        return media_playback_status.PAUSED
    return media_playback_status.STOPPED


def _windows_repeat_mode(mode: RepeatMode, media_repeat_mode: Any) -> Any:
    if mode == RepeatMode.ONE:
        return media_repeat_mode.TRACK
    if mode == RepeatMode.ALL:
        return media_repeat_mode.LIST
    return media_repeat_mode.NONE


def _repeat_mode_from_windows(mode: Any, media_repeat_mode: Any) -> RepeatMode:
    if mode == media_repeat_mode.TRACK:
        return RepeatMode.ONE
    if mode == media_repeat_mode.LIST:
        return RepeatMode.ALL
    return RepeatMode.OFF


def _timedelta_like_to_milliseconds(value: Any) -> int:
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        return max(0, int(total_seconds() * 1000))
    return 0


def _snapshot_track_id(snapshot: PlaybackSnapshot | None) -> str | None:
    if snapshot is None or snapshot.current_item is None:
        return None
    return snapshot.current_item.track.id

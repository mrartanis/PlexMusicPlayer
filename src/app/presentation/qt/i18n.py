from __future__ import annotations

import locale
import plistlib
import sys
from os import environ
from pathlib import Path

from PySide6.QtCore import QLocale

_SUPPORTED_LANGUAGES = {"en", "ru"}
_SUPPORTED_PREFERENCES = {"system", "en", "ru"}

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "action.add_to_queue": "Add to queue",
        "action.append_all": "Append all",
        "action.back": "Back",
        "action.clear_queue": "Clear queue",
        "action.close": "Close",
        "action.copy_share_link": "Copy share link",
        "action.exit_full_screen": "Exit Full Screen",
        "action.export_playlist": "Export playlist",
        "action.full_screen": "Full Screen",
        "action.go_to_album": "Go to album",
        "action.go_to_artist": "Go to artist",
        "action.like": "Like",
        "action.logout": "Logout",
        "action.maximize": "Maximize",
        "action.minimize": "Minimize",
        "action.next": "Next",
        "action.pause": "Pause",
        "action.play": "Play",
        "action.play_all": "Play all",
        "action.play_next": "Play next",
        "action.previous": "Previous",
        "action.remove_from_queue": "Remove from queue",
        "action.restore": "Restore",
        "action.search": "Search",
        "action.settings": "Settings",
        "action.shuffle_queue": "Shuffle queue",
        "action.start_album_radio": "Start album radio",
        "action.start_artist_radio": "Start artist radio",
        "action.start_track_radio": "Start track radio",
        "action.toggle_navigation": "Toggle navigation",
        "action.unlike": "Unlike",
        "action.volume": "Volume",
        "app.auth_dialog.status": (
            "Sign in to Plex with a PIN code, then choose a server and music library."
        ),
        "app.auth_dialog.title": "Plex Login",
        "app.title": "Plex Music Player",
        "browser.empty": "No items",
        "browser.loading": "Loading...",
        "browser.placeholder.recent_searches": "History",
        "browser.placeholder.search": "Search Plex Library",
        "label.album": "Album",
        "label.artist_metadata": "Artist metadata will appear here",
        "label.discovery": "Discovery",
        "label.library": "Library",
        "label.login_required": "Login required",
        "label.no_cover": "No cover",
        "label.no_track_selected": "No track selected",
        "label.playback_state.stopped": "Stopped",
        "label.queue_idle": "Queue idle",
        "label.starter_signal": "Starter Signal",
        "label.unknown_artist": "Unknown artist",
        "library.artist": "Artist",
        "library.artist_compilations_title": "Artist: {name} | Compilations",
        "library.artist_playlists_title": "Artist: {name} | Playlists",
        "library.artist_radio": "Artist Radio",
        "library.artist_radio_item": "{name} Radio",
        "library.artist_radio_subtitle": "Artist radio",
        "library.artist_singles_title": "Artist: {name} | Singles",
        "library.artist_top_tracks_title": "Artist: {name} | Top Tracks",
        "library.artist_albums_title": "Artist: {name} | Albums",
        "library.list.my_albums": "Albums",
        "library.list.my_artists": "Artists",
        "library.list.my_tracks": "Liked Tracks",
        "library.list.playlists": "Playlists",
        "library.radio": "Radio",
        "library.radio_item": "{name} Radio",
        "library.search": "Search",
        "library.search_title": "Search: {query}",
        "library.tab.albums": "Albums",
        "library.tab.artist_radio": "Artist Radio",
        "library.tab.artists": "Artists",
        "library.tab.compilations": "Compilations",
        "library.tab.playlists": "Playlists",
        "library.tab.singles": "Singles",
        "library.tab.top_tracks": "Top Tracks",
        "library.tab.tracks": "Tracks",
        "library.track": "Track",
        "library.track_count": "{count} tracks",
        "nav.my_albums": "Albums",
        "nav.my_artists": "Artists",
        "nav.my_tracks": "Liked Tracks",
        "nav.my_wave": "Random Mix",
        "nav.playlists": "Playlists",
        "settings.corner_style": "Corner style: {value}",
        "settings.language": "Language",
        "settings.language_preference": "Language: {value}",
        "settings.option.corner.rounded": "Rounded",
        "settings.option.corner.straight": "Straight",
        "settings.option.language.en": "English",
        "settings.option.language.ru": "Russian",
        "settings.option.language.system": "System",
        "settings.option.theme.dark": "Dark",
        "settings.option.theme.light": "Light",
        "settings.option.theme.system": "System",
        "settings.option.waveform_progress.disabled": "Off",
        "settings.option.waveform_progress.enabled": "On",
        "settings.quality": "Quality",
        "settings.section.corners": "Corners",
        "settings.section.language": "Language",
        "settings.section.theme": "Theme",
        "settings.section.waveform_progress": "Waveformed Progress",
        "settings.theme": "Theme preference: {value}",
        "settings.waveform_progress": "Waveformed progress: {value}",
        "status.audio_quality": "Audio quality: {value}",
        "status.authenticated_as": "Authenticated as {username}",
        "status.copied_share_link": "Copied share link: {link}",
        "status.export_playlist.empty": "Queue is empty",
        "status.export_playlist.error": "Playlist export failed: {message}",
        "status.export_playlist.saved": "Playlist exported: {path}",
        "status.loading_full_source": "Loading full source...",
        "status.loading_source_start": "Loading {title}...",
        "status.loading_source_progress": "Loading {title}: queued {count} tracks...",
        "status.loading_source_complete": "Loaded {title}: queued {count} tracks",
        "status.library_error": "Library error: {message}",
        "status.library_select_track": "Library error: select or play a track first",
        "status.logged_out": "Logged out",
        "status.playback_error": "Playback error: {message}",
        "status.prompt_select_track": "Select or play a track first",
        "status.queue_summary": "{count} tracks | {duration}",
        "status.track.like": "Liked: {title}",
        "status.track.unlike": "Unliked: {title}",
        "status.album.like": "Liked album: {title}",
        "status.album.unlike": "Unliked album: {title}",
        "status.artist.like": "Liked artist: {name}",
        "status.artist.unlike": "Unliked artist: {name}",
        "status.playlist.like": "Liked playlist: {title}",
        "status.playlist.unlike": "Unliked playlist: {title}",
        "status.auth_error": "Auth error: {message}",
        "track.choose_music": "Choose music from Random Mix, library, or search",
        "track.tooltip.like": "Like current track",
        "track.tooltip.unlike": "Unlike current track",
        "dialog.export_playlist.title": "Export playlist",
        "window.player": "Main Player",
        "window.queue": "Queue",
        "window.search_library": "Search / Library",
        "window.navigation": "Navigation",
    },
    "ru": {
        "action.add_to_queue": "Добавить в очередь",
        "action.append_all": "Добавить всё",
        "action.back": "Назад",
        "action.clear_queue": "Очистить очередь",
        "action.close": "Закрыть",
        "action.copy_share_link": "Скопировать ссылку",
        "action.exit_full_screen": "Выйти из полноэкранного режима",
        "action.export_playlist": "Экспортировать плейлист",
        "action.full_screen": "На весь экран",
        "action.go_to_album": "Перейти к альбому",
        "action.go_to_artist": "Перейти к артисту",
        "action.like": "Лайк",
        "action.logout": "Выйти",
        "action.maximize": "Развернуть",
        "action.minimize": "Свернуть",
        "action.next": "Следующий",
        "action.pause": "Пауза",
        "action.play": "Играть",
        "action.play_all": "Играть всё",
        "action.play_next": "Играть следующим",
        "action.previous": "Предыдущий",
        "action.remove_from_queue": "Убрать из очереди",
        "action.restore": "Восстановить",
        "action.search": "Поиск",
        "action.settings": "Настройки",
        "action.shuffle_queue": "Перемешать очередь",
        "action.start_album_radio": "Запустить радио по альбому",
        "action.start_artist_radio": "Запустить радио по артисту",
        "action.start_track_radio": "Запустить радио по треку",
        "action.toggle_navigation": "Переключить навигацию",
        "action.unlike": "Убрать лайк",
        "action.volume": "Громкость",
        "app.auth_dialog.status": (
            "Войдите в Plex по PIN-коду, затем выберите сервер и музыкальную библиотеку."
        ),
        "app.auth_dialog.title": "Вход в Plex",
        "app.title": "Plex Music Player",
        "browser.empty": "Ничего не найдено",
        "browser.loading": "Загрузка...",
        "browser.placeholder.recent_searches": "История",
        "browser.placeholder.search": "Искать в Plex",
        "label.album": "Альбом",
        "label.artist_metadata": "Здесь появятся данные об артисте",
        "label.discovery": "Открытия",
        "label.library": "Библиотека",
        "label.login_required": "Требуется вход",
        "label.no_cover": "Нет обложки",
        "label.no_track_selected": "Трек не выбран",
        "label.playback_state.stopped": "Остановлено",
        "label.queue_idle": "Очередь пуста",
        "label.starter_signal": "Стартовый сигнал",
        "label.unknown_artist": "Неизвестный артист",
        "library.artist": "Артист",
        "library.artist_albums_title": "Артист: {name} | Альбомы",
        "library.artist_compilations_title": "Артист: {name} | Сборники",
        "library.artist_playlists_title": "Артист: {name} | Плейлисты",
        "library.artist_radio": "Радио артиста",
        "library.artist_radio_item": "Радио {name}",
        "library.artist_radio_subtitle": "Радио артиста",
        "library.artist_singles_title": "Артист: {name} | Синглы",
        "library.artist_top_tracks_title": "Артист: {name} | Топ треки",
        "library.list.my_albums": "Альбомы",
        "library.list.my_artists": "Артисты",
        "library.list.my_tracks": "Любимые треки",
        "library.list.playlists": "Плейлисты",
        "library.radio": "Радио",
        "library.radio_item": "Радио {name}",
        "library.search": "Поиск",
        "library.search_title": "Поиск: {query}",
        "library.tab.albums": "Альбомы",
        "library.tab.artist_radio": "Радио артиста",
        "library.tab.artists": "Артисты",
        "library.tab.compilations": "Сборники",
        "library.tab.playlists": "Плейлисты",
        "library.tab.singles": "Синглы",
        "library.tab.top_tracks": "Топ треки",
        "library.tab.tracks": "Треки",
        "library.track": "Трек",
        "library.track_count": "{count} треков",
        "nav.my_albums": "Альбомы",
        "nav.my_artists": "Артисты",
        "nav.my_tracks": "Любимые треки",
        "nav.my_wave": "Случайный микс",
        "nav.playlists": "Плейлисты",
        "settings.corner_style": "Стиль углов: {value}",
        "settings.language": "Язык: {value}",
        "settings.language_preference": "Язык: {value}",
        "settings.option.corner.rounded": "Скруглённые",
        "settings.option.corner.straight": "Прямые",
        "settings.option.language.en": "English",
        "settings.option.language.ru": "Русский",
        "settings.option.language.system": "Системный",
        "settings.option.theme.dark": "Тёмная",
        "settings.option.theme.light": "Светлая",
        "settings.option.theme.system": "Системная",
        "settings.option.waveform_progress.disabled": "Выкл",
        "settings.option.waveform_progress.enabled": "Вкл",
        "settings.quality": "Качество",
        "settings.section.corners": "Углы",
        "settings.section.language": "Язык",
        "settings.section.theme": "Тема",
        "settings.section.waveform_progress": "Waveform-прогресс",
        "settings.theme": "Тема: {value}",
        "settings.waveform_progress": "Waveform-прогресс: {value}",
        "status.audio_quality": "Качество звука: {value}",
        "status.authenticated_as": "Вошли как {username}",
        "status.copied_share_link": "Ссылка скопирована: {link}",
        "status.export_playlist.empty": "Очередь пуста",
        "status.export_playlist.error": "Не удалось экспортировать плейлист: {message}",
        "status.export_playlist.saved": "Плейлист экспортирован: {path}",
        "status.loading_full_source": "Загружаю весь источник...",
        "status.loading_source_start": "Загружаю {title}...",
        "status.loading_source_progress": "Загружаю {title}: добавлено {count} треков...",
        "status.loading_source_complete": "Загрузил {title}: добавлено {count} треков",
        "status.library_error": "Ошибка библиотеки: {message}",
        "status.library_select_track": "Ошибка библиотеки: сначала выберите или запустите трек",
        "status.logged_out": "Вы вышли из аккаунта",
        "status.playback_error": "Ошибка воспроизведения: {message}",
        "status.prompt_select_track": "Сначала выберите или запустите трек",
        "status.queue_summary": "{count} треков | {duration}",
        "status.track.like": "Лайк: {title}",
        "status.track.unlike": "Убрали лайк: {title}",
        "status.album.like": "Лайк альбому: {title}",
        "status.album.unlike": "Убрали лайк у альбома: {title}",
        "status.artist.like": "Лайк артисту: {name}",
        "status.artist.unlike": "Убрали лайк у артиста: {name}",
        "status.playlist.like": "Лайк плейлисту: {title}",
        "status.playlist.unlike": "Убрали лайк у плейлиста: {title}",
        "status.auth_error": "Ошибка входа: {message}",
        "track.choose_music": "Выберите музыку из случайного микса, библиотеки или поиска",
        "track.tooltip.like": "Поставить лайк текущему треку",
        "track.tooltip.unlike": "Убрать лайк у текущего трека",
        "dialog.export_playlist.title": "Экспортировать плейлист",
        "window.navigation": "Навигация",
        "window.player": "Основной плеер",
        "window.queue": "Очередь",
        "window.search_library": "Поиск / Библиотека",
    },
}


def normalize_language_preference(value: str | None) -> str:
    if value in _SUPPORTED_PREFERENCES:
        return value
    return "system"


def detect_language_from_locale_name(locale_name: str | None) -> str:
    normalized = (locale_name or "").strip().lower().replace("-", "_")
    if normalized.startswith("ru"):
        return "ru"
    return "en"


def _resolve_macos_system_language() -> str | None:
    preferences_path = Path.home() / "Library/Preferences/.GlobalPreferences.plist"
    try:
        with preferences_path.open("rb") as handle:
            preferences = plistlib.load(handle)
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return None

    languages = preferences.get("AppleLanguages")
    if isinstance(languages, list):
        for language in languages:
            if isinstance(language, str) and language.strip():
                return detect_language_from_locale_name(language)

    locale_name = preferences.get("AppleLocale")
    if isinstance(locale_name, str) and locale_name.strip():
        return detect_language_from_locale_name(locale_name)
    return None


def resolve_system_language() -> str:
    if sys.platform == "darwin":
        language = _resolve_macos_system_language()
        if language is not None:
            return language
    candidates = [
        QLocale.system().name(),
        QLocale.system().bcp47Name(),
        environ.get("LC_ALL"),
        environ.get("LC_MESSAGES"),
        environ.get("LANG"),
        locale.getlocale()[0],
    ]
    for candidate in candidates:
        if candidate:
            return detect_language_from_locale_name(candidate)
    return "en"


def resolve_language(preference: str | None) -> str:
    normalized = normalize_language_preference(preference)
    if normalized == "system":
        return resolve_system_language()
    if normalized in _SUPPORTED_LANGUAGES:
        return normalized
    return "en"


class UiTextCatalog:
    def __init__(self, *, settings_service) -> None:
        self._settings_service = settings_service

    def language_preference(self) -> str:
        return self._settings_service.load_language_preference()

    def resolved_language(self) -> str:
        return resolve_language(self.language_preference())

    def text(self, key: str, **params: object) -> str:
        language = self.resolved_language()
        template = _STRINGS.get(language, {}).get(key) or _STRINGS["en"].get(key) or key
        return template.format(**params)

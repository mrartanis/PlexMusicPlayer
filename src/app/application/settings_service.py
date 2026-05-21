from __future__ import annotations

from app.domain import AudioQuality, Logger, SettingsRepo
from app.domain.errors import StorageError


class SettingsService:
    _VOLUME_KEY = "volume"
    _AUDIO_QUALITY_KEY = "audio_quality"
    _THEME_KEY = "theme"
    _CORNER_STYLE_KEY = "corner_style"
    _LANGUAGE_KEY = "language"
    _MY_WAVE_HISTORY_KEY = "my_wave_history"
    _WAVEFORM_PROGRESS_KEY = "waveform_progress"

    def __init__(self, *, settings_repo: SettingsRepo, logger: Logger) -> None:
        self._settings_repo = settings_repo
        self._logger = logger

    def load_volume(self, *, default: int = 100) -> int:
        value = self._load_value(self._VOLUME_KEY)
        if not isinstance(value, int):
            return default
        return max(0, min(100, value))

    def save_volume(self, volume: int) -> None:
        self._save_value(self._VOLUME_KEY, max(0, min(100, volume)))

    def load_audio_quality(self, *, default: AudioQuality = AudioQuality.HQ) -> AudioQuality:
        value = self._load_value(self._AUDIO_QUALITY_KEY)
        if not isinstance(value, str):
            return default
        try:
            return AudioQuality(value)
        except ValueError:
            return default

    def save_audio_quality(self, quality: AudioQuality) -> None:
        self._save_value(self._AUDIO_QUALITY_KEY, quality.value)

    def load_theme_preference(
        self,
        *,
        default: str = "system",
    ) -> str:
        value = self._load_value(self._THEME_KEY)
        if not isinstance(value, str):
            return default
        if value not in {"system", "light", "dark"}:
            return default
        return value

    def save_theme_preference(self, theme: str) -> None:
        if theme not in {"system", "light", "dark"}:
            theme = "system"
        self._save_value(self._THEME_KEY, theme)

    def load_corner_style_preference(
        self,
        *,
        default: str = "straight",
    ) -> str:
        value = self._load_value(self._CORNER_STYLE_KEY)
        if not isinstance(value, str):
            return default
        if value not in {"straight", "rounded"}:
            return default
        return value

    def save_corner_style_preference(self, corner_style: str) -> None:
        if corner_style not in {"straight", "rounded"}:
            corner_style = "straight"
        self._save_value(self._CORNER_STYLE_KEY, corner_style)

    def load_language_preference(
        self,
        *,
        default: str = "system",
    ) -> str:
        value = self._load_value(self._LANGUAGE_KEY)
        if not isinstance(value, str):
            return default
        if value not in {"system", "en", "ru"}:
            return default
        return value

    def save_language_preference(self, language: str) -> None:
        if language not in {"system", "en", "ru"}:
            language = "system"
        self._save_value(self._LANGUAGE_KEY, language)

    def load_my_wave_history(self) -> list[str]:
        value = self._load_value(self._MY_WAVE_HISTORY_KEY)
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                continue
            normalized = entry.strip()
            if len(normalized) == 7 and normalized.startswith("#"):
                result.append(normalized.lower())
        return result

    def save_my_wave_history(self, samples: list[str]) -> None:
        normalized: list[str] = []
        for sample in samples:
            if not isinstance(sample, str):
                continue
            value = sample.strip()
            if len(value) == 7 and value.startswith("#"):
                normalized.append(value.lower())
        self._save_value(self._MY_WAVE_HISTORY_KEY, normalized)

    def load_waveform_progress_enabled(self, *, default: bool = False) -> bool:
        value = self._load_value(self._WAVEFORM_PROGRESS_KEY)
        if not isinstance(value, bool):
            return default
        return value

    def save_waveform_progress_enabled(self, enabled: bool) -> None:
        self._save_value(self._WAVEFORM_PROGRESS_KEY, bool(enabled))

    def _load_value(self, key: str) -> object | None:
        try:
            settings = self._settings_repo.load_settings()
        except StorageError as exc:
            self._logger.warning("Failed to load setting %s: %s", key, exc)
            return None
        return settings.get(key)

    def _save_value(self, key: str, value: object) -> None:
        try:
            settings = dict(self._settings_repo.load_settings())
            settings[key] = value
            self._settings_repo.save_settings(settings)
        except StorageError as exc:
            self._logger.warning("Failed to save setting %s: %s", key, exc)

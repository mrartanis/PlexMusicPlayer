from __future__ import annotations

from app.presentation.qt.i18n import (
    UiTextCatalog,
    detect_language_from_locale_name,
    normalize_language_preference,
    resolve_language,
    resolve_system_language,
)


class StubSettingsService:
    def __init__(self, language: str) -> None:
        self._language = language

    def load_language_preference(self) -> str:
        return self._language


def test_detect_language_from_locale_name_defaults_to_english() -> None:
    assert detect_language_from_locale_name("en_US") == "en"
    assert detect_language_from_locale_name("de_DE.UTF-8") == "en"
    assert detect_language_from_locale_name(None) == "en"


def test_detect_language_from_locale_name_accepts_russian_variants() -> None:
    assert detect_language_from_locale_name("ru_RU") == "ru"
    assert detect_language_from_locale_name("ru-RS") == "ru"


def test_normalize_and_resolve_language_preference() -> None:
    assert normalize_language_preference("ru") == "ru"
    assert normalize_language_preference("jp") == "system"
    assert resolve_language("en") == "en"
    assert resolve_language("ru") == "ru"


def test_ui_text_catalog_formats_translated_strings() -> None:
    catalog = UiTextCatalog(settings_service=StubSettingsService("ru"))

    assert catalog.text("action.search") == "Поиск"
    assert catalog.text("status.authenticated_as", username="alice") == "Вошли как alice"


def test_resolve_system_language_uses_linux_locale_environment(monkeypatch) -> None:
    class StubLocale:
        @staticmethod
        def system():
            class StubSystemLocale:
                @staticmethod
                def name() -> str:
                    return ""

                @staticmethod
                def bcp47Name() -> str:
                    return ""

            return StubSystemLocale()

    monkeypatch.setattr("app.presentation.qt.i18n.QLocale", StubLocale)
    monkeypatch.setattr("app.presentation.qt.i18n.sys.platform", "linux")
    monkeypatch.setattr("app.presentation.qt.i18n.locale.getlocale", lambda: (None, None))
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LC_MESSAGES", "ru_RU.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")

    assert resolve_system_language() == "ru"


def test_resolve_system_language_prefers_macos_apple_languages(monkeypatch, tmp_path) -> None:
    preferences_dir = tmp_path / "Library" / "Preferences"
    preferences_dir.mkdir(parents=True)
    preferences_path = preferences_dir / ".GlobalPreferences.plist"
    preferences_path.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        b'<plist version="1.0"><dict>'
        b"<key>AppleLanguages</key><array><string>en</string></array>"
        b"<key>AppleLocale</key><string>ru_RU</string>"
        b"</dict></plist>"
    )

    monkeypatch.setattr("app.presentation.qt.i18n.sys.platform", "darwin")
    monkeypatch.setattr("app.presentation.qt.i18n.Path.home", lambda: tmp_path)
    monkeypatch.setenv("LC_ALL", "ru_RU.UTF-8")
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")

    assert resolve_system_language() == "en"

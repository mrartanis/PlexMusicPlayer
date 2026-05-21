from app.bootstrap.startup import build_startup_context


def test_main_window_can_be_constructed(qtbot, qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_PLAYBACK_BACKEND", "fake")

    context = build_startup_context(argv=["yaymp-test"], existing_qt_app=qapp)

    qtbot.addWidget(context.main_window)
    context.main_window.show()

    assert context.main_window.windowTitle() == "Plex Music Player"
    assert context.container.config.settings_file.name == "settings.json"
    assert context.container.services.settings_service.load_volume() == 100
    assert context.main_window.isVisible()
    context.main_window._set_theme_preference("light")

    assert context.container.services.settings_service.load_theme_preference() == "light"
    assert "#f5f7fb" in context.main_window.styleSheet()

from PySide6.QtGui import QColor

from app.presentation.qt.my_wave_button import MyWaveButton


def test_my_wave_button_seeds_full_history(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)

    button.set_visuals(
        accent="#ff0000",
        accent_text="#ffffff",
        trailing="#0000ff",
        rounded=True,
        theme_mode="light",
    )

    assert button._history_samples == []


def test_my_wave_button_advances_only_after_two_seconds(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)
    button.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )
    button.sync_playback(enabled=True, track_id="track-1", position_ms=0, accent="#00ff00")
    button.sync_playback(enabled=True, track_id="track-1", position_ms=1_000, accent="#00ff00")

    assert button._history_samples == []

    button.sync_playback(enabled=True, track_id="track-1", position_ms=2_000, accent="#00ff00")

    assert button._history_samples[0] == QColor("#00ff00")


def test_my_wave_button_tracks_current_accent_until_history_starts(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)
    button.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )

    button.set_visuals(
        accent="#ff6600",
        accent_text="#ffffff",
        trailing="#202020",
        rounded=True,
        theme_mode="light",
    )

    assert button._history_samples == []


def test_my_wave_button_preserves_history_when_paused_or_switched_off(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)
    button.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )
    button.sync_playback(enabled=True, track_id="track-1", position_ms=0, accent="#ffaa00")
    button.sync_playback(enabled=True, track_id="track-1", position_ms=2_000, accent="#ffaa00")
    frozen_head = QColor(button._history_samples[0])

    button.sync_playback(enabled=False, track_id=None, position_ms=0, accent="#00ff00")

    assert button._history_samples[0] == frozen_head


def test_my_wave_button_ignores_large_seek_jumps(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)
    button.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )
    button.sync_playback(enabled=True, track_id="track-1", position_ms=0, accent="#ff00ff")
    button.sync_playback(enabled=True, track_id="track-1", position_ms=12_000, accent="#ff00ff")

    assert button._history_samples == []


def test_my_wave_button_resets_step_accumulator_on_track_change(qtbot) -> None:
    button = MyWaveButton("Random Mix")
    qtbot.addWidget(button)
    button.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )

    button.sync_playback(enabled=True, track_id="track-1", position_ms=0, accent="#ff0000")
    button.sync_playback(enabled=True, track_id="track-1", position_ms=1_000, accent="#ff0000")
    button.sync_playback(enabled=True, track_id="track-2", position_ms=0, accent="#00ff00")
    button.sync_playback(enabled=True, track_id="track-2", position_ms=1_000, accent="#00ff00")

    assert button._history_samples == []

    button.sync_playback(enabled=True, track_id="track-2", position_ms=2_000, accent="#00ff00")

    assert button._history_samples[0] == QColor("#00ff00")


def test_my_wave_button_exports_and_restores_history(qtbot) -> None:
    source = MyWaveButton("Random Mix")
    qtbot.addWidget(source)
    source.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )
    source.sync_playback(enabled=True, track_id="track-1", position_ms=0, accent="#ff0000")
    source.sync_playback(enabled=True, track_id="track-1", position_ms=2_000, accent="#ff0000")
    source.sync_playback(enabled=True, track_id="track-1", position_ms=4_000, accent="#00ff00")

    restored = MyWaveButton("Random Mix")
    qtbot.addWidget(restored)
    restored.set_visuals(
        accent="#526ee8",
        accent_text="#ffffff",
        trailing="#d8e2f8",
        rounded=True,
        theme_mode="light",
    )
    restored.restore_history(source.export_history())

    assert restored.export_history() == source.export_history()

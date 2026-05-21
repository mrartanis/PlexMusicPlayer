from __future__ import annotations

import ctypes.util
import os
import sys
from pathlib import Path

import pytest

from app.infrastructure.playback import mpv_loader
from app.infrastructure.playback.mpv_loader import ensure_mpv_available, load_mpv_module


@pytest.mark.skipif(
    os.getenv("PLEX_MUSIC_PLAYER_ENABLE_MPV_TESTS") != "1",
    reason="MPV availability checks are enabled only in environments that provide libmpv.",
)
def test_mpv_loader_resolves_python_binding_and_system_library() -> None:
    module, library_path = ensure_mpv_available()

    assert module is not None
    assert hasattr(module, "MPV")
    assert library_path


def test_mpv_loader_patches_find_library_for_explicit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    bundled_path = "/tmp/bundled/libmpv.so.1"

    def fake_import_module(name: str):
        assert name == "mpv"
        assert ctypes.util.find_library("mpv") == bundled_path
        return object()

    def fake_find_library(name: str) -> str | None:
        return None

    monkeypatch.setattr("app.infrastructure.playback.mpv_loader.import_module", fake_import_module)
    monkeypatch.setattr("app.infrastructure.playback.mpv_loader.invalidate_caches", lambda: None)
    monkeypatch.setattr(
        "app.infrastructure.playback.mpv_loader.ctypes.util.find_library",
        fake_find_library,
    )
    monkeypatch.delitem(sys.modules, "mpv", raising=False)

    module = load_mpv_module(bundled_path)

    assert module is not None
    assert ctypes.util.find_library is fake_find_library


def test_linux_loader_checks_usr_lib_next_to_appimage_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable_dir = tmp_path / "usr" / "bin"
    executable_dir.mkdir(parents=True)
    executable = executable_dir / "yaymp"
    executable.touch()

    bundled_library = tmp_path / "usr" / "lib" / "libmpv.so.1"
    bundled_library.parent.mkdir(parents=True)
    bundled_library.touch()

    monkeypatch.setattr(mpv_loader.sys, "platform", "linux")
    monkeypatch.setattr(mpv_loader.sys, "executable", str(executable))

    assert mpv_loader.resolve_mpv_library_path() == str(bundled_library)

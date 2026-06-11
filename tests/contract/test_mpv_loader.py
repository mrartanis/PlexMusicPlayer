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


def test_mpv_loader_patches_find_library_for_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundled_library = tmp_path / "bundled" / mpv_loader._candidate_library_names()[0]
    bundled_library.parent.mkdir(parents=True)
    bundled_library.touch()
    bundled_path = str(bundled_library)
    expected_names = {"mpv", *mpv_loader._candidate_library_names()}

    def fake_import_module(name: str):
        assert name == "mpv"
        for library_name in expected_names:
            assert ctypes.util.find_library(library_name) == bundled_path
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


def test_windows_loader_checks_lib_directory_next_to_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable_dir = tmp_path / "dist"
    executable_dir.mkdir(parents=True)
    executable = executable_dir / "PlexMusicPlayer.exe"
    executable.touch()

    bundled_library = executable_dir / "lib" / "mpv-2.dll"
    bundled_library.parent.mkdir(parents=True)
    bundled_library.touch()

    monkeypatch.setattr(mpv_loader.sys, "platform", "win32")
    monkeypatch.setattr(mpv_loader.sys, "executable", str(executable))

    assert mpv_loader.resolve_mpv_library_path() == str(bundled_library)


def test_windows_loader_adds_library_directory_for_dependent_dlls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundled_library = tmp_path / "lib" / "libmpv-2.dll"
    bundled_library.parent.mkdir(parents=True)
    bundled_library.touch()

    added_directories: list[str] = []
    closed_handles: list[str] = []

    class DummyHandle:
        def __init__(self, path: str) -> None:
            self.path = path

        def close(self) -> None:
            closed_handles.append(self.path)

    def fake_add_dll_directory(path: str) -> DummyHandle:
        added_directories.append(path)
        return DummyHandle(path)

    def fake_import_module(name: str):
        assert name == "mpv"
        assert ctypes.util.find_library("mpv") == str(bundled_library)
        assert ctypes.util.find_library("mpv-2.dll") == str(bundled_library)
        assert ctypes.util.find_library("libmpv-2.dll") == str(bundled_library)
        return object()

    monkeypatch.setattr(mpv_loader.sys, "platform", "win32")
    monkeypatch.setattr(mpv_loader.os, "add_dll_directory", fake_add_dll_directory, raising=False)
    monkeypatch.setattr("app.infrastructure.playback.mpv_loader.import_module", fake_import_module)
    monkeypatch.setattr("app.infrastructure.playback.mpv_loader.invalidate_caches", lambda: None)
    monkeypatch.delitem(sys.modules, "mpv", raising=False)

    module = load_mpv_module(str(bundled_library))

    assert module is not None
    assert added_directories == [str(bundled_library.parent.resolve())]
    assert closed_handles == [str(bundled_library.parent.resolve())]

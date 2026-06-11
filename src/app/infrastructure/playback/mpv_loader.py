from __future__ import annotations

import ctypes.util
import os
import sys
from ctypes.util import find_library
from importlib import import_module, invalidate_caches
from pathlib import Path

from app.domain.errors import PlaybackBackendError


def _candidate_runtime_roots() -> list[Path]:
    roots: list[Path] = []
    executable = Path(sys.executable).resolve()
    roots.append(executable.parent)

    if sys.platform.startswith("linux"):
        # AppImage/AppDir layouts typically place the binary in usr/bin and
        # shared libraries in usr/lib.
        usr_dir = executable.parent.parent
        roots.append(usr_dir)

    if sys.platform == "darwin":
        # Nuitka app bundles place the executable in Contents/MacOS.
        contents_dir = executable.parent.parent
        if contents_dir.name == "Contents":
            roots.append(contents_dir)
            roots.append(contents_dir / "Resources")
            roots.append(contents_dir / "Frameworks")

    return roots


def _candidate_library_names() -> tuple[str, ...]:
    if sys.platform == "darwin":
        return ("libmpv.2.dylib", "libmpv.dylib")
    if sys.platform.startswith("linux"):
        return ("libmpv.so.2", "libmpv.so.1", "libmpv.so")
    if sys.platform == "win32":
        return ("mpv-2.dll", "mpv-1.dll", "libmpv-2.dll", "libmpv.dll")
    return ("libmpv",)


def _resolve_bundled_mpv_library() -> str | None:
    relative_dirs = (
        Path("."),
        Path("lib"),
        Path("Frameworks"),
        Path("Resources") / "lib",
    )
    for root in _candidate_runtime_roots():
        for relative_dir in relative_dirs:
            for library_name in _candidate_library_names():
                candidate = root / relative_dir / library_name
                if candidate.exists():
                    return str(candidate)
    return None


def resolve_mpv_library_path() -> str | None:
    bundled = _resolve_bundled_mpv_library()
    if bundled:
        return bundled
    override = os.getenv("PLEX_MUSIC_PLAYER_MPV_LIBRARY")
    if override:
        return override
    return find_library("mpv")


def _import_mpv_with_explicit_library(library_path: str):
    original_find_library = ctypes.util.find_library
    dll_directory = None
    dll_directory_handle = None
    patched_names = {"mpv", *(_candidate_library_names())}

    if sys.platform == "win32":
        dll_directory = str(Path(library_path).resolve().parent)

    def patched_find_library(name: str) -> str | None:
        if name in patched_names:
            return library_path
        return original_find_library(name)

    ctypes.util.find_library = patched_find_library
    try:
        if dll_directory and hasattr(os, "add_dll_directory"):
            dll_directory_handle = os.add_dll_directory(dll_directory)
        if "mpv" in sys.modules:
            del sys.modules["mpv"]
        invalidate_caches()
        return import_module("mpv")
    finally:
        if dll_directory_handle is not None:
            dll_directory_handle.close()
        ctypes.util.find_library = original_find_library


def load_mpv_module(library_path: str):
    try:
        return _import_mpv_with_explicit_library(library_path)
    except ModuleNotFoundError as exc:
        raise PlaybackBackendError("python-mpv is not installed") from exc
    except OSError as exc:
        raise PlaybackBackendError(f"Failed to load libmpv from {library_path}") from exc


def ensure_mpv_available() -> tuple[object, str]:
    library_path = resolve_mpv_library_path()
    if library_path is None:
        raise PlaybackBackendError("libmpv could not be resolved")
    module = load_mpv_module(library_path)
    return module, library_path

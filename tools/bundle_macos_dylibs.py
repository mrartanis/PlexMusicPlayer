from __future__ import annotations

import argparse
import shutil
import subprocess
from collections import deque
from pathlib import Path


def _run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True)


def _run_quiet(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _is_system_library(path: str) -> bool:
    return (
        path.startswith("/System/Library/")
        or path.startswith("/usr/lib/")
        or path.startswith("@")
    )


def _linked_libraries(path: Path) -> list[str]:
    lines = _run(["otool", "-L", str(path)]).splitlines()[1:]
    libraries: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        library = stripped.split(" ", 1)[0]
        if not _is_system_library(library):
            libraries.append(library)
    return libraries


def _copy_library(source: Path, target_dir: Path, target_name: str | None = None) -> Path:
    target = target_dir / (target_name or source.name)
    if target.exists():
        return target
    shutil.copy2(source, target)
    target.chmod(0o644)
    subprocess.run(["xattr", "-c", str(target)], check=False)
    return target


def bundle_dylibs(root_library: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    root_target = _copy_library(root_library.resolve(), target_dir, target_name=root_library.name)
    pending: deque[Path] = deque([root_target])
    copied: dict[str, Path] = {str(root_library.resolve()): root_target}
    visited: set[Path] = set()

    while pending:
        library = pending.popleft()
        if library in visited:
            continue
        visited.add(library)

        for dependency in _linked_libraries(library):
            dependency_path = Path(dependency).resolve()
            target = _copy_library(
                dependency_path,
                target_dir,
                target_name=Path(dependency).name,
            )
            copied[dependency] = target
            if target not in visited:
                pending.append(target)

    bundled_names = {path.name for path in copied.values()}
    for library in sorted(copied.values()):
        _run_quiet(["install_name_tool", "-id", f"@loader_path/{library.name}", str(library)])
        for dependency in _linked_libraries(library):
            dependency_name = Path(dependency).name
            if dependency_name in bundled_names:
                _run_quiet(
                    [
                        "install_name_tool",
                        "-change",
                        dependency,
                        f"@loader_path/{dependency_name}",
                        str(library),
                    ]
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle macOS dylib dependencies.")
    parser.add_argument("--root-library", required=True, type=Path)
    parser.add_argument("--target-dir", required=True, type=Path)
    args = parser.parse_args()

    bundle_dylibs(root_library=args.root_library, target_dir=args.target_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

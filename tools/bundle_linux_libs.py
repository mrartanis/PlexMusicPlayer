from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path

LDD_ARROW_RE = re.compile(r"^\s*\S+\s+=>\s+(/[^ ]+)")
LDD_DIRECT_RE = re.compile(r"^\s*(/[^ ]+)")
EXCLUDED_PREFIXES = ("/lib64/ld-linux",)
EXCLUDED_BASENAMES = {
    "ld-linux-x86-64.so.2",
    "libc.so.6",
    "libdl.so.2",
    "libgcc_s.so.1",
    "libm.so.6",
    "libpthread.so.0",
    "librt.so.1",
}


def _run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True)


def _run_quiet(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _linked_libraries(path: Path) -> list[str]:
    libraries: list[str] = []
    for line in _run(["ldd", str(path)]).splitlines():
        match = LDD_ARROW_RE.match(line) or LDD_DIRECT_RE.match(line)
        if not match:
            continue
        library = match.group(1)
        if library.startswith("linux-vdso"):
            continue
        if library.startswith(EXCLUDED_PREFIXES):
            continue
        if Path(library).name in EXCLUDED_BASENAMES:
            continue
        libraries.append(library)
    return libraries


def _copy_library(source: Path, target_dir: Path, target_name: str | None = None) -> Path:
    target = target_dir / (target_name or source.name)
    if target.exists():
        return target
    shutil.copy2(source, target)
    target.chmod(0o755)
    return target


def bundle_libraries(root_library: Path, target_dir: Path) -> None:
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
        _run_quiet(["patchelf", "--set-rpath", "$ORIGIN", str(library)])
        for dependency in _linked_libraries(library):
            dependency_name = Path(dependency).name
            if dependency_name in bundled_names:
                _run_quiet(
                    [
                        "patchelf",
                        "--replace-needed",
                        dependency,
                        dependency_name,
                        str(library),
                    ]
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle Linux shared library dependencies.")
    parser.add_argument("--root-library", required=True, type=Path)
    parser.add_argument("--target-dir", required=True, type=Path)
    args = parser.parse_args()

    bundle_libraries(root_library=args.root_library, target_dir=args.target_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

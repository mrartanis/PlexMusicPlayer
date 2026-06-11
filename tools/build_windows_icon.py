from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtGui import QImage


def build_windows_icon(source: Path, destination: Path) -> None:
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f"Failed to load source icon: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(destination), "ICO"):
        raise SystemExit(f"Failed to save Windows icon: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    build_windows_icon(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys
from pathlib import Path


def _add_source_path_for_uncompiled_dev_runs() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "src"
    if source_path.exists():
        sys.path.insert(0, str(source_path))


_add_source_path_for_uncompiled_dev_runs()


if __name__ == "__main__":
    from app.__main__ import main

    raise SystemExit(main())

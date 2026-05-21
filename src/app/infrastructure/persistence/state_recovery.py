from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.domain import Logger
from app.domain.errors import StorageError


def quarantine_state_file(path: Path, *, logger: Logger, reason: str) -> Path | None:
    if not path.exists():
        return None

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    target = _available_quarantine_path(path, timestamp=timestamp)
    try:
        path.replace(target)
    except OSError as exc:
        raise StorageError(f"Failed to quarantine state file {path}") from exc

    logger.warning("Quarantined invalid state file %s -> %s: %s", path, target, reason)
    return target


def _available_quarantine_path(path: Path, *, timestamp: str) -> Path:
    target = path.with_name(f"{path.name}.invalid-{timestamp}")
    if not target.exists():
        return target
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.name}.invalid-{timestamp}-{index}")
        if not candidate.exists():
            return candidate
    raise StorageError(f"Failed to find quarantine filename for {path}")

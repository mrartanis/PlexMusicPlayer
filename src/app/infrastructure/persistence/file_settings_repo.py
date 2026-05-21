from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.domain import SettingsRepo
from app.domain.errors import StorageError


class FileSettingsRepo(SettingsRepo):
    def __init__(self, *, file_path: Path) -> None:
        self._file_path = file_path

    def load_settings(self) -> Mapping[str, Any]:
        if not self._file_path.exists():
            return {}

        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("Failed to load settings") from exc

        if not isinstance(payload, dict):
            raise StorageError("Settings file is invalid")
        return payload

    def save_settings(self, settings: Mapping[str, Any]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file_path.write_text(
                json.dumps(dict(settings), indent=2, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )
        except (OSError, TypeError) as exc:
            raise StorageError("Failed to save settings") from exc

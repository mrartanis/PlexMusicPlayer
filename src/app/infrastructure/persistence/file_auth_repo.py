from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.domain import AuthRepo, AuthSession
from app.domain.errors import StorageError


class FileAuthRepo(AuthRepo):
    def __init__(self, *, file_path: Path) -> None:
        self._file_path = file_path

    def load_session(self) -> AuthSession | None:
        if not self._file_path.exists():
            return None

        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("Failed to load auth session") from exc

        try:
            expires_at_raw = payload.get("expires_at")
            expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else None
            return AuthSession(
                user_id=payload["user_id"],
                token=payload["token"],
                expires_at=expires_at,
                display_name=payload.get("display_name"),
                server_name=payload.get("server_name"),
                server_url=payload.get("server_url"),
                server_access_token=payload.get("server_access_token"),
                music_section_id=payload.get("music_section_id"),
                music_section_title=payload.get("music_section_title"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError("Auth session file is invalid") from exc

    def save_session(self, session: AuthSession) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "user_id": session.user_id,
            "token": session.token,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "display_name": session.display_name,
            "server_name": session.server_name,
            "server_url": session.server_url,
            "server_access_token": session.server_access_token,
            "music_section_id": session.music_section_id,
            "music_section_title": session.music_section_title,
        }
        try:
            self._file_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError("Failed to save auth session") from exc

    def clear_session(self) -> None:
        if not self._file_path.exists():
            return
        try:
            self._file_path.unlink()
        except OSError as exc:
            raise StorageError("Failed to clear auth session") from exc

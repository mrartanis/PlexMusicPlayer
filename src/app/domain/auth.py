from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    user_id: str
    token: str
    expires_at: datetime | None = None
    display_name: str | None = None
    server_name: str | None = None
    server_url: str | None = None
    server_access_token: str | None = None
    music_section_id: str | None = None
    music_section_title: str | None = None

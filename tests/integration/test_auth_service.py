from __future__ import annotations

from datetime import UTC, datetime

from app.application.auth_service import AuthService
from app.domain import AuthSession


class TestLogger:
    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        del message, args

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class InMemoryAuthRepo:
    def __init__(self, session: AuthSession | None = None) -> None:
        self.session = session

    def load_session(self) -> AuthSession | None:
        return self.session

    def save_session(self, session: AuthSession) -> None:
        self.session = session

    def clear_session(self) -> None:
        self.session = None


class FakeMusicService:
    def clear_auth_session(self) -> None:
        self.cleared_session = True

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        return AuthSession(
            user_id="user-3",
            token=token,
            expires_at=expires_at,
            display_name="listener",
        )


def test_restore_session_recovers_saved_session() -> None:
    session = AuthSession(
        user_id="user-1",
        token="token-1",
        expires_at=datetime(2026, 4, 20, tzinfo=UTC),
        display_name="Listener",
    )
    service = AuthService(auth_repo=InMemoryAuthRepo(session), logger=TestLogger())

    restored = service.restore_session()

    assert restored == session
    assert service.current_session() == session


def test_save_and_clear_session_updates_repo_and_current_state() -> None:
    repo = InMemoryAuthRepo()
    service = AuthService(auth_repo=repo, logger=TestLogger())
    session = AuthSession(user_id="user-2", token="token-2")

    saved = service.save_session(session)
    assert saved == session
    assert repo.session == session
    assert service.current_session() == session

    service.clear_session()

    assert repo.session is None
    assert service.current_session() is None


def test_authenticate_with_token_builds_and_persists_session() -> None:
    repo = InMemoryAuthRepo()
    service = AuthService(auth_repo=repo, logger=TestLogger())

    session = service.authenticate_with_token(
        "token-3",
        music_service=FakeMusicService(),
        expires_in=3600,
    )

    assert session.user_id == "user-3"
    assert session.display_name == "listener"
    assert session.token == "token-3"
    assert repo.session == session

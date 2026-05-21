from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain import AuthRepo, AuthSession, Logger, MusicService


class AuthService:
    def __init__(self, *, auth_repo: AuthRepo, logger: Logger) -> None:
        self._auth_repo = auth_repo
        self._logger = logger
        self._session: AuthSession | None = None

    def restore_session(self) -> AuthSession | None:
        self._session = self._auth_repo.load_session()
        if self._session is None:
            self._logger.info("No saved auth session found")
        else:
            self._logger.info("Recovered auth session for user %s", self._session.user_id)
        return self._session

    def save_session(self, session: AuthSession) -> AuthSession:
        self._auth_repo.save_session(session)
        self._session = session
        self._logger.info("Saved auth session for user %s", session.user_id)
        return session

    def clear_session(self) -> None:
        self._auth_repo.clear_session()
        self._session = None
        self._logger.info("Cleared auth session")

    def current_session(self) -> AuthSession | None:
        return self._session

    def authenticate_with_token(
        self,
        token: str,
        *,
        music_service: MusicService,
        expires_in: int | None = None,
    ) -> AuthSession:
        expires_at = None
        if expires_in is not None:
            expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_in)
        session = music_service.build_auth_session(token, expires_at=expires_at)
        return self.save_session(session)

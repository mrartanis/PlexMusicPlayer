from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import AuthSession, StorageError
from app.infrastructure.persistence.file_auth_repo import FileAuthRepo


def test_file_auth_repo_round_trips_session(tmp_path) -> None:
    repo = FileAuthRepo(file_path=tmp_path / "auth.json")
    session = AuthSession(
        user_id="user-1",
        token="secret",
        expires_at=datetime(2026, 4, 20, tzinfo=UTC),
        display_name="Listener",
    )

    repo.save_session(session)

    assert repo.load_session() == session


def test_file_auth_repo_returns_none_when_file_is_missing(tmp_path) -> None:
    repo = FileAuthRepo(file_path=tmp_path / "missing.json")

    assert repo.load_session() is None


def test_file_auth_repo_raises_storage_error_for_invalid_payload(tmp_path) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"broken": true}', encoding="utf-8")
    repo = FileAuthRepo(file_path=path)

    with pytest.raises(StorageError):
        repo.load_session()


def test_file_auth_repo_clear_session_removes_file(tmp_path) -> None:
    path = tmp_path / "auth.json"
    repo = FileAuthRepo(file_path=path)
    repo.save_session(AuthSession(user_id="user-1", token="secret"))

    repo.clear_session()

    assert not path.exists()

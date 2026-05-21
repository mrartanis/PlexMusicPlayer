from __future__ import annotations

import pytest

from app.domain import StorageError
from app.infrastructure.persistence.file_settings_repo import FileSettingsRepo


def test_file_settings_repo_round_trips_settings(tmp_path) -> None:
    repo = FileSettingsRepo(file_path=tmp_path / "settings.json")

    repo.save_settings({"volume": 72, "quality": "hq"})

    assert repo.load_settings() == {"quality": "hq", "volume": 72}


def test_file_settings_repo_returns_empty_when_missing(tmp_path) -> None:
    repo = FileSettingsRepo(file_path=tmp_path / "missing.json")

    assert repo.load_settings() == {}


def test_file_settings_repo_rejects_invalid_payload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('["not", "a", "mapping"]', encoding="utf-8")
    repo = FileSettingsRepo(file_path=path)

    with pytest.raises(StorageError):
        repo.load_settings()


def test_file_settings_repo_maps_unserializable_values_to_storage_error(tmp_path) -> None:
    repo = FileSettingsRepo(file_path=tmp_path / "settings.json")

    with pytest.raises(StorageError):
        repo.save_settings({"bad": object()})

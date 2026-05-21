from __future__ import annotations

from pathlib import Path

from app.infrastructure.persistence.state_recovery import quarantine_state_file


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        self.warnings.append(message % args)

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


def test_quarantine_state_file_renames_existing_file(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("broken", encoding="utf-8")
    logger = RecordingLogger()

    quarantine_path = quarantine_state_file(path, logger=logger, reason="invalid json")

    assert quarantine_path is not None
    assert not path.exists()
    assert quarantine_path.read_text(encoding="utf-8") == "broken"
    assert quarantine_path.name.startswith("settings.json.invalid-")
    assert "Quarantined invalid state file" in logger.warnings[0]


def test_quarantine_state_file_returns_none_for_missing_file(tmp_path) -> None:
    logger = RecordingLogger()

    assert quarantine_state_file(Path(tmp_path / "missing.json"), logger=logger, reason="x") is None
    assert logger.warnings == []

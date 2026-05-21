from __future__ import annotations

import webbrowser
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.infrastructure.plex import PlexAuthWorker, PlexMusicService


class AuthDialog(QDialog):
    session_captured = Signal(object)

    def __init__(
        self,
        *,
        parent=None,
        window_title: str,
        status_text: str,
        music_service: PlexMusicService,
        logger: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(560, 320)

        self._music_service = music_service
        self._logger = logger
        self._token: str | None = None
        self._auth_url: str | None = None
        self._resources: list[dict[str, object]] = []
        self._selected_server_name: str | None = None
        self._selected_server_url: str | None = None
        self._selected_server_token: str | None = None
        self._sections: tuple[dict[str, str], ...] = ()
        self._worker = PlexAuthWorker()
        self._wire_worker()

        layout = QVBoxLayout(self)
        self._status_label = QLabel(status_text)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._pin_label = QLabel("...")
        self._pin_label.setStyleSheet("font-size: 28px; font-weight: 800;")
        layout.addWidget(self._pin_label)

        pin_actions = QHBoxLayout()
        self._open_browser_button = QPushButton("Open Plex Login")
        self._open_browser_button.setEnabled(False)
        self._open_browser_button.clicked.connect(self._open_browser)
        pin_actions.addWidget(self._open_browser_button)

        self._retry_button = QPushButton("Retry")
        self._retry_button.clicked.connect(self._restart_pin_flow)
        pin_actions.addWidget(self._retry_button)
        pin_actions.addStretch(1)
        layout.addLayout(pin_actions)

        self._server_combo = QComboBox()
        self._server_combo.setVisible(False)
        layout.addWidget(self._server_combo)

        self._library_combo = QComboBox()
        self._library_combo.setVisible(False)
        layout.addWidget(self._library_combo)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._continue_button = QPushButton("Continue")
        self._continue_button.setEnabled(False)
        self._continue_button.clicked.connect(self._continue_flow)
        footer.addWidget(self._continue_button)
        layout.addLayout(footer)

        self._worker.request_pin()

    def apply_texts(self, *, window_title: str, status_text: str) -> None:
        self.setWindowTitle(window_title)
        self._status_label.setText(status_text)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._worker.stop()
        super().closeEvent(event)

    def _wire_worker(self) -> None:
        self._worker.pin_created.connect(self._handle_pin_created)
        self._worker.authorized.connect(self._handle_authorized)
        self._worker.resources_loaded.connect(self._handle_resources_loaded)
        self._worker.connection_found.connect(self._handle_connection_found)
        self._worker.error.connect(self._handle_error)

    def _restart_pin_flow(self) -> None:
        self._worker.stop()
        self._worker = PlexAuthWorker()
        self._wire_worker()
        self._token = None
        self._auth_url = None
        self._resources = []
        self._sections = ()
        self._selected_server_name = None
        self._selected_server_url = None
        self._selected_server_token = None
        self._server_combo.clear()
        self._library_combo.clear()
        self._server_combo.setVisible(False)
        self._library_combo.setVisible(False)
        self._continue_button.setEnabled(False)
        self._pin_label.setText("...")
        self._status_label.setText("Requesting Plex PIN...")
        self._worker.request_pin()

    def _open_browser(self) -> None:
        if self._auth_url:
            webbrowser.open(self._auth_url)

    def _handle_pin_created(self, code: str, url: str) -> None:
        self._auth_url = url
        self._pin_label.setText(code)
        self._open_browser_button.setEnabled(True)
        self._status_label.setText("Visit plex.tv/link, enter the code, and finish sign-in.")

    def _handle_authorized(self, token: str) -> None:
        self._token = token
        self._status_label.setText("Signed in. Loading Plex servers...")
        self._worker.get_resources()

    def _handle_resources_loaded(self, resources: list) -> None:
        self._resources = [resource for resource in resources if resource.get("connections")]
        self._server_combo.clear()
        for resource in self._resources:
            self._server_combo.addItem(str(resource.get("name") or "Plex Server"))
        self._server_combo.setVisible(True)
        self._continue_button.setEnabled(bool(self._resources))
        self._continue_button.setText("Connect Server")
        self._status_label.setText("Choose a Plex server.")

    def _handle_connection_found(self, name: str, url: str, token: str) -> None:
        self._selected_server_name = name
        self._selected_server_url = url
        self._selected_server_token = token
        self._sections = self._music_service.available_music_sections(
            server_url=url,
            server_token=token,
        )
        self._library_combo.clear()
        for section in self._sections:
            self._library_combo.addItem(section["title"])
        self._library_combo.setVisible(True)
        self._continue_button.setEnabled(bool(self._sections))
        self._continue_button.setText("Finish Login")
        self._status_label.setText("Choose a Plex music library.")

    def _handle_error(self, message: str) -> None:
        if self._logger is not None:
            self._logger.warning("Plex auth flow error: %s", message)
        self._status_label.setText(message)
        self._continue_button.setEnabled(bool(self._resources))

    def _continue_flow(self) -> None:
        if self._selected_server_url and self._selected_server_token and self._sections:
            section = self._sections[self._library_combo.currentIndex()]
            if not self._token:
                self._handle_error("Plex token is missing")
                return
            session = self._music_service.build_authenticated_session(
                token=self._token,
                server_name=self._selected_server_name or "Plex Server",
                server_url=self._selected_server_url,
                server_access_token=self._selected_server_token,
                music_section_id=section["id"],
                music_section_title=section["title"],
            )
            self.session_captured.emit(session)
            self.accept()
            return

        if not self._resources:
            self._handle_error("No Plex servers are available for this account")
            return

        current_index = self._server_combo.currentIndex()
        if current_index < 0 or current_index >= len(self._resources):
            self._handle_error("Select a Plex server first")
            return

        self._continue_button.setEnabled(False)
        self._status_label.setText("Connecting to selected Plex server...")
        self._worker.test_connection(self._resources[current_index])

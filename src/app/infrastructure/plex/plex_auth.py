from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3
from PySide6.QtCore import QThread, Signal

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PlexAuthWorker(QThread):
    pin_created = Signal(str, str)
    authorized = Signal(str)
    resources_loaded = Signal(list)
    connection_found = Signal(str, str, str)
    error = Signal(str)

    def __init__(self, *, app_version: str = "dev") -> None:
        super().__init__()
        self._client_identifier = str(uuid.uuid4())
        self._pin_login = None
        self._token: str | None = None
        self._app_version = app_version
        self._should_stop = False
        self._executor = ThreadPoolExecutor(max_workers=4)

    def request_pin(self) -> None:
        self.start()

    def get_resources(self) -> None:
        self._executor.submit(self._load_resources)

    def test_connection(self, resource: dict[str, object]) -> None:
        self._executor.submit(self._test_connection, resource)

    def run(self) -> None:
        try:
            self._create_pin()
            self._poll_pin()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._should_stop = True
        if self.isRunning():
            self.wait(2000)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Plex-Client-Identifier": self._client_identifier,
            "X-Plex-Product": "Plex Music Player",
            "X-Plex-Version": self._app_version,
            "X-Plex-Platform": "Desktop",
            "X-Plex-Platform-Version": "",
            "X-Plex-Device": "Desktop",
            "X-Plex-Device-Name": "Plex Music Player",
            "X-Plex-Model": "Plex Music Player",
            "Accept": "application/xml",
        }

    def _create_pin(self) -> None:
        try:
            from plexapi.myplex import MyPlexPinLogin
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("plexapi is not installed") from exc

        session = requests.Session()
        session.verify = False
        headers = self._headers()
        session.headers.update(headers)
        self._pin_login = MyPlexPinLogin(session=session, headers=headers, oauth=False)
        if not self._pin_login.pin:
            raise RuntimeError("Failed to obtain Plex PIN code")
        self.pin_created.emit(self._pin_login.pin, "https://plex.tv/link")

    def _poll_pin(self) -> None:
        if self._pin_login is None:
            raise RuntimeError("PIN login is not initialized")
        while not self._should_stop:
            if self._pin_login.checkLogin():
                token = self._pin_login.token
                if not token:
                    raise RuntimeError("Plex login completed without token")
                self._token = token
                self.authorized.emit(token)
                return
            if self._pin_login.finished:
                raise RuntimeError("Plex PIN expired before authorization completed")
            self.msleep(2000)

    def _load_resources(self) -> None:
        if not self._token:
            self.error.emit("No Plex token available")
            return
        try:
            from plexapi.myplex import MyPlexAccount
        except ImportError as exc:  # pragma: no cover - runtime dependency
            self.error.emit(f"plexapi is not installed: {exc}")
            return

        try:
            account = MyPlexAccount(token=self._token)
            resources = []
            for resource in account.resources():
                if "server" not in getattr(resource, "provides", ()):
                    continue
                resources.append(
                    {
                        "name": resource.name,
                        "access_token": resource.accessToken,
                        "connections": [connection.uri for connection in resource.connections],
                    }
                )
            self.resources_loaded.emit(resources)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _test_connection(self, resource: dict[str, object]) -> None:
        token = str(resource.get("access_token") or "")
        name = str(resource.get("name") or "Plex Server")
        connections = resource.get("connections") or ()
        for url in connections:
            if self._should_stop:
                return
            try:
                response = requests.get(
                    f"{url}/identity",
                    headers={"X-Plex-Token": token},
                    timeout=3,
                    verify=False,
                )
            except Exception:  # noqa: BLE001
                continue
            if response.status_code == 200:
                self.connection_found.emit(name, str(url), token)
                return
        self.error.emit(f"Could not connect to {name}")

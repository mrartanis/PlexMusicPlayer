import uuid
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import pyqtSignal, QThread
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from .logger import Logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = Logger()

class PlexAuthWorker(QThread):
    pin_created = pyqtSignal(str, str)  # code, url
    authorized = pyqtSignal(str, str)   # token, username
    error = pyqtSignal(str)
    resources_loaded = pyqtSignal(list)
    connection_found = pyqtSignal(str, str, str) # server_name, url, token
    
    def __init__(self, client_identifier=None):
        super().__init__()
        self.client_identifier = client_identifier or str(uuid.uuid4())
        self.pin_login = None
        self.account = None
        self._token = None
        self.should_stop = False
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._action = None
        self._resource = None

    def request_pin(self):
        self._action = 'request_pin'
        self.start()

    def get_resources(self):
        # Use executor for one-off operations to avoid blocking the main polling thread
        self.executor.submit(self._do_get_resources)

    def test_connection(self, resource):
        # Use executor for one-off operations
        self.executor.submit(self._do_test_connection, resource)

    def run(self):
        if self._action == 'request_pin':
            self._do_request_pin()

def _do_request_pin(self):
    try:
        logger.debug("Requesting PIN with client identifier: %s", self.client_identifier)

        headers = {
            "X-Plex-Client-Identifier": str(self.client_identifier),
            "X-Plex-Product": "PlexMusicPlayer",
            "X-Plex-Version": getattr(self, "app_version", "dev"),
            "X-Plex-Platform": "Linux",
            "X-Plex-Platform-Version": "",
            "X-Plex-Device": "Desktop",
            "X-Plex-Device-Name": "PlexMusicPlayer",
            "X-Plex-Model": "PlexMusicPlayer",
            "Accept": "application/xml",
        }

        session = requests.Session()
        session.verify = False
        if session.verify is False:
            logger.warning("TLS verification is disabled (session.verify=False).")

        session.headers.update(headers)

        max_retries = 3
        sleep_ms = 1000

        code = None
        auth_url = None

        def _log_pins_probe():
            try:
                r = session.post("https://plex.tv/api/v2/pins", timeout=15)
                ct = (r.headers.get("content-type") or "").lower()
                head = (r.text or "")[:250].replace("\r", "\\r").replace("\n", "\\n")
                logger.debug(
                    "pins probe: status=%s ct=%r url=%s head=%r",
                    r.status_code, ct, getattr(r, "url", ""), head
                )
                return r
            except Exception as e:
                logger.warning("pins probe failed: %s", e)
                return None

        last_probe = None

        for attempt in range(1, max_retries + 1):
            try:
                if attempt in (1, max_retries):
                    last_probe = _log_pins_probe()

                self.pin_login = MyPlexPinLogin(session=session, headers=headers, oauth=False)

                code = self.pin_login.pin
                if code:
                    break

                logger.debug("Failed to get PIN (pin_login.pin is empty), attempt %s/%s", attempt, max_retries)
                self.msleep(sleep_ms)

            except Exception as e:
                # Логируем стек — чтобы не было “фигни по сути”.
                logger.exception("Error in PIN request attempt %s/%s: %s", attempt, max_retries, e)
                if attempt >= max_retries:
                    raise

        if not code:
            # Если probe был и там HTTP не 2xx — сообщим это в ошибке, это очень помогает.
            if last_probe is not None and not getattr(last_probe, "ok", True):
                raise Exception(
                    f"Failed to obtain PIN. Plex returned HTTP {last_probe.status_code} "
                    f"({(last_probe.headers.get('content-type') or '').strip()})."
                )
            raise Exception("Failed to obtain PIN code after multiple attempts (empty response).")

        auth_url = "https://plex.tv/link"
        logger.debug("PIN created: %s, URL: %s", code, auth_url)

        self.pin_created.emit(code, auth_url)
        self._poll_pin()

    except Exception as e:
        logger.exception("Error requesting PIN: %s", e)
        self.error.emit(str(e))

    def _poll_pin(self):
        while not self.should_stop:
            try:
                logger.debug("Polling PIN...")
                if self.pin_login.checkLogin():
                    logger.debug("PIN authorized!")
                    token = self.pin_login.token
                    logger.debug("Got token, emitting signal immediately...")
                    # Don't create MyPlexAccount here - it does network requests which are slow
                    # Just emit the token, we'll create account later when needed
                    self._token = token
                    # Emit only token, username will be fetched later if needed
                    self.authorized.emit(token, "")
                    logger.debug("Signal emitted")
                    return
                elif self.pin_login.finished:
                    logger.debug("PIN polling finished without success (expired?)")
                    return
                
                # Sleep in thread is fine
                self.msleep(2000)
            except Exception as e:
                logger.error(f"Error polling PIN: {e}")
                # Usually we continue polling unless it's a fatal error
                if self.should_stop:
                    return
                self.msleep(2000)

    def _do_get_resources(self):
        try:
            # Create account only when we actually need it (lazy initialization)
            if not self.account:
                logger.debug("Creating account for resources...")
                if not hasattr(self, '_token') or not self._token:
                    logger.error("No token available for creating account")
                    self.error.emit("No authentication token available")
                    return
                self.account = MyPlexAccount(token=self._token)
                logger.debug("Account created")
            
            logger.debug("Fetching resources...")
            resources = self.account.resources()
            # Filter for servers that provide 'server'
            servers = [r for r in resources if 'server' in r.provides]
            logger.debug(f"Found {len(servers)} servers")
            self.resources_loaded.emit(servers)
        except Exception as e:
            logger.error(f"Error getting resources: {e}")
            self.error.emit(str(e))

    def _do_test_connection(self, resource):
        try:
            logger.debug(f"Testing connections for {resource.name}")
            connections = resource.connections
            if not connections:
                logger.debug(f"No connections found for {resource.name}")
                self.error.emit(f"No connections found for {resource.name}")
                return

            token = resource.accessToken
            
            def check_url(connection):
                url = connection.uri
                try:
                    logger.debug(f"Checking {url}...")
                    response = requests.get(f"{url}/identity", headers={'X-Plex-Token': token}, timeout=3, verify=False)
                    if response.status_code == 200:
                        return url
                except Exception:
                    pass
                return None

            # We can run this blocking in the thread
            for conn in connections:
                 if self.should_stop: return
                 result = check_url(conn)
                 if result:
                     logger.debug(f"Connection successful: {result}")
                     self.connection_found.emit(resource.name, result, token)
                     return

            logger.debug(f"Could not connect to {resource.name}")
            self.error.emit(f"Could not connect to {resource.name}")

        except Exception as e:
            logger.error(f"Error testing connection: {e}")
            self.error.emit(str(e))

    def stop(self):
        self.should_stop = True
        self.wait()


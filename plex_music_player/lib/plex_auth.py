import uuid
import requests
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import pyqtSignal, QThread
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from .logger import Logger

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
            logger.debug(f"Requesting PIN with client identifier: {self.client_identifier}")
            headers = {'X-Plex-Client-Identifier': self.client_identifier}
            
            # Retry mechanism for getting PIN
            max_retries = 3
            code = None
            auth_url = None
            
            for attempt in range(max_retries):
                try:
                    self.pin_login = MyPlexPinLogin(headers=headers, oauth=False)
                    code = self.pin_login.pin
                    if code:
                        break
                    logger.debug(f"Failed to get PIN, attempt {attempt + 1}/{max_retries}")
                    self.msleep(1000)
                except Exception as e:
                    logger.error(f"Error in PIN request attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        raise
            
            if not code:
                raise Exception("Failed to obtain PIN code after multiple attempts")
                
            auth_url = "https://plex.tv/link"
            logger.debug(f"PIN created: {code}, URL: {auth_url}")
            # Emit signal - it will be queued to main thread
            self.pin_created.emit(code, auth_url)
            # Start polling (this will block this thread, but that's OK)
            self._poll_pin()
        except Exception as e:
            logger.error(f"Error requesting PIN: {e}")
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


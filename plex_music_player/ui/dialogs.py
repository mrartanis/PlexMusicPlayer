import os
import json
import webbrowser
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QComboBox,
    QMessageBox,
    QListWidget,
    QCheckBox,
    QStackedWidget,
    QProgressBar,
    QFrame,
    QApplication,
)
from plexapi.server import PlexServer
from plexapi.audio import Track
from plexapi.exceptions import Unauthorized, NotFound
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from ..models.player import TrackLoader, ArtistLoader
from ..lib.logger import Logger
from ..lib.plex_auth import PlexAuthWorker
from plex_music_player.lib.lastfm_auth_server import LastFMAuthServer, open_auth_url

logger = Logger()

class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plex = None
        self.worker = None
        self.resources = []
        self.auth_url = None
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        self.setWindowTitle("Connect to Plex")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        layout = QVBoxLayout(self)

        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)

        # Page 1: Login Options
        self.page_login = QFrame()
        login_layout = QVBoxLayout(self.page_login)
        
        login_label = QLabel("Welcome to Plex Music Player")
        login_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        login_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        login_layout.addWidget(login_label)
        
        self.sign_in_button = QPushButton("Sign In with Plex")
        self.sign_in_button.clicked.connect(self.start_pin_auth)
        self.sign_in_button.setMinimumHeight(40)
        self.sign_in_button.setStyleSheet("background-color: #e5a00d; color: black; font-weight: bold;")
        login_layout.addWidget(self.sign_in_button)
        
        self.manual_button = QPushButton("Manual Connection")
        self.manual_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page_manual))
        login_layout.addWidget(self.manual_button)
        
        login_layout.addStretch()
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        login_layout.addWidget(close_button)
        
        self.stacked_widget.addWidget(self.page_login)

        # Page 2: PIN Flow
        self.page_pin = QFrame()
        pin_layout = QVBoxLayout(self.page_pin)
        
        pin_info = QLabel("Visit plex.tv/link and enter this code:")
        pin_info.setWordWrap(True)
        pin_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_layout.addWidget(pin_info)
        
        self.pin_code_label = QLabel("Loading...")
        self.pin_code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_code_label.setStyleSheet("font-size: 32px; font-weight: bold; margin: 20px; color: #e5a00d;")
        self.pin_code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pin_code_label.setMinimumHeight(60)
        self.pin_code_label.setMinimumWidth(200)
        pin_layout.addWidget(self.pin_code_label)
        
        self.open_browser_button = QPushButton("Open Browser")
        self.open_browser_button.clicked.connect(self.open_browser)
        pin_layout.addWidget(self.open_browser_button)
        
        pin_layout.addStretch()
        
        self.cancel_pin_button = QPushButton("Cancel")
        self.cancel_pin_button.clicked.connect(self.cancel_pin_auth)
        pin_layout.addWidget(self.cancel_pin_button)
        
        self.stacked_widget.addWidget(self.page_pin)

        # Page 3: Server Selection
        self.page_servers = QFrame()
        servers_layout = QVBoxLayout(self.page_servers)
        
        servers_layout.addWidget(QLabel("Select Server:"))
        self.server_combo = QComboBox()
        servers_layout.addWidget(self.server_combo)
        
        self.connection_status_label = QLabel("")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        servers_layout.addWidget(self.connection_status_label)
        
        self.connect_server_button = QPushButton("Connect")
        self.connect_server_button.clicked.connect(self.connect_selected_server)
        servers_layout.addWidget(self.connect_server_button)
        
        servers_layout.addStretch()
        
        back_server_button = QPushButton("Back")
        back_server_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page_login))
        servers_layout.addWidget(back_server_button)
        
        self.stacked_widget.addWidget(self.page_servers)

        # Page 4: Manual Connection
        self.page_manual = QFrame()
        manual_layout = QVBoxLayout(self.page_manual)
        
        # URL
        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("http://localhost:32400")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        manual_layout.addLayout(url_layout)
        
        # Token
        token_layout = QHBoxLayout()
        token_label = QLabel("Token:")
        self.token_edit = QLineEdit()
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_edit)
        manual_layout.addLayout(token_layout)
        
        manual_layout.addStretch()
        
        manual_buttons = QHBoxLayout()
        self.manual_connect_button = QPushButton("Connect")
        self.manual_connect_button.clicked.connect(self.try_manual_connect)
        manual_buttons.addWidget(self.manual_connect_button)
        
        self.manual_back_button = QPushButton("Back")
        self.manual_back_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.page_login))
        manual_buttons.addWidget(self.manual_back_button)
        
        manual_layout.addLayout(manual_buttons)
        self.stacked_widget.addWidget(self.page_manual)

    def load_config(self):
        try:
            config_path = os.path.expanduser("~/.config/plex_music_player/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    if 'plex' in config:
                        self.url_edit.setText(config['plex'].get('url', ''))
                        self.token_edit.setText(config['plex'].get('token', ''))
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")

    def start_pin_auth(self):
        self.stacked_widget.setCurrentWidget(self.page_pin)
        self.pin_code_label.setText("Loading...")
        self.open_browser_button.setEnabled(False)
        
        if self.worker:
            self.worker.stop()
            self.worker.deleteLater()
        
        self.worker = PlexAuthWorker()
        # Use QueuedConnection explicitly to ensure signals are processed in main thread
        self.worker.pin_created.connect(self.on_pin_created, Qt.ConnectionType.QueuedConnection)
        self.worker.authorized.connect(self.on_authorized, Qt.ConnectionType.QueuedConnection)
        self.worker.error.connect(self.on_worker_error, Qt.ConnectionType.QueuedConnection)
        self.worker.resources_loaded.connect(self.on_resources_loaded, Qt.ConnectionType.QueuedConnection)
        self.worker.connection_found.connect(self.on_connection_found, Qt.ConnectionType.QueuedConnection)
        
        self.worker.request_pin()

    def cancel_pin_auth(self):
        if self.worker:
            self.worker.stop()
        self.stacked_widget.setCurrentWidget(self.page_login)

    def open_browser(self):
        if self.auth_url:
            webbrowser.open(self.auth_url)

    def on_pin_created(self, code, url):
        logger.debug(f"on_pin_created called with code: {code}")
        # Ensure we're on the PIN page
        self.stacked_widget.setCurrentWidget(self.page_pin)
        # Update the label immediately
        self.pin_code_label.setText(code)
        self.pin_code_label.show()
        # Force update on macOS - sometimes needs explicit update/repaint
        self.pin_code_label.update()
        self.pin_code_label.repaint()
        self.page_pin.update()
        self.page_pin.repaint()
        # Set other properties
        self.auth_url = url
        self.open_browser_button.setEnabled(True)
        # Force immediate UI update
        QApplication.processEvents()
        # Additional update after processing events (helps on macOS)
        QTimer.singleShot(50, lambda: (self.pin_code_label.update(), self.pin_code_label.repaint()))
        logger.debug(f"PIN label text set to: {self.pin_code_label.text()}, visible: {self.pin_code_label.isVisible()}, current widget: {self.stacked_widget.currentWidget()}")

    def on_authorized(self, token, username):
        logger.debug(f"Authorized! Token received, username: {username if username else 'will be fetched later'}")
        self.stacked_widget.setCurrentWidget(self.page_servers)
        self.connection_status_label.setText("Loading servers...")
        self.connect_server_button.setEnabled(False)
        
        # Get resources (this will create account in worker thread when needed)
        self.worker.get_resources()

    def on_resources_loaded(self, resources):
        self.resources = resources
        self.server_combo.clear()
        if not resources:
            self.connection_status_label.setText("No servers found")
            return
            
        for resource in resources:
            self.server_combo.addItem(resource.name)
        
        self.connection_status_label.setText("")
        self.connect_server_button.setEnabled(True)

    def connect_selected_server(self):
        if not self.resources:
            return
            
        index = self.server_combo.currentIndex()
        if index < 0:
            return
            
        resource = self.resources[index]
        self.connection_status_label.setText(f"Connecting to {resource.name}...")
        self.connect_server_button.setEnabled(False)
        self.server_combo.setEnabled(False)
        
        # Test connection
        self.worker.test_connection(resource)

    def on_connection_found(self, name, url, token):
        logger.debug(f"Connected to {name} at {url}")
        self.connection_status_label.setText("Connection successful!")
        
        # Connect player
        if hasattr(self.parent(), 'player'):
            self.parent().player.connect_server(url, token)
            
        # We should probably save the config here too, but player.connect_server doesn't save automatically?
        # Player.connect_server just connects.
        # Player.save_config() saves current config.
        # We should update the player's config manually if needed or rely on player to save if it does.
        # Looking at player.py: connect_server doesn't save.
        # But we can call self.parent().player.save_config() after ensuring player has the data.
        # Player.connect_server sets self.plex.
        # Player.config() uses self.plex._baseurl and self.plex._token.
        # So saving config after connect_server should work.
        
        try:
            if hasattr(self.parent(), 'player'):
                self.parent().player.save_config()
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            
        self.accept()

    def on_worker_error(self, error_msg):
        logger.error(f"Worker error: {error_msg}")
        # If we are in PIN page, show error there or alert
        if self.stacked_widget.currentWidget() == self.page_pin:
             QMessageBox.warning(self, "Error", f"Authentication error: {error_msg}")
             self.cancel_pin_auth()
        elif self.stacked_widget.currentWidget() == self.page_servers:
             self.connection_status_label.setText(f"Error: {error_msg}")
             self.connect_server_button.setEnabled(True)
             self.server_combo.setEnabled(True)

    def try_manual_connect(self):
        url = self.url_edit.text().strip()
        token = self.token_edit.text().strip()

        if not url or not token:
            QMessageBox.warning(self, "Error", "Please enter URL and token")
            return

        try:
            # Try to connect
            self.plex = PlexServer(url, token)
            # Save credentials in main window
            if hasattr(self.parent(), 'player'):
                self.parent().player.connect_server(url, token)
                self.parent().player.save_config() # Save manually
            self.accept()
        except Unauthorized:
            QMessageBox.critical(self, "Error", "Invalid token")
        except NotFound:
            QMessageBox.critical(self, "Error", "Server not found")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")

    def closeEvent(self, event):
        self.cancel_pin_auth()
        super().closeEvent(event)


class AddTracksDialog(QDialog):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.setup_ui()
        self.load_artists()

    def setup_ui(self):
        self.setWindowTitle("Add Tracks")
        self.setMinimumSize(800, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Lists
        lists_layout = QHBoxLayout()
        
        # Artists
        artists_layout = QVBoxLayout()
        artists_header = QHBoxLayout()
        artists_header.setContentsMargins(0, 0, 0, 5)
        artists_label = QLabel("Artists")
        artists_label.setObjectName("header_label")
        artists_header.addWidget(artists_label)
        artists_header.addStretch(1)
        artists_layout.addLayout(artists_header)
        
        self.artists_list = QListWidget()
        self.artists_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.artists_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.artists_list.itemClicked.connect(self.load_albums)
        self.artists_list.itemDoubleClicked.connect(self.add_artist_to_playlist)
        artists_layout.addWidget(self.artists_list)
        
        add_all_artists_button = QPushButton("Add All Artists")
        add_all_artists_button.setObjectName("add_all_button")
        add_all_artists_button.clicked.connect(self.add_all_artists)
        artists_layout.addWidget(add_all_artists_button)
        
        lists_layout.addLayout(artists_layout)
        
        # Albums
        albums_layout = QVBoxLayout()
        albums_header = QHBoxLayout()
        albums_header.setContentsMargins(0, 0, 0, 5)
        albums_label = QLabel("Albums")
        albums_label.setObjectName("header_label")
        albums_header.addWidget(albums_label)
        albums_header.addStretch(1)
        albums_layout.addLayout(albums_header)
        
        self.albums_list = QListWidget()
        self.albums_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.albums_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.albums_list.itemClicked.connect(self.load_tracks)
        self.albums_list.itemDoubleClicked.connect(self.add_album_to_playlist)
        albums_layout.addWidget(self.albums_list)
        lists_layout.addLayout(albums_layout)
        
        # Tracks
        tracks_layout = QVBoxLayout()
        tracks_header = QHBoxLayout()
        tracks_header.setContentsMargins(0, 0, 0, 5)
        tracks_label = QLabel("Tracks")
        tracks_label.setObjectName("header_label")
        tracks_header.addWidget(tracks_label)
        tracks_header.addStretch(1)
        tracks_layout.addLayout(tracks_header)
        
        self.tracks_list = QListWidget()
        self.tracks_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_list.itemDoubleClicked.connect(self.add_track_to_playlist)
        tracks_layout.addWidget(self.tracks_list)
        lists_layout.addLayout(tracks_layout)
        
        layout.addLayout(lists_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_library)
        buttons_layout.addWidget(self.refresh_button)
        
        buttons_layout.addStretch(1)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(close_button)
        
        layout.addLayout(buttons_layout)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            #add_all_button {
                background-color: #444444;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                color: #ffffff;
                font-size: 12px;
                margin-top: 5px;
            }
            #add_all_button:hover {
                background-color: #555555;
            }
            #header_label {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
            }
            QListWidget {
                background-color: #2d2d2d;
                border: none;
                border-radius: 3px;
                padding: 3px;
                color: #ffffff;
            }
            QListWidget::item {
                padding: 3px;
                border-radius: 2px;
            }
            QListWidget::item:selected {
                background-color: #444444;
            }
            QListWidget::item:hover {
                background-color: #3d3d3d;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
        """)

        # Update refresh button style
        refresh_button_style = """
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """
        self.refresh_button.setStyleSheet(refresh_button_style)

    def refresh_library(self):
        """Refreshes the library"""
        try:
            self.player.load_artists()
            self.load_artists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to refresh library: {str(e)}")

    def load_artists(self):
        """Loads list of artists"""
        self.artists_list.clear()
        self.albums_list.clear()
        self.tracks_list.clear()
        for artist in self.player.artists:
            self.artists_list.addItem(artist.title)

    def load_albums(self, item):
        self.albums_list.clear()
        artist_index = self.artists_list.row(item)
        albums = self.player.load_albums(artist_index)
        self.albums_list.addItems(albums)

    def load_tracks(self, item):
        self.tracks_list.clear()
        album_index = self.albums_list.row(item)
        tracks = self.player.load_tracks(album_index)
        self.tracks_list.addItems(tracks)

    def add_artist_to_playlist(self, item):
        """Adds all tracks from the artist to the playlist"""
        try:
            artist_index = self.artists_list.row(item)
            artist = self.player.artists[artist_index]
            self.player.start_artist_tracks_loading(artist)
            self.accept()  # Close dialog after initiating loading
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add artist: {str(e)}")

    def add_album_to_playlist(self, item):
        """Adds all tracks from the album to the playlist"""
        try:
            album_index = self.albums_list.row(item)
            album = self.player.albums[album_index]
            self.player.start_album_tracks_loading(album)
            self.accept()  # Close dialog after initiating loading
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add album: {str(e)}")

    def add_track_to_playlist(self, item):
        """Adds a single track to the playlist"""
        track_index = self.tracks_list.row(item)
        track = self.player.tracks[track_index]
        self.parent().add_to_playlist(track)

    def add_all_artists(self):
        """Add all artists from Plex server"""
        try:
            # Disable UI elements
            self.refresh_button.setEnabled(False)
            self.artists_list.setEnabled(False)
            self.albums_list.setEnabled(False)
            
            # Get all artists directly from player
            artists = self.player.artists
            if not artists:
                QMessageBox.critical(self, "Error", "No artists found in the library")
                self._enable_ui()
                return
                
            # Start track loading for each artist sequentially
            for artist in artists:
                self.player.start_artist_tracks_loading(artist, stop_previous=False)
                
            # Close dialog after initiating loading for all artists
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load artists: {str(e)}")
            self._enable_ui()

    def _enable_ui(self):
        """Enable UI elements"""
        self.refresh_button.setEnabled(True)
        self.artists_list.setEnabled(True)
        self.albums_list.setEnabled(True)

    def add_all_albums(self):
        """Adds all albums from the current artist to the playlist"""
        try:
            if not self.albums_list.count():
                return
            tracks_batch = []
            for i in range(self.albums_list.count()):
                album = self.player.albums[i]
                tracks_batch.extend(album.tracks())
            if tracks_batch:
                for track in tracks_batch:
                    self.player.add_to_playlist(track)
            self.accept()  # Close dialog after successful addition
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add all albums: {str(e)}")

    def add_all_tracks(self):
        """Adds all tracks from the current album to the playlist"""
        try:
            if not self.tracks_list.count():
                return
            tracks_batch = [self.player.tracks[i] for i in range(self.tracks_list.count())]
            if tracks_batch:
                for track in tracks_batch:
                    self.player.add_to_playlist(track)
            self.accept()  # Close dialog after successful addition
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add all tracks: {str(e)}")

    def _add_remaining_tracks(self):
        """Add remaining tracks to the playlist."""
        try:
            if self.tracks_batch:
                logger.debug(f"Adding remaining {len(self.tracks_batch)} tracks to playlist")
                # Add tracks in larger batches for background loading
                batch_size = 100
                for i in range(0, len(self.tracks_batch), batch_size):
                    current_batch = self.tracks_batch[i:i + batch_size]
                    logger.debug(f"Adding remaining batch {i//batch_size + 1}")
                    self.player.add_tracks_batch_async(current_batch)
                
                logger.debug("All remaining tracks have been sent to player")
                self.tracks_batch = []
        except Exception as e:
            logger.error(f"Error adding remaining tracks: {str(e)}")


class LastFMAuthCallback(QObject):
    token_received = pyqtSignal(str)

class LastFMSettingsDialog(QDialog):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.auth_server = None
        self.auth_callback = LastFMAuthCallback()
        self.auth_callback.token_received.connect(self.handle_auth_callback)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        self.setWindowTitle("Last.fm Settings")
        layout = QVBoxLayout(self)

        # API Key
        api_key_layout = QHBoxLayout()
        api_key_label = QLabel("API Key:")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter your Last.fm API key")
        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.api_key_edit)
        layout.addLayout(api_key_layout)

        # API Secret
        api_secret_layout = QHBoxLayout()
        api_secret_label = QLabel("API Secret:")
        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setPlaceholderText("Enter your Last.fm API secret")
        api_secret_layout.addWidget(api_secret_label)
        api_secret_layout.addWidget(self.api_secret_edit)
        layout.addLayout(api_secret_layout)

        # Session Key
        session_key_layout = QHBoxLayout()
        session_key_label = QLabel("Session Key:")
        self.session_key_edit = QLineEdit()
        self.session_key_edit.setPlaceholderText("Will be obtained automatically")
        self.session_key_edit.setReadOnly(True)
        session_key_layout.addWidget(session_key_label)
        session_key_layout.addWidget(self.session_key_edit)
        layout.addLayout(session_key_layout)

        # Enable scrobbling checkbox
        self.scrobble_checkbox = QCheckBox("Enable scrobbling")
        layout.addWidget(self.scrobble_checkbox)

        # Buttons
        buttons_layout = QHBoxLayout()
        self.auth_button = QPushButton("Authorize")
        self.auth_button.clicked.connect(self.start_auth)
        buttons_layout.addWidget(self.auth_button)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        buttons_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)

    def load_settings(self):
        config = self.player.load_config()
        if config and "lastfm" in config:
            lastfm_config = config["lastfm"]
            self.api_key_edit.setText(lastfm_config.get("api_key", ""))
            self.api_secret_edit.setText(lastfm_config.get("api_secret", ""))
            self.session_key_edit.setText(lastfm_config.get("session_key", ""))
            self.scrobble_checkbox.setChecked(lastfm_config.get("enabled", False))

    def save_settings(self):
        logger.debug("Saving Last.fm settings")
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        session_key = self.session_key_edit.text().strip()
        enabled = self.scrobble_checkbox.isChecked()

        if not api_key or not api_secret:
            logger.error("Missing API Key or API Secret")
            QMessageBox.warning(self, "Error", "API Key and API Secret are required")
            return

        if not session_key:
            logger.error("Missing Session Key")
            QMessageBox.warning(self, "Error", "Please authorize your Last.fm account first")
            return

        logger.debug("Loading current config")
        # Update Last.fm configuration in the player
        logger.debug("Updating Last.fm configuration in player")
        self.player.lastfm.api_key = api_key
        self.player.lastfm.api_secret = api_secret
        self.player.lastfm.session_key = session_key
        self.player.lastfm.enabled = enabled
        
        logger.debug("Saving config")
        self.player.save_config()
        
        logger.debug("Settings saved successfully")
        self.accept()

    def start_auth(self):
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Error", "Please enter your Last.fm API Key first")
            return

        # Start the auth server
        self.auth_server = LastFMAuthServer(self.auth_callback.token_received.emit)
        try:
            self.auth_server.start()
            # Open the auth URL in the browser with the correct port
            open_auth_url(api_key, self.auth_server.port)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start auth server: {str(e)}")
            if self.auth_server:
                self.auth_server.stop()
                self.auth_server = None

    def handle_auth_callback(self, token: str):
        logger.debug(f"Handling auth callback with token: {token}")
        # Stop the auth server
        if self.auth_server:
            logger.debug("Stopping auth server")
            self.auth_server.stop()
            self.auth_server = None

        # Ensure scrobbler has up-to-date API key and secret
        self.player.lastfm.api_key = self.api_key_edit.text().strip()
        self.player.lastfm.api_secret = self.api_secret_edit.text().strip()

        # Get session key using the token
        try:
            logger.debug("Getting session key from Last.fm")
            session_key = self.player.lastfm.get_session_key(token)
            if session_key:
                logger.debug(f"Got session key: {session_key}")
                self.session_key_edit.setText(session_key)
                # Auto-save settings after successful authorization
                logger.debug("Auto-saving settings")
                self.save_settings()
                QMessageBox.information(self, "Success", "Successfully authorized with Last.fm")
            else:
                logger.error("Failed to get session key - empty response")
                QMessageBox.warning(self, "Error", "Failed to get session key")
        except Exception as e:
            logger.error(f"Error getting session key: {e}")
            QMessageBox.warning(self, "Error", f"Failed to get session key: {str(e)}")

    def closeEvent(self, event):
        # Stop the auth server if it's running
        if self.auth_server:
            self.auth_server.stop()
        super().closeEvent(event) 
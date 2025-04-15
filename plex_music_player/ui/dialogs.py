import os
import json
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
)
from plexapi.server import PlexServer
from plexapi.audio import Track
from plexapi.exceptions import Unauthorized, NotFound
from PyQt6.QtCore import Qt, QTimer
from ..models.player import TrackLoader, ArtistLoader
from ..lib.logger import Logger

logger = Logger()

class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plex = None
        self.setup_ui()
        
        # Load saved credentials
        try:
            config_path = os.path.expanduser("~/.config/plex_music_player/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    if 'plex' in config:
                        self.url_edit.setText(config['plex']['url'])
                        self.token_edit.setText(config['plex']['token'])
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")

    def setup_ui(self):
        self.setWindowTitle("Connect to Plex")
        layout = QVBoxLayout(self)

        # Server URL
        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("http://localhost:32400")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        layout.addLayout(url_layout)

        # Token
        token_layout = QHBoxLayout()
        token_label = QLabel("Token:")
        self.token_edit = QLineEdit()
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_edit)
        layout.addLayout(token_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.try_connect)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.connect_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)

    def try_connect(self):
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
            self.accept()
        except Unauthorized:
            QMessageBox.critical(self, "Error", "Invalid token")
        except NotFound:
            QMessageBox.critical(self, "Error", "Server not found")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")


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
                background-color: #0078d4;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
                color: #ffffff;
                font-size: 12px;
                margin-top: 5px;
            }
            #add_all_button:hover {
                background-color: #1e8ae6;
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
                background-color: #0078d4;
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
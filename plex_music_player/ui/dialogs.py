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
from PyQt6.QtCore import Qt

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
            print(f"Error loading credentials: {e}")

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
                self.parent().player.connect(url, token)
            self.accept()
        except Unauthorized:
            QMessageBox.critical(self, "Error", "Invalid token")
        except NotFound:
            QMessageBox.critical(self, "Error", "Server not found")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")

class AddTrackDialog(QDialog):
    def __init__(self, plex: PlexServer, parent=None):
        super().__init__(parent)
        self.plex = plex
        self.artists = []
        self.albums = []
        self.tracks = []
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Добавить трек")
        layout = QVBoxLayout(self)

        # Выбор исполнителя
        artist_layout = QHBoxLayout()
        artist_label = QLabel("Исполнитель:")
        self.artist_combo = QComboBox()
        self.artist_combo.currentIndexChanged.connect(self.load_albums)
        artist_layout.addWidget(artist_label)
        artist_layout.addWidget(self.artist_combo)
        layout.addLayout(artist_layout)

        # Выбор альбома
        album_layout = QHBoxLayout()
        album_label = QLabel("Альбом:")
        self.album_combo = QComboBox()
        self.album_combo.currentIndexChanged.connect(self.load_tracks)
        album_layout.addWidget(album_label)
        album_layout.addWidget(self.album_combo)
        layout.addLayout(album_layout)

        # Выбор трека
        track_layout = QHBoxLayout()
        track_label = QLabel("Трек:")
        self.track_combo = QComboBox()
        track_layout.addWidget(track_label)
        track_layout.addWidget(self.track_combo)
        layout.addLayout(track_layout)

        # Кнопки
        buttons_layout = QHBoxLayout()
        add_button = QPushButton("Добавить")
        add_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        self.load_artists()

    def load_artists(self):
        try:
            self.artists = self.plex.library.search(libtype="artist")
            self.artist_combo.clear()
            for artist in self.artists:
                self.artist_combo.addItem(artist.title)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить исполнителей: {str(e)}")

    def load_albums(self):
        try:
            artist_index = self.artist_combo.currentIndex()
            if artist_index < 0:
                return
            artist = self.artists[artist_index]
            self.albums = artist.albums()
            self.album_combo.clear()
            for album in self.albums:
                self.album_combo.addItem(album.title)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить альбомы: {str(e)}")

    def load_tracks(self):
        try:
            album_index = self.album_combo.currentIndex()
            if album_index < 0:
                return
            album = self.albums[album_index]
            self.tracks = album.tracks()
            self.track_combo.clear()
            for track in self.tracks:
                self.track_combo.addItem(f"{track.index}. {track.title}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить треки: {str(e)}")

    def get_selected_track(self) -> Track:
        """Возвращает выбранный трек"""
        try:
            track_index = self.track_combo.currentIndex()
            if track_index < 0:
                return None
            return self.tracks[track_index]
        except:
            return None

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
        artists_label = QLabel("Artists")
        artists_header.addWidget(artists_label)
        
        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setFixedSize(24, 24)
        self.refresh_button.clicked.connect(self.refresh_library)
        artists_header.addWidget(self.refresh_button)
        artists_header.addStretch(1)
        artists_layout.addLayout(artists_header)
        
        self.artists_list = QListWidget()
        self.artists_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.artists_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.artists_list.itemClicked.connect(self.load_albums)
        self.artists_list.itemDoubleClicked.connect(self.add_artist_to_playlist)
        artists_layout.addWidget(self.artists_list)
        lists_layout.addLayout(artists_layout)
        
        # Albums
        albums_layout = QVBoxLayout()
        albums_label = QLabel("Albums")
        albums_layout.addWidget(albums_label)
        self.albums_list = QListWidget()
        self.albums_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.albums_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.albums_list.itemClicked.connect(self.load_tracks)
        self.albums_list.itemDoubleClicked.connect(self.add_album_to_playlist)
        albums_layout.addWidget(self.albums_list)
        lists_layout.addLayout(albums_layout)
        
        # Tracks
        tracks_layout = QVBoxLayout()
        tracks_label = QLabel("Tracks")
        tracks_layout.addWidget(tracks_label)
        self.tracks_list = QListWidget()
        self.tracks_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_list.itemDoubleClicked.connect(self.add_track_to_playlist)
        tracks_layout.addWidget(self.tracks_list)
        lists_layout.addLayout(tracks_layout)
        
        layout.addLayout(lists_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
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
        artist_index = self.artists_list.row(item)
        artist = self.player.artists[artist_index]
        
        try:
            # Collect all tracks at once
            all_tracks = []
            albums = artist.albums()
            for album in albums:
                all_tracks.extend(album.tracks())
            
            # Update UI at once
            self.parent().add_tracks_batch(all_tracks)
        except Exception as e:
            print(f"Error adding artist tracks: {e}")

    def add_album_to_playlist(self, item):
        """Adds all tracks from the album to the playlist"""
        album_index = self.albums_list.row(item)
        album = self.player.albums[album_index]
        
        try:
            tracks = album.tracks()
            self.parent().add_tracks_batch(tracks)
        except Exception as e:
            print(f"Error adding album tracks: {e}")

    def add_track_to_playlist(self, item):
        """Adds a single track to the playlist"""
        track_index = self.tracks_list.row(item)
        track = self.player.tracks[track_index]
        self.parent().add_to_playlist(track) 
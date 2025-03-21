from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QSlider,
    QDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from plex_music_player.models.player import PlayerThread
from plex_music_player.ui.dialogs import ConnectionDialog, AddTracksDialog
from plex_music_player.lib.utils import format_time, format_track_info, load_cover_image


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Start the player thread and wait for the player to be ready
        self.player_thread = PlayerThread()
        self.player_thread.player_ready.connect(self.on_player_ready)
        self.player_thread.start()

        # Setup initial UI showing connection status
        self.setup_ui(show_connect_only=True)
        
        self.setMinimumSize(300, 700)
        self.setMaximumSize(450, 900)
    
    @pyqtSlot(object)
    def on_player_ready(self, player):
        self.player = player
        self.player.playback_state_changed.connect(self._on_playback_state_changed)
        self.player.track_changed.connect(self.update_playback_ui)
        self.player.track_changed.connect(self.update_playlist_selection)
        
        # Attempt auto-connect using saved configuration
        try:
            config = self.player.load_config()
            if config and 'plex' in config:
                plex_config = config['plex']
                self.player.connect_server(plex_config['url'], plex_config['token'])
                self.player.load_artists()  # Load library
                # Rebuild UI with full controls if connection succeeds
                self.setup_ui(show_connect_only=False)
            else:
                # No valid configuration found; update status message and show connect button
                self.status_label.setText("Could not connect.\nPlease press 'Connect to Plex'.")
                self.connect_button.show()
        except Exception as e:
            print(f"Error during auto-connect: {e}")
            self.status_label.setText("Error connecting.\nPlease press 'Connect to Plex'.")
            self.connect_button.show()

    def setup_ui(self, show_connect_only: bool = True) -> None:
        """Updated setup_ui method to keep the track info label truly centered,
        especially in narrow windows."""
        self.setWindowTitle("Plex Music Player")
        
        # Set margins and spacing for the main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(layout)

        if show_connect_only:
            # Show a connection status screen with a status label and connect button
            connect_container = QVBoxLayout()
            connect_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.status_label = QLabel("Connecting to Plex...")
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            connect_container.addWidget(self.status_label)
            
            self.connect_button = QPushButton("Connect to Plex")
            self.connect_button.setFixedWidth(150)
            self.connect_button.clicked.connect(self.show_connection_dialog)
            self.connect_button.hide()
            connect_container.addWidget(self.connect_button)
            
            layout.addLayout(connect_container)
            return

        # --- Full UI setup below ---
        # Center section: cover and track info
        center_container = QVBoxLayout()
        center_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_container.setSpacing(15)

        # Cover container
        cover_container = QHBoxLayout()
        cover_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_container.setContentsMargins(0, 0, 0, 0)
        cover_container.setSpacing(0)
        self.cover_label = QLabel()
        self.cover_label.setFixedHeight(300)
        self.cover_label.setStyleSheet("border: none; background: transparent;")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_container.addWidget(self.cover_label)
        center_container.addLayout(cover_container)

        # Track info container
        track_info_container = QHBoxLayout()
        track_info_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Changed margins to (0,0,0,0) and removed min/max width lines for track_info
        track_info_container.setContentsMargins(0, 0, 0, 0)

        self.track_info = QLabel("No track")
        self.track_info.setWordWrap(True)
        self.track_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Removed self.track_info.setMinimumWidth(...) / setMaximumWidth(...)
        track_info_container.addWidget(self.track_info)
        center_container.addLayout(track_info_container)

        layout.addLayout(center_container)

        # Playlist section
        playlist_widget = QWidget()
        playlist_layout = QVBoxLayout(playlist_widget)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(5)
        playlist_header = QHBoxLayout()
        
        self.add_button = QPushButton("✙")
        self.add_button.setFixedSize(30, 30)
        self.add_button.setStyleSheet(self.get_button_style())
        self.add_button.clicked.connect(self.show_add_tracks_dialog)
        playlist_header.addWidget(self.add_button)
        
        self.shuffle_button = QPushButton("⇄")
        self.shuffle_button.setFixedSize(30, 30)
        self.shuffle_button.setStyleSheet(self.get_button_style())
        self.shuffle_button.clicked.connect(self.shuffle_playlist)
        playlist_header.addWidget(self.shuffle_button)
        
        self.remove_button = QPushButton("✖")
        self.remove_button.setFixedSize(30, 30)
        self.remove_button.setStyleSheet(self.get_button_style())
        self.remove_button.clicked.connect(self.remove_from_playlist)
        playlist_header.addWidget(self.remove_button)
        
        self.clear_button = QPushButton("☠︎︎")
        self.clear_button.setFixedSize(30, 30)
        self.clear_button.setStyleSheet(self.get_button_style())
        self.clear_button.clicked.connect(self.clear_playlist)
        playlist_header.addWidget(self.clear_button)
        
        playlist_layout.addLayout(playlist_header)
        
        self.playlist_list = QListWidget()
        self.playlist_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.playlist_list.itemDoubleClicked.connect(self.play_from_playlist)
        playlist_layout.addWidget(self.playlist_list)
        
        layout.addWidget(playlist_widget)

        # Bottom control panel
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(10)

        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderMoved.connect(self.seek_position)
        controls_layout.addWidget(self.progress_slider)

        # Time label
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-family: 'Courier New', Courier, monospace; font-weight: bold;")
        controls_layout.addWidget(self.time_label)

        # Control buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_layout.setSpacing(10)

        self.prev_button = QPushButton("⏮")
        self.prev_button.setEnabled(False)
        self.prev_button.setFixedSize(40, 40)
        self.prev_button.clicked.connect(self.play_previous_track)
        buttons_layout.addWidget(self.prev_button)

        self.play_button = QPushButton("▶")
        self.play_button.setEnabled(False)
        self.play_button.setFixedSize(40, 40)
        self.play_button.clicked.connect(self.toggle_play)
        buttons_layout.addWidget(self.play_button)

        self.next_button = QPushButton("⏭")
        self.next_button.setEnabled(False)
        self.next_button.setFixedSize(40, 40)
        self.next_button.clicked.connect(self.play_next_track)
        buttons_layout.addWidget(self.next_button)

        controls_layout.addLayout(buttons_layout)

        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.setFixedHeight(20)
        controls_layout.addWidget(self.volume_slider)

        layout.addLayout(controls_layout)

        # Apply styles
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 3px;
                padding: 3px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
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
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background-color: #2d2d2d;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background-color: #0078d4;
                border: none;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background-color: #0078d4;
                border-radius: 2px;
            }
            #track_info {
                font-size: 14px;
                line-height: 1.4;
                font-weight: 500;
                color: #ffffff;
                padding: 10px;
                margin: 0 10px;
            }
            #time_label {
                font-size: 12px;
                color: #888888;
            }
        """)

        # Set object names for special styling
        self.track_info.setObjectName("track_info")
        self.time_label.setObjectName("time_label")

        # Update control buttons style
        control_buttons_style = """
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                padding: 0px;
                color: white;
            }
            QPushButton:hover {
                background-color: #1e8ae6;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """
        for btn in [self.prev_button, self.play_button, self.next_button]:
            btn.setStyleSheet(control_buttons_style)
            btn.setFixedSize(40, 40)

        # Update playlist buttons style
        playlist_buttons_style = """
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
        for btn in [self.add_button, self.shuffle_button, self.remove_button, self.clear_button]:
            btn.setStyleSheet(playlist_buttons_style)
            btn.setFixedSize(24, 24)

        # Timer for progress updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress)
        self.update_timer.start(1000)

        # Load saved playlist if connected
        if self.player.plex:
            self.player.load_playlist()
            self.playlist_list.clear()
            for track in self.player.playlist:
                year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
                self.playlist_list.addItem(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
            self.update_playlist_selection()
            self.play_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            self.player.playback_state_changed.connect(self.update_play_button)
            if not self.player.is_playing():
                self.play_button.setText("▶")


    def show_connection_dialog(self) -> None:
        """Show connection dialog."""
        dialog = ConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.plex:
            self.player.load_artists()  # Load library
            self.setup_ui(show_connect_only=False)

    def show_add_tracks_dialog(self) -> None:
        """Show dialog for adding tracks."""
        dialog = AddTracksDialog(self.player, self)
        dialog.exec()

    def update_playback_ui(self) -> None:
        """Updates playback UI elements."""
        # Update play/pause icon according to player's state.
        self.play_button.setText("⏸" if self.player.is_playing() else "▶")
        self.progress_slider.setEnabled(True)
        self.progress_slider.setMaximum(self.player.current_track.duration)
        self.progress_slider.setValue(0)
        self.update_time_label(0, self.player.current_track.duration)
        self.track_info.setText(format_track_info(self.player.current_track))
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self.load_cover()
        self.update_playlist_selection()

    def load_cover(self) -> None:
        """Load and display album cover."""
        if not self.player.current_track or not self.player.plex:
            return
        pixmap = load_cover_image(self.player.plex, self.player.current_track)
        if pixmap:
            window_width = self.width()
            window_height = self.height()
            scaled_pixmap = pixmap.scaled(window_width, window_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(scaled_pixmap)
        else:
            self.cover_label.clear()

    def toggle_play(self) -> None:
        """Toggle play/pause state. If no track is loaded but a playlist exists,
        start playing the first track and update the UI (including loading the cover)."""
        if not self.player.current_track and self.player.playlist:
            self.player.current_playlist_index = 0
            self.player.current_track = self.player.playlist[0]
        if not self.player.is_playing():
            if not self.player._play_track_impl():
                return
        else:
            self.player.toggle_play()
        self.update_playback_ui()


    def seek_position(self, position: int) -> None:
        """Seek to specified position."""
        self.player.seek_position(position)

    def update_progress(self) -> None:
        """Update playback progress."""
        if self.player.is_playing() and self.player.current_track:
            current_pos = self.player.get_current_position()
            self.progress_slider.setValue(current_pos)
            self.update_time_label(current_pos, self.player.current_track.duration)
            if current_pos >= self.player.current_track.duration:
                print("Track ended, playing next track...")
                self.play_next_track()
        else:
            if self.player.current_track and self.progress_slider.value() >= self.player.current_track.duration:
                self.play_next_track()

    def update_time_label(self, current: int, total: int) -> None:
        """Update time display."""
        current_str = format_time(current)
        total_str = format_time(total)
        self.time_label.setText(f"{current_str} / {total_str}")

    def play_next_track(self) -> None:
        """Play the next track."""
        if self.player.play_next_track():
            self.update_playback_ui()

    def play_previous_track(self) -> None:
        """Play the previous track."""
        if self.player.play_previous_track():
            self.update_playback_ui()

    def update_playlist_selection(self) -> None:
        """Update current track selection in playlist."""
        try:
            for i in range(self.playlist_list.count()):
                item = self.playlist_list.item(i)
                if item:
                    item.setSelected(False)
            if self.player.current_track and self.player.current_playlist_index >= 0:
                current_item = self.playlist_list.item(self.player.current_playlist_index)
                if current_item:
                    current_item.setSelected(True)
                    self.playlist_list.scrollToItem(current_item)
        except Exception as e:
            print(f"Error updating selection: {e}")

    def clear_playlist(self) -> None:
        """Clear the playlist and safely pause playback if necessary."""
        # Pause playback if a track is currently playing, since no stop() method exists
        if self.player.is_playing():
            self.player.toggle_play()  # Pause playback
        # Clear current track to avoid NoneType attribute errors
        self.player.current_track = None

        self.player.clear_playlist()
        self.playlist_list.clear()
        self.play_button.setText("▶")
        self.play_button.setEnabled(False)
        self.progress_slider.setEnabled(False)
        self.progress_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.track_info.setText("No track")
        self.cover_label.clear()
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.player.save_playlist()

    def remove_from_playlist(self) -> None:
        """Remove selected tracks from playlist."""
        selected_items = self.playlist_list.selectedItems()
        if not selected_items:
            return
        indices = [self.playlist_list.row(item) for item in selected_items]

        # If the currently playing track is being removed, stop playback safely
        if self.player.current_track and self.player.current_playlist_index in indices:
            self.player.stop()  # Stop playback safely
            self.player.current_track = None
            self.play_button.setText("▶")
            self.progress_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")
            self.track_info.setText("No track")
            self.cover_label.clear()

        self.player.remove_from_playlist(indices)
        for index in sorted(indices, reverse=True):
            self.playlist_list.takeItem(index)
        self.player.save_playlist()

    def play_from_playlist(self, item) -> None:
        """Play track from playlist on double click."""
        try:
            index = self.playlist_list.row(item)
            if 0 <= index < len(self.player.playlist):
                self.player.current_playlist_index = index
                self.player.current_track = self.player.playlist[index]
                if self.player._play_track_impl():
                    self.update_playback_ui()
                    self.play_button.setEnabled(True)
                    self.prev_button.setEnabled(True)
                    self.next_button.setEnabled(True)
        except Exception as e:
            print(f"Error playing from playlist: {e}")

    def shuffle_playlist(self) -> None:
        """Shuffle the playlist."""
        self.player.shuffle_playlist()
        self.playlist_list.clear()
        for track in self.player.playlist:
            year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
            self.playlist_list.addItem(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
        self.update_playlist_selection()

    def _on_playback_state_changed(self, is_playing: bool) -> None:
        """Handle playback state changes."""
        self.play_button.setText("⏸" if is_playing else "▶")
        self.progress_slider.setEnabled(is_playing)

    def add_to_playlist(self, track) -> None:
        """Add a track to the playlist."""
        self.player.add_to_playlist(track)
        year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
        self.playlist_list.addItem(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
        if len(self.player.playlist) == 1:
            self.player.current_playlist_index = 0
            self.player.current_track = track
            if self.player._play_track_impl():
                self.update_playback_ui()
                self.play_button.setEnabled(True)
                self.prev_button.setEnabled(True)
                self.next_button.setEnabled(True)
        self.player.save_playlist()

    def add_tracks_batch(self, tracks):
        """Batch add tracks to the playlist."""
        if not tracks:
            return
        self.player.add_tracks_batch(tracks)
        items = []
        for track in tracks:
            year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
            items.append(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
        self.playlist_list.addItems(items)
        if len(self.player.playlist) == len(tracks):
            self.player.current_playlist_index = 0
            self.player.current_track = tracks[0]
            if self.player._play_track_impl():
                self.update_playback_ui()
                self.play_button.setEnabled(True)
                self.prev_button.setEnabled(True)
                self.next_button.setEnabled(True)
        self.player.save_playlist()

    def closeEvent(self, event) -> None:
        self.player.save_playlist()
        self.player.close()
        super().closeEvent(event)

    def update_play_button(self, is_playing: bool) -> None:
        """Update the play/pause button based on playback state."""
        self.play_button.setText("⏸" if is_playing else "▶")
        self.play_button.setEnabled(True)

    def change_volume(self, value: int) -> None:
        """Change the player's volume."""
        self.player._audio_output.setVolume(value / 100.0)
    
    def get_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 15px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1e8ae6;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """

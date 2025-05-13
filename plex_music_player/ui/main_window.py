import sys
import time
import re

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
    QProgressBar,
    QSplitter,
)
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QSize
from plex_music_player.models.player import PlayerThread
from plex_music_player.ui.dialogs import ConnectionDialog, AddTracksDialog, LastFMSettingsDialog
from plex_music_player.lib.utils import format_time, format_track_info, load_cover_image
from plex_music_player.lib.utils import resource_path
from plex_music_player.lib.color_utils import get_dominant_color, get_contrasting_text_color, adjust_color_brightness
from plex_music_player.lib.logger import Logger
from plex_music_player.ui.custom_title_bar import CustomTitleBar

logger = Logger()

class DraggableCoverLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mouse_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._mouse_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._mouse_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._mouse_pos = None

class MainWindow(QMainWindow):
    RESIZE_MARGIN = 6

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        # Start the player thread and wait for the player to be ready
        self.player_thread = PlayerThread()
        self.player_thread.player_ready.connect(self.on_player_ready)
        self.player_thread.start()
        
        self.loading_tracks = False
        self.tracks_to_load = 0
        self.tracks_loaded = 0
        
        # Setup initial UI showing connection status
        self.setup_ui(show_connect_only=True)
        
        # Set minimum size and store initial width
        self.setMinimumSize(300, 700)
        self.initial_width = self.width()
        self.is_wide_mode = self.width() >= self.initial_width * 1.5
        
        self._resizing = False
        self._resize_edge = None
        self._mouse_pos = None
        self._start_geom = None
    
    @pyqtSlot(object)
    def on_player_ready(self, player):
        self.player = player
        self.player.playback_state_changed.connect(self._on_playback_state_changed)
        self.player.track_changed.connect(self.update_playback_ui)
        self.player.track_changed.connect(self.update_playlist_selection)
        self.player.tracks_batch_loaded.connect(self.on_tracks_batch_loaded)
        self.player.lastfm_status_changed.connect(self._on_lastfm_status_changed)
        
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
            logger.error(f"Error during auto-connect: {e}")
            self.status_label.setText("Error connecting.\nPlease press 'Connect to Plex'.")
            self.connect_button.show()

    def __load_window_icons(self) -> None:
        if sys.platform == "win32":
            import ctypes
            myappid = u'mycompany.myproduct.subproduct.version'  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        if sys.platform in ["linux",  "win32"]:
            self.setWindowIcon(QIcon(resource_path("icon/icon_256x256.png")))

    def resizeEvent(self, event):
        """Handle window resize events to switch between layouts"""
        super().resizeEvent(event)
        if not hasattr(self, 'player'):
            return
            
        new_width = event.size().width()
        should_be_wide = new_width >= self.initial_width * 1.5
        
        if should_be_wide != self.is_wide_mode:
            current_track = self.player.current_track
            current_position = self.player.get_current_position() if self.player.is_playing() else 0
            is_playing = self.player.is_playing()
            volume = self.volume_slider.value()
            current_playlist_index = self.player.current_playlist_index
            
            self.is_wide_mode = should_be_wide
            self.setup_ui(show_connect_only=False)
            
            if current_track:
                self.player.current_track = current_track
                self.player.current_playlist_index = current_playlist_index
                self.track_info.setText(format_track_info(current_track))
                self.progress_slider.setMaximum(current_track.duration)
                self.progress_slider.setValue(current_position)
                self.progress_slider.setEnabled(True)
                self.update_time_label(current_position, current_track.duration)
                self.load_cover()
                
                if is_playing:
                    self.play_button.setIcon(QIcon(resource_path("icons_svg/pause.svg")))
                else:
                    self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))
                    
                self.volume_slider.setValue(volume)
                
                self.play_button.setEnabled(True)
                self.prev_button.setEnabled(True)
                self.next_button.setEnabled(True)
                
                if self.player.playlist:
                    self.playlist_list.clear()
                    for track in self.player.playlist:
                        year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
                        self.playlist_list.addItem(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
                    self.update_playlist_selection()
                    if current_playlist_index >= 0 and current_playlist_index < self.playlist_list.count():
                        self.playlist_list.scrollToItem(self.playlist_list.item(current_playlist_index))
            
        # Update cover size
        if hasattr(self, 'cover_label') and hasattr(self, 'player') and self.player.current_track:
            self.load_cover()
            
    def setup_ui(self, show_connect_only: bool = True) -> None:
        self.setWindowTitle("Plex Music Player")
        self.__load_window_icons()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


        self.title_bar = CustomTitleBar(self, color="#1e1e1e", button_color="#ffffff")
        layout.addWidget(self.title_bar)

        main_content = QVBoxLayout()
        main_content.setContentsMargins(10, 10, 10, 10)
        main_content.setSpacing(10)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setLayout(layout)

        if show_connect_only:
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
            main_content.addLayout(connect_container)
            layout.addLayout(main_content)
            return

        if self.is_wide_mode:
            # Create splitter for resizable layout
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.setChildrenCollapsible(False)  # Prevent sections from being collapsed
            
            # Left side - playlist
            self.playlist_widget = self.create_playlist_widget()
            splitter.addWidget(self.playlist_widget)
            
            # Right side container
            right_container = QWidget()
            right_layout = QVBoxLayout(right_container)
            right_layout.setSpacing(5)
            
            # Cover container (takes most space)
            cover_container = QWidget()
            cover_layout = QVBoxLayout(cover_container)
            cover_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cover_label = DraggableCoverLabel()
            self.cover_label.setMinimumHeight(400)  # Minimum height for cover
            self.cover_label.setStyleSheet("border: none; background: transparent;")
            self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover_layout.addWidget(self.cover_label)
            right_layout.addWidget(cover_container, stretch=80)
            
            # Bottom info and controls container
            bottom_container = QWidget()
            bottom_layout = QVBoxLayout(bottom_container)
            bottom_layout.setSpacing(5)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            
            # Track info with smaller height
            self.track_info = QLabel("No track")
            self.track_info.setWordWrap(True)
            self.track_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.track_info.setMaximumHeight(50)
            bottom_layout.addWidget(self.track_info)
            
            # Controls
            controls_layout = self.create_controls_layout()
            bottom_layout.addLayout(controls_layout)
            
            right_layout.addWidget(bottom_container, stretch=20)
            
            splitter.addWidget(right_container)
            
            # Set initial sizes (40% : 60%)
            splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])
            
            # Add splitter to layout
            layout.addWidget(splitter)
            
            # Style the splitter handle
            splitter.setStyleSheet("""
                QSplitter::handle {
                    background-color: #2d2d2d;
                    width: 2px;
                }
                QSplitter::handle:hover {
                    background-color: #0078d4;
                }
            """)
        else:
            # Normal mode layout
            main_content = QVBoxLayout()  # Changed to QVBoxLayout for vertical stacking
            main_content.setSpacing(10)
            
            # Top section with cover and track info
            top_container = QVBoxLayout()
            top_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top_container.setSpacing(15)

            # Cover container
            cover_container = QHBoxLayout()
            cover_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cover_label = DraggableCoverLabel()
            self.cover_label.setFixedHeight(300)
            self.cover_label.setStyleSheet("border: none; background: transparent;")
            self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover_container.addWidget(self.cover_label)
            top_container.addLayout(cover_container)

            # Track info
            self.track_info = QLabel("No track")
            self.track_info.setWordWrap(True)
            self.track_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top_container.addWidget(self.track_info)
            
            main_content.addLayout(top_container)
            
            # Controls section
            controls_layout = self.create_controls_layout()
            main_content.addLayout(controls_layout)
            
            # Playlist section at the bottom
            self.playlist_widget = self.create_playlist_widget()
            main_content.addWidget(self.playlist_widget)
            
            layout.addLayout(main_content)
        
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
                background-color: #444444;
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
                background-color: #444444;
                border: none;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background-color: #444444;
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
            #loading_progress {
                background-color: #2d2d2d;
                border: none;
                border-radius: 3px;
                height: 2px;
                margin: 0px;
                text-align: center;
            }
            #loading_progress::chunk {
                background-color: #444444;
            }
        """)

        # Set object names for special styling
        self.track_info.setObjectName("track_info")
        self.time_label.setObjectName("time_label")

        # Reset button styles to default
        self._reset_button_styles()

        # Timer for progress updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress)
        self.update_timer.start(1000)

        # Load saved playlist if connected
        if hasattr(self, 'player') and self.player.plex:
            self.player.load_playlist()
            self.playlist_list.clear()
            for track in self.player.playlist:
                year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
                self.playlist_list.addItem(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
            self.update_playlist_selection()
            
            # Schedule scrolling to current track after UI is fully initialized
            if self.player.playlist and self.player.current_playlist_index >= 0:
                if self.player.current_playlist_index < len(self.player.playlist):
                    QTimer.singleShot(100, self.scroll_to_current_track)
            
            self.play_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            self.player.playback_state_changed.connect(self.update_play_button)
            if not self.player.is_playing():
                self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))

    def create_playlist_widget(self) -> QWidget:
        """Create playlist widget with controls"""
        playlist_widget = QWidget()
        playlist_layout = QVBoxLayout(playlist_widget)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(5)
        
        # Playlist controls
        playlist_header = QHBoxLayout()
        
        self.add_button = QPushButton()
        self.add_button.setIcon(QIcon(resource_path("icons_svg/add_to_playlist.svg")))
        self.add_button.setIconSize(QSize(11, 11))
        self.add_button.setFixedSize(30, 30)
        self.add_button.setStyleSheet(self.get_button_style())
        self.add_button.setToolTip("Add to playlist")
        self.add_button.clicked.connect(self.show_add_tracks_dialog)
        playlist_header.addWidget(self.add_button)
        
        self.shuffle_button = QPushButton()
        self.shuffle_button.setIcon(QIcon(resource_path("icons_svg/shuffle_playlist.svg")))
        self.shuffle_button.setIconSize(QSize(11, 11))
        self.shuffle_button.setFixedSize(30, 30)
        self.shuffle_button.setStyleSheet(self.get_button_style())
        self.shuffle_button.setToolTip("Shuffle playlist")
        self.shuffle_button.clicked.connect(self.shuffle_playlist)
        playlist_header.addWidget(self.shuffle_button)
        
        self.remove_button = QPushButton()
        self.remove_button.setIcon(QIcon(resource_path("icons_svg/remove_track.svg")))
        self.remove_button.setIconSize(QSize(11, 11))
        self.remove_button.setFixedSize(30, 30)
        self.remove_button.setStyleSheet(self.get_button_style())
        self.remove_button.setToolTip("Remove selected track")
        self.remove_button.clicked.connect(self.remove_from_playlist)
        playlist_header.addWidget(self.remove_button)
        
        self.clear_button = QPushButton()
        self.clear_button.setIcon(QIcon(resource_path("icons_svg/clear_playlist.svg")))
        self.clear_button.setIconSize(QSize(11, 11))
        self.clear_button.setFixedSize(30, 30)
        self.clear_button.setStyleSheet(self.get_button_style())
        self.clear_button.setToolTip("Clear playlist")
        self.clear_button.clicked.connect(self.clear_playlist)
        playlist_header.addWidget(self.clear_button)

        self.scroll_to_current_button = QPushButton()
        self.scroll_to_current_button.setIcon(QIcon(resource_path("icons_svg/locate_track.svg")))
        self.scroll_to_current_button.setIconSize(QSize(11, 11))
        self.scroll_to_current_button.setFixedSize(30, 30)
        self.scroll_to_current_button.setStyleSheet(self.get_button_style())
        self.scroll_to_current_button.setToolTip("Show current track")
        self.scroll_to_current_button.clicked.connect(self.scroll_to_current_track)
        playlist_header.addWidget(self.scroll_to_current_button)
        
        playlist_layout.addLayout(playlist_header)
        
        # Playlist list
        self.playlist_list = QListWidget()
        self.playlist_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.playlist_list.itemDoubleClicked.connect(self.play_from_playlist)
        playlist_layout.addWidget(self.playlist_list)
        
        return playlist_widget
        
    def create_controls_layout(self) -> QVBoxLayout:
        """Create playback controls layout"""
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(10)

        # Progress slider
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderReleased.connect(lambda: self.seek_position(self.progress_slider.value()))
        controls_layout.addWidget(self.progress_slider)

        # Time label
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-family: 'Courier New', Courier, monospace; font-weight: bold;")
        controls_layout.addWidget(self.time_label)

        # Control buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_layout.setSpacing(10)

        self.prev_button = QPushButton()
        self.prev_button.setIcon(QIcon(resource_path("icons_svg/previous.svg")))
        self.prev_button.setIconSize(QSize(14, 14))
        self.prev_button.setEnabled(False)
        self.prev_button.setFixedSize(40, 40)
        self.prev_button.clicked.connect(self.play_previous_track)
        buttons_layout.addWidget(self.prev_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))
        self.play_button.setIconSize(QSize(14, 14))
        self.play_button.setEnabled(False)
        self.play_button.setFixedSize(40, 40)
        self.play_button.clicked.connect(self.toggle_play)
        buttons_layout.addWidget(self.play_button)

        self.next_button = QPushButton()
        self.next_button.setIcon(QIcon(resource_path("icons_svg/next.svg")))
        self.next_button.setIconSize(QSize(14, 14))
        self.next_button.setEnabled(False)
        self.next_button.setFixedSize(40, 40)
        self.next_button.clicked.connect(self.play_next_track)
        buttons_layout.addWidget(self.next_button)

        controls_layout.addLayout(buttons_layout)

        # Volume slider at the bottom
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_slider.setFixedHeight(20)
        controls_layout.addWidget(self.volume_slider)
        
        return controls_layout


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
        if hasattr(self, 'prev_button') and hasattr(self, 'play_button') and hasattr(self, 'next_button'):
            # Use the same icon_color logic as in load_cover
            dominant_color = None
            if hasattr(self, 'player') and self.player.current_track:
                image = self.cover_label.pixmap().toImage() if self.cover_label.pixmap() else None
                if image:
                    from plex_music_player.lib.color_utils import get_dominant_color, get_contrasting_text_color
                    dominant_color = get_dominant_color(image)
            if dominant_color:
                from plex_music_player.lib.color_utils import get_contrasting_text_color
                icon_color = "#ffffff" if get_contrasting_text_color(dominant_color).name() == "#ffffff" else "#000000"
            else:
                icon_color = "#ffffff"
            if self.player.is_playing():
                self.play_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/pause.svg"), icon_color))
            else:
                self.play_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/play.svg"), icon_color))
        else:
            if self.player.is_playing():
                self.play_button.setIcon(QIcon(resource_path("icons_svg/pause.svg")))
            else:
                self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))
        
        if not self.player.current_track:
            self.progress_slider.setEnabled(False)
            self.progress_slider.setMaximum(0)
            self.progress_slider.setValue(0)
            self.update_time_label(0, 0)
            self.track_info.setText("")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.cover_label.clear()
            self._reset_button_styles()
            return
            
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
        
        # Получаем URL обложки
        thumb = None
        if hasattr(self.player.current_track, 'parentThumb'):
            thumb = self.player.current_track.parentThumb
        elif hasattr(self.player.current_track, 'thumb'):
            thumb = self.player.current_track.thumb
        
        if not thumb:
            return
        
        thumb_url = self.player.plex.url(thumb, includeToken=True)
        pixmap = load_cover_image(self.player.plex, self.player.current_track)
        
        if pixmap:
            window_width = self.width()
            window_height = self.height()
            scaled_pixmap = pixmap.scaled(window_width, window_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(scaled_pixmap)
            
            # Extract dominant color from the cover
            image = scaled_pixmap.toImage()
            dominant_color = get_dominant_color(image, url=thumb_url)
            
            if dominant_color:
                # Get contrasting text color
                text_color = get_contrasting_text_color(dominant_color)
                text_color_str = f"rgb({text_color.red()}, {text_color.green()}, {text_color.blue()})"
                
                # Create slightly darker and lighter versions for hover and pressed states
                darker_color = adjust_color_brightness(dominant_color, 0.8)
                lighter_color = adjust_color_brightness(dominant_color, 1.2)
                
                darker_color_str = f"rgb({darker_color.red()}, {darker_color.green()}, {darker_color.blue()})"
                lighter_color_str = f"rgb({lighter_color.red()}, {lighter_color.green()}, {lighter_color.blue()})"
                
                # Update control buttons style
                control_buttons_style = f"""
                    QPushButton {{
                        background-color: {dominant_color.name()};
                        border: none;
                        border-radius: 20px;
                        font-size: 16px;
                        padding: 0px;
                        color: {text_color_str};
                    }}
                    QPushButton:hover {{
                        background-color: {lighter_color_str};
                    }}
                    QPushButton:disabled {{
                        background-color: #2d2d2d;
                        color: #666666;
                    }}
                """
                icon_color = "#ffffff" if get_contrasting_text_color(dominant_color).name() == "#ffffff" else "#000000"
                self.prev_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/previous.svg"), icon_color))
                self.play_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/play.svg" if not self.player.is_playing() else "icons_svg/pause.svg"), icon_color))
                self.next_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/next.svg"), icon_color))
                for btn in [self.prev_button, self.play_button, self.next_button]:
                    btn.setStyleSheet(control_buttons_style)
                # Update playlist buttons style
                playlist_buttons_style = f"""
                    QPushButton {{
                        background-color: {dominant_color.name()};
                        border: none;
                        border-radius: 12px;
                        font-size: 12px;
                        padding: 0px;
                        color: {text_color_str};
                    }}
                    QPushButton:hover {{
                        background-color: {lighter_color_str};
                    }}
                    QPushButton:disabled {{
                        background-color: #2d2d2d;
                        color: #666666;
                    }}
                    QPushButton:pressed {{
                        background-color: {darker_color_str};
                    }}
                """
                self.add_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/add_to_playlist.svg"), icon_color))
                self.shuffle_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/shuffle_playlist.svg"), icon_color))
                self.remove_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/remove_track.svg"), icon_color))
                self.clear_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/clear_playlist.svg"), icon_color))
                self.scroll_to_current_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/locate_track.svg"), icon_color))
                for btn in [self.add_button, self.shuffle_button, self.remove_button, self.clear_button, self.scroll_to_current_button]:
                    btn.setStyleSheet(playlist_buttons_style)
                
                # Update slider colors
                slider_style = f"""
                    QSlider::groove:horizontal {{
                        border: none;
                        height: 4px;
                        background-color: #2d2d2d;
                        border-radius: 2px;
                    }}
                    QSlider::handle:horizontal {{
                        background-color: {dominant_color.name()};
                        border: none;
                        width: 12px;
                        margin: -4px 0;
                        border-radius: 6px;
                    }}
                    QSlider::sub-page:horizontal {{
                        background-color: {dominant_color.name()};
                        border-radius: 2px;
                    }}
                """
                self.progress_slider.setStyleSheet(slider_style)
                self.volume_slider.setStyleSheet(slider_style)
                
                # Update selected item color in playlist
                # Выбираем более светлый фон если текст черный
                playlist_bg_color = "#404040" if text_color.name() == "#ffffff" else "#b0b0b0"
                hover_bg_color = "#505050" if text_color.name() == "#ffffff" else "#a0a0a0"
                
                self.playlist_list.setStyleSheet(f"""
                    QListWidget {{
                        background-color: {playlist_bg_color};
                        border: none;
                        border-radius: 3px;
                        padding: 3px;
                        color: {text_color_str};
                    }}
                    QListWidget::item {{
                        padding: 3px;
                        border-radius: 2px;
                        color: {text_color_str};
                    }}
                    QListWidget::item:selected {{
                        background-color: {dominant_color.name()};
                        color: {text_color_str};
                    }}
                    QListWidget::item:hover {{
                        background-color: {hover_bg_color};
                        color: {text_color_str};
                    }}
                """)
                # Update title bar button colors
                if hasattr(self, 'title_bar'):
                    self.title_bar.set_button_color(dominant_color.name(), text_color_str)
                    self.title_bar.update_icons()
        else:
            self.cover_label.clear()
            # Reset to default styles if no cover
            self._reset_button_styles()

    def toggle_play(self) -> None:
        """Toggle play/pause state. If no track is loaded but a playlist exists,
        start playing the first track and update the UI (including loading the cover)."""
        logger.debug("=== Starting toggle_play in MainWindow ===")
        logger.debug(f"Current state: {self.player._player.playbackState() if self.player._player else 'No player'}")
        logger.debug(f"Current track: {self.player.current_track.title if self.player.current_track else 'None'}")
        logger.debug(f"Current index: {self.player.current_playlist_index}")
        
        if not self.player.current_track and self.player.playlist:
            logger.debug("No current track but playlist exists")
            # If no current track but playlist exists, use saved index or start with the first track
            if self.player.current_playlist_index >= 0 and self.player.current_playlist_index < len(self.player.playlist):
                logger.debug(f"Using saved index: {self.player.current_playlist_index}")
                self.player.current_track = self.player.playlist[self.player.current_playlist_index]
            else:
                logger.debug("Using first track")
                self.player.current_playlist_index = 0
                self.player.current_track = self.player.playlist[0]
            
            # Stop any existing playback first
            if self.player._player:
                logger.debug("Stopping existing playback")
                self.player._player.stop()
                time.sleep(0.1)  # Small delay to ensure stop completes
            
            logger.debug("Starting new playback")
            if not self.player._play_track_impl():
                logger.error("Failed to start playback")
                return
        else:
            # If track is already loaded, just toggle play/pause
            logger.debug("Toggling existing playback")
            logger.debug("Emitting toggle_play signal")
            result = self.player.toggle_play()
            logger.debug(f"Toggle play result: {result}")
        
        logger.debug("Updating playback UI")
        self.update_playback_ui()
        logger.debug("=== Finished toggle_play in MainWindow ===")


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
                logger.info("Track ended, playing next track...")
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
            logger.error(f"Error updating selection: {e}")

    def clear_playlist(self) -> None:
        """Clear the playlist and safely pause playback if necessary."""
        # Stop playback and clear player
        if self.player._player:
            self.player._player.stop()
            self.player._player = None
        self.player.current_track = None
        self.player.current_playlist_index = -1

        self.player.clear_playlist()
        self.playlist_list.clear()
        self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))
        self.play_button.setEnabled(False)
        self.progress_slider.setEnabled(False)
        self.progress_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.track_info.setText("No track")
        self.cover_label.clear()
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self._reset_button_styles()
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
            self.update_play_button(False)
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
            logger.debug("Starting play_from_playlist")
            index = self.playlist_list.row(item)
            logger.debug(f"Selected index: {index}")
            
            if 0 <= index < len(self.player.playlist):
                logger.debug(f"Index valid, current playlist length: {len(self.player.playlist)}")
                logger.debug(f"Current player state: {self.player._player.playbackState() if self.player._player else 'No player'}")
                
                # Save current index
                old_index = self.player.current_playlist_index
                
                # Set new index
                self.player.current_playlist_index = index
                self.player.current_track = self.player.playlist[index]
                logger.debug(f"New track set: {self.player.current_track.title if self.player.current_track else 'None'}")
                
                if not self.player._recreate_player():
                    logger.error("Failed to recreate player")
                    return
                
                # Start playback
                logger.debug("Attempting to play track")
                if self.player._play_track_impl():
                    logger.debug("Track started successfully")
                    self.update_playback_ui()
                    self.play_button.setEnabled(True)
                    self.prev_button.setEnabled(True)
                    self.next_button.setEnabled(True)
                else:
                    logger.error("Failed to start track playback")
        except Exception as e:
            logger.error(f"Error in play_from_playlist: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")

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
        if is_playing:
            self.play_button.setIcon(QIcon(resource_path("icons_svg/pause.svg")))
        else:
            self.play_button.setIcon(QIcon(resource_path("icons_svg/play.svg")))
        self.progress_slider.setEnabled(is_playing)

    def add_to_playlist(self, track) -> None:
        """Add a track to the playlist"""
        self.player.add_to_playlist(track)
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
        """Add multiple tracks to the playlist at once"""
        # Check if this is the first batch of tracks
        is_first_batch = len(self.player.playlist) == 0
        
        # Add tracks to the playlist
        self.player.add_tracks_batch(tracks)
        
        # Update UI
        items = []
        for track in tracks:
            year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
            items.append(f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]")
        self.playlist_list.addItems(items)
        
        # If this is the first batch, set up playback
        if is_first_batch and tracks:
            self.player.current_playlist_index = 0
            self.player.current_track = tracks[0]
            self.update_playback_ui()
            self.play_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            if self.player._play_track_impl():
                self.update_playback_ui()
        
        self.player.save_playlist()

    def closeEvent(self, event) -> None:
        self.player.save_playlist()
        self.player.close()
        super().closeEvent(event)

    def update_play_button(self, is_playing: bool) -> None:
        """Update the play/pause button based on playback state."""
        # Use the same icon_color logic as in load_cover
        dominant_color = None
        if hasattr(self, 'player') and self.player.current_track:
            image = self.cover_label.pixmap().toImage() if self.cover_label.pixmap() else None
            if image:
                from plex_music_player.lib.color_utils import get_dominant_color, get_contrasting_text_color
                dominant_color = get_dominant_color(image)
        if dominant_color:
            from plex_music_player.lib.color_utils import get_contrasting_text_color
            icon_color = "#ffffff" if get_contrasting_text_color(dominant_color).name() == "#ffffff" else "#000000"
        else:
            icon_color = "#ffffff"
        if is_playing:
            self.play_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/pause.svg"), icon_color))
        else:
            self.play_button.setIcon(self._get_icon_with_color(resource_path("icons_svg/play.svg"), icon_color))
        self.play_button.setEnabled(True)

    def change_volume(self, value: int) -> None:
        """Change the player's volume."""
        self.player._audio_output.setVolume(value / 100.0)
    
    def get_button_style(self) -> str:
        """Return the style for playlist control buttons."""
        return """
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """

    @pyqtSlot(list)
    def on_tracks_batch_loaded(self, tracks):
        """Handle batch of tracks loaded"""
        # Update playlist UI
        self.update_playlist_ui(tracks)
        
        # Check if this is the first batch of tracks
        if len(self.player.playlist) == len(tracks) and tracks:
            # This is the first batch, set up playback
            self.player.current_playlist_index = 0
            self.player.current_track = tracks[0]
            self.update_playback_ui()
            self.play_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            if self.player._play_track_impl():
                self.update_playback_ui()

    def update_playlist_ui(self, tracks):
        """Update playlist UI with new tracks"""
        for track in tracks:
            year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
            item_text = f"{track.title}{year} - {track.grandparentTitle} [{track.parentTitle}]"
            self.playlist_list.addItem(item_text)
        
        logger.debug(f"New playlist list count: {self.playlist_list.count()}")
        
        # Enable controls if this is the first track
        if len(self.player.playlist) == len(tracks):
            self.play_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
        
        # Force update of the list widget
        self.playlist_list.update()

    def scroll_to_current_track(self) -> None:
        """Scroll to the current track in the playlist."""
        try:
            if self.player.current_track and self.player.current_playlist_index >= 0:
                current_item = self.playlist_list.item(self.player.current_playlist_index)
                if current_item:
                    self.playlist_list.scrollToItem(current_item)
        except Exception as e:
            logger.error(f"Error scrolling to current track: {e}")

    def _reset_button_styles(self) -> None:
        """Reset button styles to default."""
        self.play_button.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                padding: 0px;
                color: white;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        self.prev_button.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                padding: 0px;
                color: white;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        self.next_button.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                padding: 0px;
                color: white;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """)
        self.remove_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """)
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """)
        self.scroll_to_current_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background-color: #2d2d2d;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background-color: #444444;
                border: none;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background-color: #444444;
                border-radius: 2px;
            }
        """)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background-color: #2d2d2d;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background-color: #444444;
                border: none;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background-color: #444444;
                border-radius: 2px;
            }
        """)
        self.playlist_list.setStyleSheet("""
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
        """)
        self.shuffle_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                border-radius: 12px;
                color: white;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666666;
            }
        """)

    def _on_lastfm_status_changed(self, enabled: bool) -> None:
        """Update Last.fm status indicator."""
        if enabled:
            self.lastfm_status.setStyleSheet("""
                QLabel {
                    color: #1DB954;
                    font-size: 16px;
                    padding: 0 5px;
                }
            """)
        else:
            self.lastfm_status.setStyleSheet("""
                QLabel {
                    color: #666666;
                    font-size: 16px;
                    padding: 0 5px;
                }
            """)

    def show_lastfm_settings(self) -> None:
        """Show Last.fm settings dialog."""
        dialog = LastFMSettingsDialog(self.player, self)
        dialog.exec()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._mouse_pos = event.globalPosition().toPoint()
                self._start_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_edge:
            delta = event.globalPosition().toPoint() - self._mouse_pos
            geom = self._start_geom
            new_geom = geom
            if "left" in self._resize_edge:
                new_geom.setLeft(geom.left() + delta.x())
            if "right" in self._resize_edge:
                new_geom.setRight(geom.right() + delta.x())
            if "top" in self._resize_edge:
                new_geom.setTop(geom.top() + delta.y())
            if "bottom" in self._resize_edge:
                new_geom.setBottom(geom.bottom() + delta.y())
            self.setGeometry(new_geom)
            event.accept()
            return
        edge = self._get_resize_edge(event.pos())
        if edge:
            self._set_cursor_for_edge(edge)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_edge = None
        self._mouse_pos = None
        self._start_geom = None
        super().mouseReleaseEvent(event)

    def _get_resize_edge(self, pos):
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        margin = self.RESIZE_MARGIN
        edges = []
        if x < margin:
            edges.append("left")
        elif x > w - margin:
            edges.append("right")
        if y < margin:
            edges.append("top")
        elif y > h - margin:
            edges.append("bottom")
        return "-".join(edges) if edges else None

    def _set_cursor_for_edge(self, edge):
        cursors = {
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "left-top": Qt.CursorShape.SizeFDiagCursor,
            "right-bottom": Qt.CursorShape.SizeFDiagCursor,
            "right-top": Qt.CursorShape.SizeBDiagCursor,
            "left-bottom": Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))

    def _get_icon_with_color(self, icon_path, color):
        try:
            with open(icon_path, "r", encoding="utf-8") as f:
                svg_data = f.read()
            svg_data = re.sub(r'fill=["\\\']#000000["\\\']', f'fill="{color}"', svg_data)
            return QIcon(QIcon.fromTheme("", QIcon(QPixmap.fromImage(QImage.fromData(bytes(svg_data, "utf-8"))))))
        except Exception:
            return QIcon(icon_path)

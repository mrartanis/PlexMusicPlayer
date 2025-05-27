import sys
import re
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QMenu
from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtGui import QCursor, QAction, QIcon, QPixmap, QImage
from plex_music_player.lib.utils import resource_path, read_resource_file, create_icon
from plex_music_player.lib.color_utils import get_contrasting_text_color

class CustomTitleBar(QWidget):
    def __init__(self, parent=None, color="#1e1e1e", button_color="#ffffff"):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(28)
        self.setStyleSheet(f"background-color: {color};")
        self._mouse_pos = None
        self._init_ui(button_color)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _init_ui(self, button_color):
        is_mac = sys.platform == "darwin"
        layout = QHBoxLayout(self)
        if is_mac:
            layout.setContentsMargins(4, 0, 0, 0)
        else:
            layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(0)

        self.buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(self.buttons_widget)
        if is_mac:
            buttons_layout.setContentsMargins(4, 0, 0, 0)
        else:
            buttons_layout.setContentsMargins(0, 0, 4, 0)
        buttons_layout.setSpacing(6)

        btn_size = 16
        circle_size = 12
        self.close_button = QPushButton("")
        self.min_button = QPushButton("")
        self.max_button = QPushButton("")
        for btn in [self.close_button, self.min_button, self.max_button]:
            btn.setFixedSize(circle_size, circle_size)
            btn.setStyleSheet(f"background-color: {button_color}; border: none; border-radius: 6px; color: transparent; font-size: 10px;")
        self.close_button.clicked.connect(self._on_close)
        self.min_button.clicked.connect(self._on_minimize)
        self.max_button.clicked.connect(self._on_maximize)
        if is_mac:
            buttons_layout.addWidget(self.close_button)
            buttons_layout.addWidget(self.min_button)
            buttons_layout.addWidget(self.max_button)
        else:
            buttons_layout.addWidget(self.min_button)
            buttons_layout.addWidget(self.max_button)
            buttons_layout.addWidget(self.close_button)

        # SVG icons
        self._icon_paths = {
            "close": resource_path("icons_svg/window-close.svg"),
            "min": resource_path("icons_svg/window-minimize.svg"),
            "max": resource_path("icons_svg/window-maximize.svg"),
        }
        self._icon_size = QSize(8, 8)

        self.menu_button = QPushButton("\u2630")
        self.menu_button.setFixedSize(btn_size, btn_size)
        self.menu_button.setStyleSheet(f"background-color: transparent; border: none; border-radius: 0px; color: #ffffff; font-size: 20px;")
        self.menu = QMenu(self)
        plex_action = QAction("Plex configuration", self)
        plex_action.triggered.connect(self._show_plex_config)
        self.menu.addAction(plex_action)
        lastfm_action = QAction("Last.fm settings", self)
        lastfm_action.triggered.connect(self._show_lastfm_settings)
        self.menu.addAction(lastfm_action)
        self.menu_button.clicked.connect(self._show_menu)

        if is_mac:
            layout.addWidget(self.buttons_widget, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignRight)
        else:
            layout.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.buttons_widget, 0, Qt.AlignmentFlag.AlignRight)

    def set_button_color(self, bg_color, icon_color):
        circle_size = 12
        for btn in [self.close_button, self.min_button, self.max_button]:
            btn.setStyleSheet(f"background-color: {bg_color}; border: none; border-radius: 6px; color: transparent; font-size: 10px;")
            btn._icon_color = icon_color
        self.menu_button.setStyleSheet(f"background-color: transparent; border: none; border-radius: 0px; color: #ffffff; font-size: 20px;")

    def _show_menu(self):
        self.menu.exec(QCursor.pos())

    def _on_close(self):
        if self.parent:
            self.parent.close()

    def _on_minimize(self):
        if self.parent:
            self.parent.showMinimized()

    def _on_maximize(self):
        if self.parent:
            if sys.platform == "darwin":
                if self.parent.isFullScreen():
                    self.parent.showNormal()
                else:
                    self.parent.showFullScreen()
            else:
                if self.parent.isMaximized():
                    self.parent.showNormal()
                else:
                    self.parent.showMaximized()

    def _show_plex_config(self):
        if self.parent and hasattr(self.parent, 'show_connection_dialog'):
            self.parent.show_connection_dialog()

    def _show_lastfm_settings(self):
        if self.parent and hasattr(self.parent, 'show_lastfm_settings'):
            self.parent.show_lastfm_settings()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pos = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._mouse_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.parent.move(event.globalPosition().toPoint() - self._mouse_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._mouse_pos = None

    def _set_icons_with_current_color(self):
        bg_color = self.close_button.palette().button().color()
        icon_color = "#ffffff" if get_contrasting_text_color(bg_color).name() == "#ffffff" else "#000000"
        for btn, key in zip([self.close_button, self.min_button, self.max_button], ["close", "min", "max"]):
            icon_path = self._icon_paths[key].replace(resource_path(""), "")
            btn.setIcon(create_icon(icon_path, icon_color))
            btn.setIconSize(self._icon_size)
            color = getattr(btn, '_icon_color', '#ffffff')
            btn.setStyleSheet(btn.styleSheet().replace("color: transparent", f"color: {color}"))

    def enterEvent(self, event):
        self._set_icons_with_current_color()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Hide SVG icons in circles when mouse leaves the panel
        self.close_button.setIcon(QIcon())
        self.min_button.setIcon(QIcon())
        self.max_button.setIcon(QIcon())
        self.close_button.setText("")
        self.min_button.setText("")
        self.max_button.setText("")
        for btn in [self.close_button, self.min_button, self.max_button]:
            color = getattr(btn, '_icon_color', '#ffffff')
            btn.setStyleSheet(btn.styleSheet().replace(f"color: {color}", "color: transparent"))
        super().leaveEvent(event)

    def _get_icon_with_color(self, icon_path, color):
        # Read SVG and replace fill color
        try:
            path = icon_path.replace(resource_path(""), "")
            return create_icon(path, color)
        except Exception:
            return QIcon(icon_path)

    def update_icons(self):
        self._set_icons_with_current_color() 

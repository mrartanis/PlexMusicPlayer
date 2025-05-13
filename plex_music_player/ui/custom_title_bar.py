import sys
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QMenu
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QCursor, QAction

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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        is_mac = sys.platform == "darwin"
        self.buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(self.buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)

        btn_size = 16
        self.close_button = QPushButton("")
        self.min_button = QPushButton("")
        self.max_button = QPushButton("")
        if is_mac:
            for btn in [self.close_button, self.min_button, self.max_button]:
                btn.setFixedSize(btn_size, btn_size)
                btn.setStyleSheet(f"background-color: transparent; border: none; color: {button_color}; font-size: 12px;")
            self.close_button.clicked.connect(self._on_close)
            self.min_button.clicked.connect(self._on_minimize)
            self.max_button.clicked.connect(self._on_maximize)
            buttons_layout.addWidget(self.close_button)
            buttons_layout.addWidget(self.min_button)
            buttons_layout.addWidget(self.max_button)
        else:
            for btn in [self.min_button, self.max_button, self.close_button]:
                btn.setFixedSize(btn_size, btn_size)
                btn.setStyleSheet(f"background-color: transparent; border: none; color: {button_color}; font-size: 12px;")
            self.close_button.clicked.connect(self._on_close)
            self.min_button.clicked.connect(self._on_minimize)
            self.max_button.clicked.connect(self._on_maximize)
            buttons_layout.addWidget(self.min_button)
            buttons_layout.addWidget(self.max_button)
            buttons_layout.addWidget(self.close_button)

        self.menu_button = QPushButton("")
        self.menu_button.setFixedSize(btn_size, btn_size)
        self.menu_button.setStyleSheet(f"background-color: transparent; border: none; border-radius: 0px; color: {button_color}; font-size: 20px;")
        self.menu = QMenu(self)
        fake_action = QAction("Fake menu item", self)
        self.menu.addAction(fake_action)
        self.menu_button.clicked.connect(self._show_menu)

        if is_mac:
            layout.addWidget(self.buttons_widget, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignRight)
        else:
            layout.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.buttons_widget, 0, Qt.AlignmentFlag.AlignRight)

    def set_button_color(self, color):
        btn_size = 16
        for btn in [self.close_button, self.min_button, self.max_button]:
            btn.setStyleSheet(f"background-color: transparent; border: none; border-radius: 8px; color: #ffffff; font-size: 12px;")
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

    def enterEvent(self, event):
        # Show icons when hovering over the panel
        self.close_button.setText("\u2716")
        self.min_button.setText("\u2212")
        self.max_button.setText("\u25A1")
        self.menu_button.setText("\u2630")
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Hide icons when mouse leaves the panel
        self.close_button.setText("")
        self.min_button.setText("")
        self.max_button.setText("")
        self.menu_button.setText("")
        super().leaveEvent(event) 
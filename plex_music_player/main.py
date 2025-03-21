import sys
import signal
from PyQt6.QtWidgets import QApplication
from .ui.main_window import MainWindow

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 
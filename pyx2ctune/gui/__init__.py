"""pyx2ctune GUI -- PyQt5 application for current loop tuning."""

import sys

from PyQt5.QtWidgets import QApplication

from pyx2ctune.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("pyx2ctune")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())

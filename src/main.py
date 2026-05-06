"""Entry point for AchachaMaker."""

import sys

from PyQt6.QtWidgets import QApplication

from src.app import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette for a modern look
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtCore import Qt

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E2E"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#181825"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1E1E2E"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#F38BA8"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#89B4FA"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#89B4FA"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1E1E2E"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

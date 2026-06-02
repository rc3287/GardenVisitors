DARK = """
QMainWindow, QWidget {
    background-color: #1E1E2E;
    color: #CDD6F4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QScrollArea { border: none; background-color: #1E1E2E; }
QScrollBar:vertical {
    background: #313244; width: 8px; border-radius: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #585B70; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #94E2D5; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QPushButton {
    background-color: #94E2D5; color: #1E1E2E;
    border: none; border-radius: 8px;
    padding: 8px 24px; font-weight: bold;
}
QPushButton:hover { background-color: #89DCEB; }
QPushButton:pressed { background-color: #74C7EC; }
QPushButton:disabled { background-color: #45475A; color: #6C7086; }

QPushButton#secondary {
    background-color: #313244; color: #CDD6F4;
}
QPushButton#secondary:hover { background-color: #45475A; }

QRadioButton { color: #CDD6F4; spacing: 8px; padding: 3px 0; }
QRadioButton::indicator {
    width: 16px; height: 16px; border-radius: 8px;
    border: 2px solid #585B70; background-color: #313244;
}
QRadioButton::indicator:checked { background-color: #94E2D5; border-color: #94E2D5; }
QRadioButton::indicator:hover { border-color: #94E2D5; }

QGroupBox {
    border: 1px solid #45475A; border-radius: 10px;
    margin-top: 14px; padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #94E2D5; font-size: 11px; font-weight: bold;
}

QLabel { color: #CDD6F4; }
QLabel#dim { color: #A6ADC8; font-size: 11px; }
QLabel#accent { color: #94E2D5; font-size: 11px; font-style: italic; }

QSplitter::handle:horizontal { background-color: #313244; width: 3px; }

QMenuBar {
    background-color: #181825; color: #CDD6F4;
    border-bottom: 1px solid #313244; padding: 2px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background-color: #313244; }
QMenu {
    background-color: #313244; color: #CDD6F4;
    border: 1px solid #45475A; border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::item:selected { background-color: #45475A; }
QMenu::separator { height: 1px; background: #45475A; margin: 4px 8px; }

QStatusBar { background-color: #181825; color: #A6ADC8; font-size: 11px; }

QFrame#ThumbnailCard {
    background-color: #2A2A3E;
    border: 2px solid transparent;
    border-radius: 10px;
}
QFrame#ThumbnailCard:hover {
    border: 2px solid #585B70;
}
QFrame#ThumbnailCard[selected="true"] {
    background-color: #313244;
    border: 2px solid #94E2D5;
}
"""

LIGHT = """
QMainWindow, QWidget {
    background-color: #F0F2F5;
    color: #2C2C3E;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QScrollArea { border: none; background-color: #F0F2F5; }
QScrollBar:vertical {
    background: #E0E0E0; width: 8px; border-radius: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #BDBDBD; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #00897B; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QPushButton {
    background-color: #00897B; color: #FFFFFF;
    border: none; border-radius: 8px;
    padding: 8px 24px; font-weight: bold;
}
QPushButton:hover { background-color: #00796B; }
QPushButton:pressed { background-color: #00695C; }
QPushButton:disabled { background-color: #E0E0E0; color: #9E9E9E; }

QPushButton#secondary {
    background-color: #E0E0E0; color: #2C2C3E;
}
QPushButton#secondary:hover { background-color: #BDBDBD; }

QRadioButton { color: #2C2C3E; spacing: 8px; padding: 3px 0; }
QRadioButton::indicator {
    width: 16px; height: 16px; border-radius: 8px;
    border: 2px solid #BDBDBD; background-color: #FFFFFF;
}
QRadioButton::indicator:checked { background-color: #00897B; border-color: #00897B; }
QRadioButton::indicator:hover { border-color: #00897B; }

QGroupBox {
    border: 1px solid #E0E0E0; border-radius: 10px;
    margin-top: 14px; padding: 10px 8px 8px 8px;
    background-color: #FFFFFF;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #00897B; font-size: 11px; font-weight: bold;
}

QLabel { color: #2C2C3E; }
QLabel#dim { color: #757575; font-size: 11px; }
QLabel#accent { color: #00897B; font-size: 11px; font-style: italic; }

QSplitter::handle:horizontal { background-color: #E0E0E0; width: 3px; }

QMenuBar {
    background-color: #FFFFFF; color: #2C2C3E;
    border-bottom: 1px solid #E0E0E0; padding: 2px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background-color: #F5F5F5; }
QMenu {
    background-color: #FFFFFF; color: #2C2C3E;
    border: 1px solid #E0E0E0; border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::item:selected { background-color: #F5F5F5; }
QMenu::separator { height: 1px; background: #E0E0E0; margin: 4px 8px; }

QStatusBar { background-color: #FFFFFF; color: #757575; font-size: 11px; }

QFrame#ThumbnailCard {
    background-color: #FFFFFF;
    border: 2px solid transparent;
    border-radius: 10px;
}
QFrame#ThumbnailCard:hover {
    border: 2px solid #BDBDBD;
}
QFrame#ThumbnailCard[selected="true"] {
    background-color: #E0F2F1;
    border: 2px solid #00897B;
}
"""

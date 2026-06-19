#!/usr/bin/env python3
"""Tokyo Night Storm theme for tapitoCAM."""

_BG = "#24283b"
_BG_DARK = "#1f2335"
_SURFACE = "#2f3346"
_SURFACE_HOVER = "#363b54"
_BORDER = "#3b4261"
_BLUE = "#7aa2f7"
_BLUE_HOVER = "#89b4fa"
_GREEN = "#9ece6a"
_ORANGE = "#ff9e64"
_RED = "#f7768e"
_TEXT = "#c0caf5"
_SUBTEXT = "#a9b1d6"
_DISABLED = "#565f89"

DARK_THEME = f"""
QMainWindow, QWidget#central_widget {{
    background: {_BG};
    color: {_TEXT};
}}
QPushButton {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    background: {_SURFACE};
    color: {_TEXT};
    font-weight: 500;
}}
QPushButton:hover {{
    background: {_SURFACE_HOVER};
    border-color: {_BLUE};
}}
QPushButton:pressed {{
    background: {_BLUE};
    color: {_BG};
}}
QPushButton:disabled {{
    background: {_BG_DARK};
    color: {_DISABLED};
    border-color: {_SURFACE};
}}
QPushButton:checked {{
    background: {_SURFACE_HOVER};
    border-color: {_BLUE};
    color: {_BLUE};
}}
QPushButton#stream_btn {{
    background: {_BLUE};
    border-color: {_BLUE};
    color: {_BG_DARK};
    font-weight: 600;
}}
QPushButton#stream_btn:hover {{
    background: {_BLUE_HOVER};
}}
QPushButton#stream_btn:pressed {{
    background: {_BLUE_HOVER};
}}
QPushButton#stream_btn:disabled {{
    background: {_BG_DARK};
    color: {_DISABLED};
    border-color: {_SURFACE};
}}
QComboBox {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    background: {_SURFACE};
    color: {_TEXT};
}}
QComboBox:focus {{
    border-color: {_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {_DISABLED};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {_SURFACE};
    color: {_TEXT};
    selection-background-color: {_SURFACE_HOVER};
    border: 1px solid {_BORDER};
    outline: none;
}}
QLabel {{
    color: {_TEXT};
}}
QLabel#secondary {{
    color: {_SUBTEXT};
}}
QLabel[streaming="true"] {{
    color: {_GREEN};
    padding: 2px 0;
    font-weight: bold;
}}
QLabel[streaming="false"] {{
    color: {_SUBTEXT};
    padding: 2px 0;
}}
QStatusBar {{
    background: {_BG_DARK};
    color: {_DISABLED};
    border-top: 1px solid {_SURFACE};
    padding: 4px;
}}
QLineEdit {{
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    background: {_SURFACE};
    color: {_TEXT};
    selection-background-color: {_BLUE};
}}
QLineEdit:focus {{
    border-color: {_BLUE};
    background: {_SURFACE};
}}
QLineEdit::placeholder {{
    color: {_DISABLED};
}}
QListWidget {{
    background: {_BG_DARK};
    color: {_TEXT};
    border: 1px solid {_SURFACE};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background: {_SURFACE_HOVER};
    color: {_TEXT};
}}
QListWidget::item:hover:!selected {{
    background: {_SURFACE};
}}
QDialog {{
    background: {_BG};
    color: {_TEXT};
}}
"""

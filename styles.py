#!/usr/bin/env python3
"""Shared stylesheet constants for tapitoCAM."""

DARK_THEME = """
QMainWindow, QWidget#central_widget {
    background: #1e1e1e;
    color: #e0e0e0;
}
QPushButton {
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 8px 16px;
    background: #2d2d2d;
    color: #e0e0e0;
    font-weight: 500;
}
QPushButton:hover {
    background: #383838;
    border-color: #3b82f6;
}
QPushButton:pressed {
    background: #3b82f6;
    color: #ffffff;
}
QPushButton:disabled {
    background: #1a1a1a;
    color: #666666;
    border-color: #2a2a2a;
}
QPushButton:checked {
    background: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}
QComboBox {
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 8px 12px;
    background: #252525;
    color: #e0e0e0;
}
QComboBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #888888;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #252525;
    color: #e0e0e0;
    selection-background-color: #3b82f6;
    border: 1px solid #3a3a3a;
    outline: none;
}
QLabel {
    color: #e0e0e0;
}
QStatusBar {
    background: #1a1a1a;
    color: #888888;
    border-top: 1px solid #333333;
    padding: 4px;
}
QLineEdit {
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 8px 12px;
    background: #252525;
    color: #e0e0e0;
    selection-background-color: #3b82f6;
}
QLineEdit:focus {
    border-color: #3b82f6;
    background: #2a2a2a;
}
QLineEdit::placeholder {
    color: #777777;
}
QListWidget {
    background: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 8px 12px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background: #3b82f6;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background: #2a2a2a;
}
QDialog {
    background: #1e1e1e;
    color: #e0e0e0;
}
"""


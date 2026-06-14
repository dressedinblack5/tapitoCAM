#!/usr/bin/env python3
"""Camera manager dialog — add, edit, and remove cameras from the config."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cameraconfig import ConfigManager


# ===========================================================================
# Camera edit sub-dialog
# ===========================================================================

class _CameraEditDialog(QDialog):
    """Modal dialog for adding or editing a single camera."""

    def __init__(self, parent=None, camera: dict | None = None):
        super().__init__(parent)
        self._camera = camera or {}
        self._result: dict | None = None
        self._build_ui()
        self._apply_stylesheet()
        if camera:
            self._populate(camera)

    def _build_ui(self):
        title = "Edit Camera" if self._camera else "Add Camera"
        self.setWindowTitle(title)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Front Door")
        form.addRow("Name:", self._name_edit)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("Tapo Username")
        form.addRow("Username:", self._user_edit)

        self._pass_edit = QLineEdit()
        self._pass_edit.setPlaceholderText("Tapo Password")
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password:", self._pass_edit)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("e.g. 192.168.1.100")
        form.addRow("IP:", self._ip_edit)

        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["HD (stream1)", "SD (stream2)"])
        form.addRow("Quality:", self._quality_combo)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, camera: dict):
        self._name_edit.setText(camera.get("name", ""))
        self._user_edit.setText(camera.get("username", ""))
        self._pass_edit.setText(camera.get("password", ""))
        self._ip_edit.setText(camera.get("ip", ""))
        self._quality_combo.setCurrentIndex(
            0 if camera.get("quality", "hd") == "hd" else 1
        )

    def _on_accept(self):
        name = self._name_edit.text().strip()
        username = self._user_edit.text().strip()
        password = self._pass_edit.text()
        ip = self._ip_edit.text().strip()
        quality = "hd" if self._quality_combo.currentIndex() == 0 else "sd"

        # Validate
        errors = []
        if not username:
            errors.append("Username is required.")
        if not password:
            errors.append("Password is required.")
        if not ip:
            errors.append("IP address is required.")
        elif not ConfigManager.validate_ip(ip):
            errors.append("Invalid IP address format.")

        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return

        self._result = {
            "name": name or None,  # ConfigManager will default to "Camera N"
            "username": username,
            "password": password,
            "ip": ip,
            "quality": quality,
        }
        self.accept()

    @property
    def result_data(self) -> dict | None:
        return self._result

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QDialog {
                background: #1e1e1e;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
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
            }
            QPushButton {
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 8px 16px;
                background: #2d2d2d;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: #383838;
                border-color: #3b82f6;
            }
            QPushButton:pressed {
                background: #3b82f6;
                color: #ffffff;
            }
        """)


# ===========================================================================
# Camera Manager Dialog  (main)
# ===========================================================================

class CameraManagerDialog(QDialog):
    """Main dialog for managing the camera list.

    On accept, saves all changes to the config file and returns the updated
    camera list via :attr:`cameras`.
    """

    def __init__(self, parent=None, config_manager: ConfigManager | None = None):
        super().__init__(parent)
        self._cfg = config_manager or ConfigManager()
        self._cameras: list[dict] = []
        self._build_ui()
        self._apply_stylesheet()
        self._refresh_list()

    def _build_ui(self):
        self.setWindowTitle("Camera Manager")
        self.setMinimumSize(480, 360)
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # List
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(2)
        layout.addWidget(self._list, stretch=1)

        # Action buttons
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._edit_btn = QPushButton("✏ Edit")
        self._remove_btn = QPushButton("✕ Remove")

        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn.clicked.connect(self._on_edit)
        self._remove_btn.clicked.connect(self._on_remove)

        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Dialog buttons
        self._ok_btn = QPushButton("OK")
        self._cancel_btn = QPushButton("Cancel")
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(self._ok_btn)
        bottom_row.addWidget(self._cancel_btn)
        layout.addLayout(bottom_row)

        # Selection tracking
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._on_selection_changed()

    def _refresh_list(self):
        self._cameras = self._cfg.load()
        self._list.clear()
        for cam in self._cameras:
            name = cam.get("name", f"Camera {cam.get('id', '?')}")
            ip = cam.get("ip", "?.?.?.?")
            item = QListWidgetItem(f"{name}  —  {ip}")
            item.setData(Qt.ItemDataRole.UserRole, cam.get("id"))
            self._list.addItem(item)
        self._on_selection_changed()

    def _on_selection_changed(self):
        has_selection = self._list.currentItem() is not None
        self._edit_btn.setEnabled(has_selection)
        self._remove_btn.setEnabled(has_selection)

    def _on_add(self):
        dialog = _CameraEditDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            data = dialog.result_data
            try:
                self._cfg.add_camera(data)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self._refresh_list()

    def _on_edit(self):
        item = self._list.currentItem()
        if not item:
            return
        cam_id = item.data(Qt.ItemDataRole.UserRole)
        camera = self._cfg.get_camera(cam_id)
        if not camera:
            return
        dialog = _CameraEditDialog(self, camera)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            try:
                self._cfg.update_camera(cam_id, dialog.result_data)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self._refresh_list()

    def _on_remove(self):
        item = self._list.currentItem()
        if not item:
            return
        cam_id = item.data(Qt.ItemDataRole.UserRole)
        camera = self._cfg.get_camera(cam_id)
        name = camera.get("name", f"Camera {cam_id}") if camera else f"Camera {cam_id}"
        reply = QMessageBox.question(
            self, "Remove Camera",
            f"Remove \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cfg.remove_camera(cam_id)
            self._refresh_list()

    def _on_ok(self):
        self.accept()

    @property
    def cameras(self) -> list[dict]:
        return self._cameras

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QDialog {
                background: #1e1e1e;
                color: #e0e0e0;
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
            QPushButton {
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 8px 16px;
                background: #2d2d2d;
                color: #e0e0e0;
                min-width: 80px;
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
            QLabel {
                color: #e0e0e0;
            }
        """)

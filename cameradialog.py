#!/usr/bin/env python3
"""Camera manager dialog — add, edit, and remove cameras from the config."""

import concurrent.futures
import socket
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cameraconfig import ConfigManager
from styles import DARK_THEME


# ===========================================================================
# Camera edit sub-dialog
# ===========================================================================


class _CameraEditDialog(QDialog):
    """Modal dialog for adding or editing a single camera."""

    def __init__(self, parent=None, camera: dict | None = None, ip: str | None = None):
        super().__init__(parent)
        self._camera = camera or {}
        self._result: dict | None = None
        self._build_ui()
        self._apply_stylesheet()
        if camera:
            self._populate(camera)
        if ip:
            self._ip_edit.setText(ip)

    def _build_ui(self):
        title = "Edit Camera" if self._camera else "Add Camera"
        self.setWindowTitle(title)
        self.setFixedSize(380, 320)

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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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
            "name": name or None,
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
        self.setStyleSheet(DARK_THEME)


# ===========================================================================
# Network scan dialog
# ===========================================================================


class _NetworkScanDialog(QDialog):

    _device_found = Signal(str)
    _progress_update = Signal(int)
    _scan_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_ip: str | None = None
        self._build_ui()
        self._apply_stylesheet()
        self._device_found.connect(self._add_result)
        self._progress_update.connect(self._update_progress)
        self._scan_finished.connect(self._on_scan_finished)
        self._start_scan()

    def _build_ui(self):
        self.setWindowTitle("Scan Network")
        self.setFixedSize(400, 350)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._progress_label = QLabel("Detecting network...")
        layout.addWidget(self._progress_label)

        self._list = QListWidget()
        layout.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)

    def _get_local_subnet(self) -> str | None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.split(".")
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
        except Exception:
            return None

    def _start_scan(self):
        subnet = self._get_local_subnet()
        if not subnet:
            self._progress_label.setText("Could not detect local network.")
            return

        self._progress_label.setText(f"Scanning {subnet}.0/24... (0/254)")

        def scan():
            def probe(i):
                ip = f"{subnet}.{i}"
                try:
                    with socket.create_connection((ip, 554), timeout=0.3):
                        self._device_found.emit(ip)
                except Exception:
                    pass
                return ip

            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as pool:
                futures = [pool.submit(probe, i) for i in range(1, 255)]
                done = 0
                for f in concurrent.futures.as_completed(futures):
                    done += 1
                    if done % 10 == 0 or done == 254:
                        self._progress_update.emit(done)

            self._scan_finished.emit()

        threading.Thread(target=scan, daemon=True).start()

    def _add_result(self, ip: str):
        item = QListWidgetItem(ip)
        item.setData(Qt.ItemDataRole.UserRole, ip)
        self._list.addItem(item)

    def _update_progress(self, done: int):
        subnet = self._get_local_subnet()
        self._progress_label.setText(f"Scanning {subnet}.0/24... ({done}/254)")

    def _on_scan_finished(self):
        count = self._list.count()
        if count > 0:
            self._progress_label.setText(f"Found {count} device(s) on port 554.")
            self._ok_button.setEnabled(True)
        else:
            self._progress_label.setText("No cameras found on the network.")

    def _on_accept(self):
        item = self._list.currentItem()
        if item:
            self._selected_ip = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    @property
    def selected_ip(self) -> str | None:
        return self._selected_ip

    def _apply_stylesheet(self):
        self.setStyleSheet(DARK_THEME)


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
        self.setFixedSize(520, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(2)
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._scan_btn = QPushButton("Scan Network")
        self._edit_btn = QPushButton("✏ Edit")
        self._remove_btn = QPushButton("✕ Remove")
        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedSize(38, 32)
        self._down_btn = QPushButton("↓")
        self._down_btn.setFixedSize(38, 32)

        self._add_btn.clicked.connect(self._on_add)
        self._scan_btn.clicked.connect(self._on_scan_network)
        self._edit_btn.clicked.connect(self._on_edit)
        self._remove_btn.clicked.connect(self._on_remove)
        self._up_btn.clicked.connect(self._on_move_up)
        self._down_btn.clicked.connect(self._on_move_down)

        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._up_btn)
        btn_row.addWidget(self._down_btn)
        layout.addLayout(btn_row)

        self._ok_btn = QPushButton("OK")
        self._cancel_btn = QPushButton("Cancel")
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self.reject)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(self._ok_btn)
        bottom_row.addWidget(self._cancel_btn)
        layout.addLayout(bottom_row)

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
        row = self._list.currentRow()
        count = self._list.count()
        self._edit_btn.setEnabled(has_selection)
        self._remove_btn.setEnabled(has_selection)
        self._up_btn.setEnabled(has_selection and row > 0)
        self._down_btn.setEnabled(has_selection and row < count - 1)

    def _on_add(self, prefill_ip: str | None = None):
        dialog = _CameraEditDialog(self, ip=prefill_ip)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            data = dialog.result_data
            try:
                self._cfg.add_camera(data)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self._refresh_list()

    def _on_scan_network(self):
        scan = _NetworkScanDialog(self)
        if scan.exec() == QDialog.DialogCode.Accepted and scan.selected_ip:
            self._on_add(prefill_ip=scan.selected_ip)

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
            self,
            "Remove Camera",
            f'Remove "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cfg.remove_camera(cam_id)
            self._refresh_list()

    def _on_move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._cfg.reorder_cameras(row, row - 1)
        self._refresh_list()
        self._list.setCurrentRow(row - 1)

    def _on_move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= self._list.count() - 1:
            return
        self._cfg.reorder_cameras(row, row + 1)
        self._refresh_list()
        self._list.setCurrentRow(row + 1)

    def _on_ok(self):
        self.accept()

    @property
    def cameras(self) -> list[dict]:
        return self._cameras

    def _apply_stylesheet(self):
        self.setStyleSheet(DARK_THEME)

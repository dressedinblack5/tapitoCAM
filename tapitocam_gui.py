#!/usr/bin/env python3

import locale
import os

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")

import base64
import re
import socket
import sys
import tempfile
import urllib.parse
from pathlib import Path

import mpv

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QInputDialog, QStatusBar, QVBoxLayout,
    QWidget,
)

def _validate_ip(ip):
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            return False
    return True


class _Worker(QObject):
    finished = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self):
        self.finished.emit(self.fn())


NETWORK_ERRORS = [
    "No route to host",
    "Connection timed out",
    "Connection refused",
    "Failed to resolve hostname",
]

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path.home() / ".config" / "tapitocam"
CONFIG_FILE = CONFIG_DIR / ".tapitocam.env"


class PTZWorker(QObject):
    connected = Signal(bool)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ptz = None
        self.profile_token = None

    @Slot(str, str, str)
    def connect(self, ip, user, password):
        try:
            from onvif import ONVIFCamera
            cam = ONVIFCamera(ip, 2020, user, password)
            self.ptz = cam.create_ptz_service()
            configs = self.ptz.GetConfigurations()
            if configs:
                self.profile_token = configs[0].token
            self.connected.emit(True)
        except Exception as e:
            self.cleanup()
            self.error.emit(str(e))
            self.connected.emit(False)

    @Slot(float, float)
    def continuous_move(self, pan, tilt):
        if not self.ptz:
            return
        try:
            request = self.ptz.create_type("ContinuousMove")
            request.ProfileToken = self.profile_token
            request.Velocity = {
                "PanTilt": {"x": float(pan), "y": float(tilt), "space": "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"},
                "Zoom": {"x": 0.0},
            }
            self.ptz.ContinuousMove(request)
        except Exception as e:
            self.error.emit(str(e))

    @Slot()
    def stop(self):
        if not self.ptz:
            return
        try:
            request = self.ptz.create_type("Stop")
            request.ProfileToken = self.profile_token
            self.ptz.Stop(request)
        except Exception as e:
            self.error.emit(str(e))

    @Slot(float, float)
    def absolute_move(self, pan, tilt):
        if not self.ptz:
            return
        try:
            request = self.ptz.create_type("AbsoluteMove")
            request.ProfileToken = self.profile_token
            request.Position = {
                "PanTilt": {"x": pan, "y": tilt},
                "Zoom": {"x": 0},
            }
            self.ptz.AbsoluteMove(request)
        except Exception as e:
            self.error.emit(str(e))

    def cleanup(self):
        self.ptz = None
        self.profile_token = None


class MainWindow(QMainWindow):
    stream_errored = Signal(str)
    stream_ended = Signal()

    def __init__(self):
        super().__init__()
        self.player = None
        self.error_log = None
        self.ptz_worker = None
        self.ptz_thread = None
        self._streaming = False
        self.stream_errored.connect(self._handle_network_error)
        self.stream_ended.connect(self._on_stream_ended)
        self._init_ui()
        self._load_config()
        self._check_camera_status()
        self._init_ptz()

    def _init_ui(self):
        self.setWindowTitle("tapitoCAM")
        self.setMinimumSize(300, 420)
        self.resize(300, 400)

        central = QWidget()
        central.setObjectName("central_widget")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        config_panel = QWidget()
        config_layout = QFormLayout(config_panel)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(6)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Tapo Username")
        config_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Tapo Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        config_layout.addRow("Password:", self.password_edit)

        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("e.g. 192.168.1.100")
        config_layout.addRow("IP:", self.ip_edit)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.reset_btn = QPushButton("Reset")
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        config_layout.addRow("", btn_row)

        layout.addWidget(config_panel)

        self.status_label = QLabel("● Checking...")
        self.status_label.setStyleSheet("color: #888888; padding: 4px 0;")
        layout.addWidget(self.status_label)

        stream_row = QHBoxLayout()
        stream_row.setSpacing(8)

        self.stream_btn = QPushButton("▶  Open Stream")
        self.stream_btn.setMinimumHeight(32)
        self.stream_btn.clicked.connect(self._toggle_stream)
        stream_row.addWidget(self.stream_btn)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["HD (stream1)", "SD (stream2)"])
        stream_row.addWidget(self.quality_combo)

        layout.addLayout(stream_row)

        self.ptz_widget = QWidget()
        self.ptz_widget.setEnabled(False)
        ptz_layout = QVBoxLayout(self.ptz_widget)
        ptz_layout.setContentsMargins(0, 0, 0, 0)
        ptz_layout.setSpacing(8)

        grid_container = QWidget()
        grid_outer = QHBoxLayout(grid_container)
        grid_outer.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.setSpacing(6)
        btn_size = 50

        self.ptz_up = QPushButton("▲")
        self.ptz_up.setFixedSize(btn_size, btn_size)
        self.ptz_down = QPushButton("▼")
        self.ptz_down.setFixedSize(btn_size, btn_size)
        self.ptz_left = QPushButton("◀")
        self.ptz_left.setFixedSize(btn_size, btn_size)
        self.ptz_right = QPushButton("▶")
        self.ptz_right.setFixedSize(btn_size, btn_size)

        grid.addWidget(self.ptz_up, 0, 1)
        grid.addWidget(self.ptz_left, 1, 0)
        grid.addWidget(self.ptz_right, 1, 2)
        grid.addWidget(self.ptz_down, 2, 1)

        grid_outer.addStretch()
        grid_outer.addLayout(grid)
        grid_outer.addStretch()

        ptz_layout.addWidget(grid_container)
        ptz_layout.addStretch()

        layout.addWidget(self.ptz_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.save_btn.clicked.connect(self._save_config)
        self.reset_btn.clicked.connect(self._reset_config)

        self.ptz_up.pressed.connect(lambda: self._ptz_move(0, 0.3))
        self.ptz_up.released.connect(self._ptz_stop)
        self.ptz_down.pressed.connect(lambda: self._ptz_move(0, -0.3))
        self.ptz_down.released.connect(self._ptz_stop)
        self.ptz_left.pressed.connect(lambda: self._ptz_move(-0.3, 0))
        self.ptz_left.released.connect(self._ptz_stop)
        self.ptz_right.pressed.connect(lambda: self._ptz_move(0.3, 0))
        self.ptz_right.released.connect(self._ptz_stop)

    def _check_camera_status(self):
        ip = self.ip_edit.text().strip()
        if not ip:
            self.status_label.setText("● No IP configured")
            self.status_label.setStyleSheet("color: #888888; padding: 4px 0;")
            return

        def check():
            try:
                s = socket.create_connection((ip, 554), timeout=2)
                s.close()
                return True
            except OSError:
                return False

        def done(ok):
            if ok:
                self.status_label.setText("● Camera reachable")
                self.status_label.setStyleSheet(
                    "color: #22c55e; padding: 4px 0; font-weight: bold;")
            else:
                self.status_label.setText("● Camera unreachable")
                self.status_label.setStyleSheet(
                    "color: #ef4444; padding: 4px 0; font-weight: bold;")

        self.status_label.setText("● Checking...")
        self.status_label.setStyleSheet("color: #888888; padding: 4px 0;")
        t = QThread(self)
        w = _Worker(check)
        w.moveToThread(t)
        t.started.connect(w.run)
        w.finished.connect(done)
        w.finished.connect(t.quit)
        w.finished.connect(w.deleteLater)
        t.finished.connect(t.deleteLater)
        t.start()

    def _init_ptz(self):
        self._cleanup_ptz()
        ip = self.ip_edit.text().strip()
        user = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        if not ip or not user or not password:
            self.ptz_widget.setEnabled(False)
            self.status_bar.showMessage("Enter credentials to connect", 3000)
            return

        self.ptz_widget.setEnabled(False)
        self.status_bar.showMessage("Connecting...", 3000)

        self.ptz_thread = QThread(self)
        self.ptz_worker = PTZWorker()
        self.ptz_worker.moveToThread(self.ptz_thread)
        self.ptz_worker.connected.connect(self._on_ptz_connected)
        self.ptz_worker.error.connect(self._on_ptz_error)
        self.ptz_thread.started.connect(
            lambda: self.ptz_worker.connect(ip, user, password))
        self.ptz_thread.start()

    def _on_ptz_connected(self, ok):
        if ok:
            self.ptz_widget.setEnabled(True)
            self.status_bar.showMessage("PTZ ready", 3000)
        else:
            self.ptz_widget.setEnabled(False)
            self.status_bar.showMessage("Connection failed", 3000)

    def _on_ptz_error(self, msg):
        self.status_bar.showMessage(f"Error: {msg}", 5000)

    def _ptz_move(self, pan, tilt):
        if self.ptz_worker:
            self.ptz_worker.continuous_move(pan, tilt)

    def _ptz_stop(self):
        if self.ptz_worker:
            self.ptz_worker.stop()

    def _cleanup_ptz(self):
        if self.ptz_thread:
            self.ptz_thread.quit()
            self.ptz_thread.wait(3000)
            self.ptz_thread = None
            self.ptz_worker = None

    def _load_config(self):
        if not CONFIG_FILE.exists():
            return
        with open(CONFIG_FILE) as f:
            for line in f:
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                val = value.strip()
                if key == "TAPO_USER":
                    self.username_edit.setText(val)
                elif key == "TAPO_PASS":
                    try:
                        val = base64.b64decode(val).decode()
                    except Exception:
                        pass
                    self.password_edit.setText(val)
                elif key == "TAPO_IP":
                    self.ip_edit.setText(val)

    def _save_config(self):
        ip = self.ip_edit.text().strip()
        if ip and not _validate_ip(ip):
            QMessageBox.warning(self, "Invalid IP",
                                "Please enter a valid IP address.")
            return
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        encoded_pass = base64.b64encode(
            self.password_edit.text().encode()).decode()
        with open(CONFIG_FILE, "w") as f:
            f.write(f"TAPO_USER={self.username_edit.text()}\n")
            f.write(f"TAPO_PASS={encoded_pass}\n")
            f.write(f"TAPO_IP={ip}\n")
        os.chmod(CONFIG_FILE, 0o600)
        self._check_camera_status()
        self._init_ptz()

    def _reset_config(self):
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        self.username_edit.clear()
        self.password_edit.clear()
        self.ip_edit.clear()
        self._cleanup_ptz()
        self.ptz_widget.setEnabled(False)
        self.status_label.setText("● No IP configured")
        self.status_label.setStyleSheet("color: #888888; padding: 4px 0;")
        self.status_bar.showMessage("Configuration reset", 3000)

    def _build_rtsp_url(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        ip = self.ip_edit.text().strip()
        stream = "stream1" if self.quality_combo.currentIndex() == 0 else "stream2"
        encoded_user = urllib.parse.quote(username, safe="")
        encoded_pass = urllib.parse.quote(password, safe="")
        return f"rtsp://{encoded_user}:{encoded_pass}@{ip}/{stream}"

    def _create_player(self):
        if self.player:
            return
        self.error_log = tempfile.NamedTemporaryFile(
            prefix="tapitocam_", suffix=".log", delete=False)

        self.player = mpv.MPV(
            profile="fast",
            untimed=True,
            cache="no",
            demuxer_readahead_secs=0,
            vd_lavc_threads=1,
            rtsp_transport="udp",
            demuxer_lavf_o=(
                "fflags=+nobuffer,"
                "probesize=5000000,"
                "analyzeduration=5000000"
            ),
            video_sync="audio",
            log_file=self.error_log.name,
            quiet=True,
        )

        self.player.register_event_callback(self._on_player_event)

    def _on_player_event(self, event):
        if event.event_id == mpv.MpvEventID.END_FILE:
            reason = event.data.reason if event.data else None
            if reason == mpv.MpvEventEndFile.ERROR:
                log_path = self.error_log.name if self.error_log else None
                if log_path:
                    error = self._check_network_error(log_path)
                    if error:
                        self.stream_errored.emit(error)
            self.stream_ended.emit()

    def _on_stream_ended(self):
        self._streaming = False
        self._set_streaming_state(False)
        self._cleanup_log()

    @Slot()
    def _start_stream(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        ip = self.ip_edit.text().strip()

        if not username or not password or not ip:
            QMessageBox.warning(self, "Missing Fields",
                                "Please enter camera credentials and IP.")
            return

        if not _validate_ip(ip):
            QMessageBox.warning(self, "Invalid IP",
                                "Please enter a valid IP address.")
            return

        self._create_player()
        rtsp_url = self._build_rtsp_url()
        try:
            self.player.play(rtsp_url)
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to start stream:\n{e}")
            return

        self._streaming = True
        self._set_streaming_state(True)
        self.status_bar.showMessage("Stream started", 3000)

    @Slot()
    def _stop_stream(self):
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
            try:
                self.player.terminate()
            except Exception:
                pass
            self.player = None
        self._cleanup_log()
        self._streaming = False
        self._set_streaming_state(False)
        self.status_bar.showMessage("Stream stopped", 3000)

    def _toggle_stream(self):
        if self._streaming:
            self._stop_stream()
        else:
            self._start_stream()

    def _set_streaming_state(self, streaming):
        self.stream_btn.setText("■  Stop Stream" if streaming else "▶  Open Stream")
        self.save_btn.setEnabled(not streaming)
        self.reset_btn.setEnabled(not streaming)
        self.username_edit.setReadOnly(streaming)
        self.password_edit.setReadOnly(streaming)
        self.ip_edit.setReadOnly(streaming)
        self.quality_combo.setEnabled(not streaming)
        self.status_bar.showMessage(
            "Streaming" if streaming else "Ready", 3000)

    def _check_network_error(self, log_path):
        try:
            with open(log_path) as f:
                for line in f:
                    for pattern in NETWORK_ERRORS:
                        if re.search(pattern, line, re.IGNORECASE):
                            return line.strip()
        except OSError:
            pass
        return None

    @Slot(str)
    def _handle_network_error(self, error_msg):
        self.status_bar.showMessage("Connection Error", 5000)
        reply = QMessageBox.question(
            self, "Connection Error",
            f"Network error detected:\n{error_msg}\n\n"
            "Would you like to enter a different camera IP?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            ip, ok = QInputDialog.getText(
                self, "Change Camera IP",
                "Enter new camera IP:",
                text=self.ip_edit.text())
            if ok and ip.strip():
                self.ip_edit.setText(ip.strip())
                self.status_bar.showMessage(
                    "IP updated. Click Start to retry.", 5000)

    def _cleanup_player(self):
        if self.player:
            try:
                self.player.terminate()
            except Exception:
                pass
            self.player = None
        self._cleanup_log()

    def _cleanup_log(self):
        if self.error_log:
            try:
                self.error_log.close()
                os.unlink(self.error_log.name)
            except OSError:
                pass
            self.error_log = None

    def closeEvent(self, event):
        self._cleanup_ptz()
        self._cleanup_player()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("tapitoCAM")
    app.setStyle("Fusion")

    app.setStyleSheet("""
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
            background: #3b82f6;
            color: #ffffff;
            border-color: #3b82f6;
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
        QLineEdit:disabled {
            background: #1a1a1a;
            color: #666666;
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
            subcontrol-origin: padding;
            subcontrol-position: top right;
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
        QStatusBar {
            background: #1a1a1a;
            color: #888888;
            border-top: 1px solid #333333;
            padding: 4px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

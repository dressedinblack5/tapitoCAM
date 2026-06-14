#!/usr/bin/env python3
"""tapitoCAM — multi-camera TP-Link Tapo RTSP control center.

Streams play in standalone mpv windows (one per camera).  The GUI acts
as a control panel for selecting cameras, managing PTZ, and starting /
stopping streams.
"""

import locale
import os

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")

import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import urllib.parse  # noqa: E402

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from cameraconfig import ConfigManager  # noqa: E402
from cameradialog import CameraManagerDialog  # noqa: E402
from cameratile import PTZController  # noqa: E402


# ===========================================================================
# Main Window
# ===========================================================================

class MainWindow(QMainWindow):
    """Control center for multiple Tapo cameras."""

    def __init__(self):
        super().__init__()
        self._cfg = ConfigManager()

        # camera_id -> subprocess.Popen
        self._processes: dict[int, subprocess.Popen] = {}

        # camera_id -> PTZController (synchronous, no threads)
        self._ptz_controllers: dict[int, PTZController] = {}

        self._current_camera_id: int | None = None
        self._updating_selector = False

        self._init_ui()
        self._refresh_camera_list()
        self._migrate_if_needed()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("tapitoCAM")
        self.setMinimumSize(420, 480)
        self.resize(480, 540)

        central = QWidget()
        central.setObjectName("central_widget")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # ---- Toolbar ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._manage_btn = QPushButton("Manage Cameras")
        self._manage_btn.clicked.connect(self._on_manage_cameras)

        self._start_all_btn = QPushButton("▶ Start All")
        self._start_all_btn.clicked.connect(self._start_all)

        self._stop_all_btn = QPushButton("■ Stop All")
        self._stop_all_btn.clicked.connect(self._stop_all)

        toolbar.addWidget(self._manage_btn)
        toolbar.addStretch()
        toolbar.addWidget(self._start_all_btn)
        toolbar.addWidget(self._stop_all_btn)
        layout.addLayout(toolbar)

        # ---- Camera selector ----
        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_row.addWidget(QLabel("Camera:"))
        self._camera_combo = QComboBox()
        self._camera_combo.setMinimumWidth(240)
        self._camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        selector_row.addWidget(self._camera_combo, stretch=1)
        layout.addLayout(selector_row)

        # ---- Camera info panel ----
        info_panel = QWidget()
        info_panel.setObjectName("info_panel")
        info_panel.setStyleSheet(
            "QWidget#info_panel { background: #1a1a1a; border: 1px solid #333333;"
            " border-radius: 8px; }"
        )
        info_layout = QVBoxLayout(info_panel)
        info_layout.setSpacing(8)
        info_layout.setContentsMargins(12, 12, 12, 12)

        # Camera details
        self._name_label = QLabel("No camera selected")
        self._name_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #e0e0e0;"
        )
        info_layout.addWidget(self._name_label)

        detail_grid = QFormLayout()
        detail_grid.setSpacing(4)
        self._ip_label = QLabel("—")
        self._ip_label.setStyleSheet("color: #aaaaaa;")
        self._status_label = QLabel("● —")
        self._status_label.setStyleSheet("color: #888888; padding: 2px 0;")
        detail_grid.addRow("IP:", self._ip_label)
        detail_grid.addRow("Status:", self._status_label)
        info_layout.addLayout(detail_grid)

        # Stream controls
        stream_row = QHBoxLayout()
        stream_row.setSpacing(8)

        self._stream_btn = QPushButton("▶ Open Stream")
        self._stream_btn.setMinimumHeight(34)
        self._stream_btn.clicked.connect(self._toggle_stream)
        self._stream_btn.setEnabled(False)
        stream_row.addWidget(self._stream_btn)

        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["HD (stream1)", "SD (stream2)"])
        self._quality_combo.setEnabled(False)
        stream_row.addWidget(self._quality_combo)

        stream_row.addStretch()
        info_layout.addLayout(stream_row)

        # PTZ controls
        ptz_widget = QWidget()
        ptz_widget.setObjectName("ptz_widget")
        ptz_grid = QGridLayout(ptz_widget)
        ptz_grid.setSpacing(4)
        ptz_grid.setContentsMargins(0, 0, 0, 0)

        btn_size = 48
        self._ptz_up = QPushButton("▲")
        self._ptz_up.setFixedSize(btn_size, btn_size)
        self._ptz_up.setEnabled(False)

        self._ptz_down = QPushButton("▼")
        self._ptz_down.setFixedSize(btn_size, btn_size)
        self._ptz_down.setEnabled(False)

        self._ptz_left = QPushButton("◀")
        self._ptz_left.setFixedSize(btn_size, btn_size)
        self._ptz_left.setEnabled(False)

        self._ptz_right = QPushButton("▶")
        self._ptz_right.setFixedSize(btn_size, btn_size)
        self._ptz_right.setEnabled(False)

        self._ptz_stop_btn = QPushButton("■")
        self._ptz_stop_btn.setFixedSize(btn_size, btn_size)
        self._ptz_stop_btn.setEnabled(False)

        ptz_grid.addWidget(self._ptz_up, 0, 1, Qt.AlignmentFlag.AlignCenter)
        ptz_grid.addWidget(self._ptz_left, 1, 0, Qt.AlignmentFlag.AlignCenter)
        ptz_grid.addWidget(self._ptz_stop_btn, 1, 1, Qt.AlignmentFlag.AlignCenter)
        ptz_grid.addWidget(self._ptz_right, 1, 2, Qt.AlignmentFlag.AlignCenter)
        ptz_grid.addWidget(self._ptz_down, 2, 1, Qt.AlignmentFlag.AlignCenter)

        self._ptz_up.pressed.connect(lambda: self._ptz_move(0, 0.3))
        self._ptz_up.released.connect(self._ptz_stop)
        self._ptz_down.pressed.connect(lambda: self._ptz_move(0, -0.3))
        self._ptz_down.released.connect(self._ptz_stop)
        self._ptz_left.pressed.connect(lambda: self._ptz_move(-0.3, 0))
        self._ptz_left.released.connect(self._ptz_stop)
        self._ptz_right.pressed.connect(lambda: self._ptz_move(0.3, 0))
        self._ptz_right.released.connect(self._ptz_stop)
        self._ptz_stop_btn.clicked.connect(self._ptz_stop)

        ptz_row = QHBoxLayout()
        ptz_row.addStretch()
        ptz_row.addWidget(ptz_widget)
        ptz_row.addStretch()
        info_layout.addLayout(ptz_row)

        layout.addWidget(info_panel, stretch=1)

        # ---- Status bar ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready", 3000)

        # Timer to refresh streaming status in UI
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self._sync_ui)
        self._refresh_timer.start()

    # ------------------------------------------------------------------
    # Camera list / selection
    # ------------------------------------------------------------------

    def _migrate_if_needed(self):
        if self._cfg.migrate_from_env():
            self.status_bar.showMessage(
                "Migrated old config to new format", 4000
            )
            self._refresh_camera_list()

    def _refresh_camera_list(self):
        self._updating_selector = True
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()

        cameras = self._cfg.load()
        if not cameras:
            self._camera_combo.addItem("— No cameras configured —", None)
        else:
            for cam in cameras:
                label = f"{cam.get('name', '?')}  —  {cam.get('ip', '?.?.?.?')}"
                self._camera_combo.addItem(label, cam.get("id"))

        self._camera_combo.blockSignals(False)
        self._updating_selector = False

        if cameras:
            self._camera_combo.setCurrentIndex(0)
            self._on_camera_selected(0)
        else:
            self._on_camera_selected(-1)

    def _on_camera_selected(self, index: int):
        if self._updating_selector:
            return
        camera_id = self._camera_combo.itemData(index)
        self._current_camera_id = camera_id
        self._select_camera(camera_id)

    def _select_camera(self, camera_id: int | None):
        """Populate the control panel for the given camera."""
        if camera_id is None:
            self._name_label.setText("No camera selected")
            self._ip_label.setText("—")
            self._status_label.setText("● —")
            self._stream_btn.setEnabled(False)
            self._quality_combo.setEnabled(False)
            self._set_ptz_enabled(False)
            return

        camera = self._cfg.get_camera(camera_id)
        if not camera:
            return

        name = camera.get("name", f"Camera {camera_id}")
        ip = camera.get("ip", "?")
        self._name_label.setText(name)
        self._ip_label.setText(ip)
        self._quality_combo.setCurrentIndex(
            0 if camera.get("quality", "hd") == "hd" else 1
        )
        self._stream_btn.setEnabled(True)
        self._quality_combo.setEnabled(True)

        self._sync_ui()

        # Connect PTZ for this camera (brief blocking ~1-3s for ONVIF init)
        self._connect_ptz(camera_id)

    def _sync_ui(self):
        """Update the stream button and status label to reflect reality.

        Also prunes any mpv processes that have exited (connection errors).
        """
        self._prune_dead_processes()

        cam_id = self._current_camera_id
        if cam_id is None:
            return

        is_streaming = cam_id in self._processes
        self._stream_btn.setText("■ Stop Stream" if is_streaming else "▶ Open Stream")

        if is_streaming:
            self._status_label.setText("● Streaming")
            self._status_label.setStyleSheet(
                "color: #22c55e; padding: 2px 0; font-weight: bold;"
            )
        else:
            self._status_label.setText("● Ready")
            self._status_label.setStyleSheet("color: #888888; padding: 2px 0;")

        # Update Start All / Stop All button states
        cameras = self._cfg.load()
        has_any = len(cameras) > 0
        any_streaming = len(self._processes) > 0
        all_streaming = has_any and len(self._processes) >= len(cameras)

        self._start_all_btn.setEnabled(has_any and not all_streaming)
        self._stop_all_btn.setEnabled(any_streaming)

    def _prune_dead_processes(self):
        """Remove mpv processes that have exited and report failures."""
        dead = []
        for cid, proc in list(self._processes.items()):
            rc = proc.poll()
            if rc is not None:
                dead.append((cid, rc))
        for cid, rc in dead:
            self._processes.pop(cid, None)
            camera = self._cfg.get_camera(cid)
            name = camera.get("name", f"Camera {cid}") if camera else f"Camera {cid}"
            if rc != 0:
                self.status_bar.showMessage(
                    f"Stream failed: {name} (mpv exited with code {rc})", 5000
                )
            else:
                self.status_bar.showMessage(f"Stream ended: {name}", 3000)

    # ------------------------------------------------------------------
    # Stream control (subprocess mpv)
    # ------------------------------------------------------------------

    def _toggle_stream(self):
        cam_id = self._current_camera_id
        if cam_id is None:
            return
        if cam_id in self._processes:
            self._stop_camera(cam_id)
        else:
            self._start_camera(cam_id)

    def _start_camera(self, camera_id: int):
        """Launch mpv for a camera in a standalone window."""
        camera = self._cfg.get_camera(camera_id)
        if not camera:
            return

        if camera_id in self._processes:
            return  # already running

        username = camera.get("username", "")
        password = camera.get("password", "")
        ip = camera.get("ip", "")
        quality_idx = self._quality_combo.currentIndex()
        stream = "stream1" if quality_idx == 0 else "stream2"

        encoded_user = urllib.parse.quote(username, safe="")
        encoded_pass = urllib.parse.quote(password, safe="")
        rtsp_url = f"rtsp://{encoded_user}:{encoded_pass}@{ip}/{stream}"

        title = camera.get("name", f"Camera {camera_id}")

        mpv_opts = [
            "mpv",
            f"--title=tapitoCAM — {title}",
            "--profile=fast",
            "--untimed",
            "--cache=no",
            "--demuxer-readahead-secs=0",
            "--vd-lavc-threads=1",
            "--rtsp-transport=udp",
            "--demuxer-lavf-o-add=fflags=+nobuffer",
            "--demuxer-lavf-o-add=probesize=5000000",
            "--demuxer-lavf-o-add=analyzeduration=5000000",
            "--video-sync=audio",
            rtsp_url,
        ]

        try:
            proc = subprocess.Popen(
                mpv_opts,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes[camera_id] = proc
            self.status_bar.showMessage(f"Started: {title}", 3000)
        except FileNotFoundError:
            QMessageBox.critical(
                self, "mpv Not Found",
                "mpv is not installed. Install it with:\n"
                "  sudo apt install mpv"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start mpv:\n{e}")

        self._sync_ui()

    def _stop_camera(self, camera_id: int):
        """Kill mpv for a camera."""
        proc = self._processes.pop(camera_id, None)
        if proc is None:
            return
        try:
            # Kill the entire process group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        camera = self._cfg.get_camera(camera_id)
        name = camera.get("name", f"Camera {camera_id}") if camera else f"Camera {camera_id}"
        self.status_bar.showMessage(f"Stopped: {name}", 3000)
        self._sync_ui()

    def _start_all(self):
        cameras = self._cfg.load()
        count = 0
        for cam in cameras:
            cid = cam["id"]
            if cid not in self._processes:
                self._start_camera(cid)
                count += 1
        if count:
            self.status_bar.showMessage(f"Started {count} camera(s)", 3000)

    def _stop_all(self):
        count = len(self._processes)
        for cid in list(self._processes.keys()):
            self._stop_camera(cid)
        if count:
            self.status_bar.showMessage(f"Stopped {count} camera(s)", 3000)

    # ------------------------------------------------------------------
    # PTZ  (synchronous — no threads, UI-safe)
    # ------------------------------------------------------------------

    def _connect_ptz(self, camera_id: int):
        """Blocking ONVIF connect for a camera.  Called from main thread."""
        # Don't re-connect if already cached
        if camera_id in self._ptz_controllers:
            ctrl = self._ptz_controllers[camera_id]
            if ctrl.is_connected:
                self._set_ptz_enabled(camera_id in self._processes)
                self.status_bar.showMessage("PTZ ready", 3000)
                return

        camera = self._cfg.get_camera(camera_id)
        if not camera:
            return
        ip = camera.get("ip", "")
        user = camera.get("username", "")
        password = camera.get("password", "")
        if not ip or not user or not password:
            return

        self.status_bar.showMessage("Connecting PTZ...", 2000)
        ctrl = PTZController()
        ok = ctrl.connect(ip, user, password)
        self._ptz_controllers[camera_id] = ctrl
        if ok:
            self._set_ptz_enabled(camera_id in self._processes)
            self.status_bar.showMessage("PTZ ready", 3000)
        else:
            self._set_ptz_enabled(False)
            self.status_bar.showMessage("PTZ connection failed", 3000)

    def _set_ptz_enabled(self, enabled: bool):
        for btn in (self._ptz_up, self._ptz_down, self._ptz_left,
                    self._ptz_right, self._ptz_stop_btn):
            btn.setEnabled(enabled)

    def _ptz_move(self, pan: float, tilt: float):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.continuous_move(pan, tilt)

    def _ptz_stop(self):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.stop()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_manage_cameras(self):
        self._stop_all()
        dialog = CameraManagerDialog(self, self._cfg)
        before = [str(c) for c in self._cfg.load()]
        if dialog.exec() == QDialog.DialogCode.Accepted:
            cameras = self._cfg.load()
            after = [str(c) for c in cameras]
            if before != after:
                self._refresh_camera_list()
                self.status_bar.showMessage("Camera config updated", 3000)
        else:
            self._refresh_camera_list()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._refresh_timer.stop()
        self._stop_all()
        for ctrl in self._ptz_controllers.values():
            ctrl.cleanup()
        self._ptz_controllers.clear()
        super().closeEvent(event)


# ===========================================================================
# App entry point
# ===========================================================================

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
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

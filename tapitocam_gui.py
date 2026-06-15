#!/usr/bin/env python3
"""tapitoCAM — multi-camera TP-Link Tapo RTSP control center.

Streams play in standalone mpv windows (one per camera).  The GUI acts
as a control panel for selecting cameras, managing PTZ, and starting /
stopping streams.
"""

import atexit
import locale
import os

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")

import signal  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from cameraconfig import ConfigManager  # noqa: E402
from cameradialog import CameraManagerDialog  # noqa: E402
from cameratile import PTZController  # noqa: E402
from motionmonitor import MotionMonitor  # noqa: E402
from styles import DARK_THEME  # noqa: E402
from utils import (  # noqa: E402
    build_rtsp_url,
    get_mpv_playlist_command,
    is_auth_error,
    is_mpv_connection_error,
    sanitize_onvif_error,
    write_rtsp_playlist,
)


# ===========================================================================
# Main Window
# ===========================================================================


class MainWindow(QMainWindow):
    """Control center for multiple Tapo cameras."""

    def __init__(self):
        super().__init__()
        self._cfg = ConfigManager()

        # camera_id -> subprocess.Popen (shared with global crash handler)
        self._processes: dict[int, subprocess.Popen] = _process_registry

        # camera_id -> playlist temp file path (shared with global crash handler)
        self._playlist_files: dict[int, str] = _playlist_registry

        # camera_id -> PTZController (synchronous, no threads)
        self._ptz_controllers: dict[int, PTZController] = {}

        # Motion detection
        self._motion_monitor = MotionMonitor(self)
        self._motion_monitor.motion_changed.connect(self._on_motion_changed)
        self._motion_monitor.error_occurred.connect(
            lambda msg: self.status_bar.showMessage(msg, 0)
        )

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
        self.setMinimumSize(400, 580)
        self.resize(400, 580)

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

        self._motion_label = QLabel("⚫")
        self._motion_label.setStyleSheet("color: #555555; padding: 2px 0;")
        self._motion_count = 0
        self._motion_count_label = QLabel("(0)")
        self._motion_count_label.setStyleSheet("color: #666666; padding: 2px 0; font-size: 12px;")

        motion_row = QHBoxLayout()
        motion_row.setSpacing(4)
        motion_row.setContentsMargins(0, 0, 0, 0)
        motion_row.addWidget(self._motion_label)
        motion_row.addWidget(self._motion_count_label)
        motion_row.addStretch()

        detail_grid.addRow("Motion:", motion_row)
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
        ptz_container = QVBoxLayout()
        ptz_container.setSpacing(6)
        ptz_container.setContentsMargins(0, 0, 0, 0)

        # Direction pad
        pad_widget = QWidget()
        ptz_grid = QGridLayout(pad_widget)
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

        # Zoom row
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(8)
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.addStretch()

        self._ptz_zoom_out = QPushButton("🔍-")
        self._ptz_zoom_out.setFixedSize(btn_size, btn_size)
        self._ptz_zoom_out.setEnabled(False)

        self._ptz_zoom_in = QPushButton("🔍+")
        self._ptz_zoom_in.setFixedSize(btn_size, btn_size)
        self._ptz_zoom_in.setEnabled(False)

        zoom_row.addWidget(self._ptz_zoom_out)
        zoom_row.addWidget(self._ptz_zoom_in)
        zoom_row.addStretch()

        self._ptz_zoom_in.pressed.connect(lambda: self._ptz_zoom(0.3))
        self._ptz_zoom_in.released.connect(self._ptz_stop)
        self._ptz_zoom_out.pressed.connect(lambda: self._ptz_zoom(-0.3))
        self._ptz_zoom_out.released.connect(self._ptz_stop)

        # Assemble
        pad_row = QHBoxLayout()
        pad_row.addStretch()
        pad_row.addWidget(pad_widget)
        pad_row.addStretch()

        ptz_container.addLayout(pad_row)
        ptz_container.addLayout(zoom_row)

        wrapper_row = QHBoxLayout()
        wrapper_row.addStretch()
        wrapper_row.addLayout(ptz_container)
        wrapper_row.addStretch()
        info_layout.addLayout(wrapper_row)

        # Preset controls
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        preset_row.addStretch()
        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(140)
        self._preset_combo.setEnabled(False)
        self._preset_combo.addItem("— no presets —")
        preset_row.addWidget(self._preset_combo)
        self._preset_go_btn = QPushButton()
        self._preset_go_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        self._preset_go_btn.setFixedSize(38, 32)
        self._preset_go_btn.setEnabled(False)
        self._preset_go_btn.clicked.connect(self._ptz_preset_go)
        preset_row.addWidget(self._preset_go_btn)
        self._preset_save_btn = QPushButton()
        self._preset_save_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self._preset_save_btn.setFixedSize(38, 32)
        self._preset_save_btn.setEnabled(False)
        self._preset_save_btn.clicked.connect(self._ptz_preset_save)
        preset_row.addWidget(self._preset_save_btn)
        self._preset_del_btn = QPushButton()
        self._preset_del_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        )
        self._preset_del_btn.setFixedSize(32, 32)
        self._preset_del_btn.setEnabled(False)
        self._preset_del_btn.clicked.connect(self._ptz_preset_delete)
        preset_row.addWidget(self._preset_del_btn)
        preset_row.addStretch()
        info_layout.addLayout(preset_row)

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
            self.status_bar.showMessage("Migrated old config to new format", 4000)
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
            self._set_pantilt_enabled(False)
            self._set_zoom_enabled(False)
            self._preset_combo.clear()
            self._preset_combo.addItem("— no presets —")
            self._preset_combo.clear()
            self._preset_combo.addItem("— no presets —")
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

        # Reset motion + preset state for new camera
        self._motion_monitor.stop()
        self._motion_label.setText("⚫")
        self._motion_count = 0
        self._motion_count_label.setText("(0)")
        self._motion_label.setStyleSheet("color: #555555; padding: 2px 0;")

        # Reset preset selector until PTZ connects
        self._preset_combo.clear()
        self._preset_combo.addItem("Loading presets...")
        self._preset_combo.setEnabled(False)
        self._preset_save_btn.setEnabled(False)
        self._preset_go_btn.setEnabled(False)
        self._preset_del_btn.setEnabled(False)

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

        # Sync PTZ enabled state — this runs on a 2s timer so it catches
        # the case where streaming started *after* the async PTZ callback fired.
        cam_id = self._current_camera_id
        if cam_id is not None:
            ctrl = self._ptz_controllers.get(cam_id)
            if ctrl is not None and ctrl.is_connected:
                is_streaming = cam_id in self._processes
                self._set_pantilt_enabled(is_streaming)
                self._set_zoom_enabled(is_streaming and ctrl.has_zoom)

    def _prune_dead_processes(self):
        """Remove mpv processes that have exited or report connection errors."""
        dead = []
        for cid, proc in list(self._processes.items()):
            if proc.stderr:
                try:
                    data = proc.stderr.read(4096)
                except Exception:
                    data = b""
                if data:
                    text = data.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    if self._is_mpv_connection_error(text):
                        self._stop_camera(cid)
                        camera = self._cfg.get_camera(cid)
                        name = (
                            camera.get("name", f"Camera {cid}")
                            if camera
                            else (f"Camera {cid}")
                        )
                        if is_auth_error(text):
                            self.status_bar.showMessage(
                                f"Auth failed: {name} — check username/password",
                                0,
                            )
                        else:
                            short = text.replace("\n", " ")[:120]
                            self.status_bar.showMessage(
                                f"Stream error: {name} — {short}", 0
                            )
                        continue

            rc = proc.poll()
            if rc is not None:
                dead.append((cid, rc))
        for cid, rc in dead:
            self._processes.pop(cid, None)
            playlist = self._playlist_files.pop(cid, None)
            if playlist:
                try:
                    os.unlink(playlist)
                except OSError:
                    pass
            camera = self._cfg.get_camera(cid)
            name = camera.get("name", f"Camera {cid}") if camera else f"Camera {cid}"
            if rc != 0:
                self.status_bar.showMessage(
                    f"Stream failed: {name} (mpv exited with code {rc})", 0
                )
            else:
                self.status_bar.showMessage(f"Stream ended: {name}", 3000)

    @staticmethod
    def _is_mpv_connection_error(text: str) -> bool:
        """Return True if *text* from mpv stderr indicates a connection failure."""
        return is_mpv_connection_error(text)

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

        rtsp_url = build_rtsp_url(username, password, ip, stream)
        title = camera.get("name", f"Camera {camera_id}")

        playlist_path = write_rtsp_playlist(rtsp_url)
        mpv_opts = get_mpv_playlist_command(title, playlist_path)

        try:
            proc = subprocess.Popen(
                mpv_opts,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if proc.stderr:
                os.set_blocking(proc.stderr.fileno(), False)
            self._processes[camera_id] = proc
            self._playlist_files[camera_id] = playlist_path
            self.status_bar.showMessage(f"Started: {title}", 3000)

            # Start motion detection for this camera
            self._motion_monitor.start(ip, username, password)
        except FileNotFoundError:
            os.unlink(playlist_path)
            QMessageBox.critical(
                self,
                "mpv Not Found",
                "mpv is not installed. Install it with:\n  sudo apt install mpv",
            )
        except Exception as e:
            os.unlink(playlist_path)
            err = str(e)
            if is_mpv_connection_error(err):
                self.status_bar.showMessage(
                    f"Stream error: {title} — {err}", 0
                )
            else:
                self.status_bar.showMessage(
                    f"Stream failed: {err[:120]}", 0
                )

        self._sync_ui()

    def _stop_camera(self, camera_id: int):
        """Kill mpv for a camera."""
        proc = self._processes.pop(camera_id, None)
        playlist = self._playlist_files.pop(camera_id, None)

        # Clean up the temp playlist file (prevents credential leakage on disk)
        if playlist:
            try:
                os.unlink(playlist)
            except OSError:
                pass

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
        name = (
            camera.get("name", f"Camera {camera_id}")
            if camera
            else f"Camera {camera_id}"
        )
        self._motion_monitor.stop()
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
        """Async ONVIF connect for a camera. Non-blocking."""
        # Don't re-connect if already cached and connected
        if camera_id in self._ptz_controllers:
            ctrl = self._ptz_controllers[camera_id]
            if ctrl.is_connected:
                is_streaming = camera_id in self._processes
                self._set_pantilt_enabled(is_streaming)
                self._set_zoom_enabled(is_streaming and ctrl.has_zoom)
                self._ptz_preset_refresh(camera_id)
                self.status_bar.showMessage("PTZ ready", 3000)
                return

        camera = self._cfg.get_camera(camera_id)
        if not camera:
            return
        name = camera.get("name", f"Camera {camera_id}")
        ip = camera.get("ip", "")
        user = camera.get("username", "")
        password = camera.get("password", "")
        if not ip or not user or not password:
            return

        self.status_bar.showMessage("Connecting PTZ...", 2000)

        # Create new controller if not exists
        if camera_id not in self._ptz_controllers:
            name = camera.get("name", f"Camera {camera_id}")
            self._ptz_controllers[camera_id] = PTZController(
                on_error=lambda msg: self.status_bar.showMessage(
                    f"PTZ error ({name}): {msg}", 0
                ),
            )

        ctrl = self._ptz_controllers[camera_id]

        def on_connected(success: bool, error: str):
            if success:
                is_streaming = camera_id in self._processes
                self._set_pantilt_enabled(is_streaming)
                self._set_zoom_enabled(is_streaming and ctrl.has_zoom)
                self._ptz_preset_refresh(camera_id)
                self.status_bar.showMessage("PTZ ready", 3000)
            else:
                self._set_pantilt_enabled(False)
                self._set_zoom_enabled(False)
                self._preset_combo.clear()
                self._preset_combo.addItem("— no presets —")
                if is_auth_error(error):
                    msg = f"PTZ auth failed: {name} — check camera credentials"
                else:
                    msg = f"PTZ connection failed: {sanitize_onvif_error(error)}"
                self.status_bar.showMessage(msg, 0)

        ctrl.connect_async(ip, user, password, on_connected)

    def _set_pantilt_enabled(self, enabled: bool):
        """Enable/disable pan, tilt, stop, and preset buttons."""
        for btn in (
            self._ptz_up,
            self._ptz_down,
            self._ptz_left,
            self._ptz_right,
            self._ptz_stop_btn,
        ):
            btn.setEnabled(enabled)
        self._preset_save_btn.setEnabled(enabled)
        self._preset_combo.setEnabled(enabled)
        self._preset_go_btn.setEnabled(
            enabled and self._preset_combo.currentData() is not None
        )
        self._preset_del_btn.setEnabled(
            enabled and self._preset_combo.currentData() is not None
        )

    def _set_zoom_enabled(self, enabled: bool):
        """Enable/disable zoom buttons independently of pan/tilt."""
        self._ptz_zoom_in.setEnabled(enabled)
        self._ptz_zoom_out.setEnabled(enabled)

    def _ptz_move(self, pan: float, tilt: float):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.continuous_move(pan, tilt)

    def _ptz_zoom(self, velocity: float):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.continuous_zoom(velocity)

    def _ptz_stop(self):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.stop()

    def _ptz_preset_refresh(self, camera_id: int | None = None):
        """Refresh the preset dropdown for *camera_id* (default: current).
        Only updates the combo if *camera_id* matches the currently
        selected camera, preventing stale async callbacks from
        overwriting the preset list of a different camera."""
        cam_id = camera_id if camera_id is not None else self._current_camera_id
        if cam_id is None or cam_id != self._current_camera_id:
            return
        ctrl = self._ptz_controllers.get(cam_id)
        camera = self._cfg.get_camera(cam_id)
        if not ctrl or not ctrl.is_connected:
            # Show cached presets from config if available
            if camera and camera.get("presets"):
                self._preset_combo.blockSignals(True)
                self._preset_combo.clear()
                for p in camera["presets"]:
                    self._preset_combo.addItem(p["name"], p["token"])
                self._preset_combo.blockSignals(False)
            return

        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        presets = ctrl.get_presets()
        if presets:
            for p in presets:
                self._preset_combo.addItem(p["name"], p["token"])
            # Cache presets locally so they survive camera reboots
            if camera:
                self._cfg.update_camera(cam_id, {"presets": presets})
        elif camera and camera.get("presets"):
            # Camera lost presets — show cached
            for p in camera["presets"]:
                self._preset_combo.addItem(p["name"], p["token"])
        else:
            self._preset_combo.addItem("— no presets —")
        self._preset_combo.blockSignals(False)
        self._preset_go_btn.setEnabled(
            self._preset_combo.currentData() is not None
        )
        self._preset_del_btn.setEnabled(
            self._preset_combo.currentData() is not None
        )

    def _ptz_preset_save(self):
        if self._current_camera_id is None:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if not ctrl or not ctrl.is_connected:
            return
        camera = self._cfg.get_camera(self._current_camera_id)
        name = camera.get("name", "Camera") if camera else "Camera"
        default = f"{name[:20]} pos"
        preset_name, ok = QInputDialog.getText(
            self, "Save Preset", "Preset name:", text=default
        )
        if not ok or not preset_name.strip():
            return
        token = ctrl.set_preset(preset_name.strip())
        if token:
            self.status_bar.showMessage("Preset saved", 2000)
            self._ptz_preset_refresh()
        else:
            self.status_bar.showMessage("Preset save failed", 2000)

    def _ptz_preset_go(self):
        if self._current_camera_id is None:
            return
        token = self._preset_combo.currentData()
        if not token:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl:
            ctrl.goto_preset(str(token))
            self.status_bar.showMessage("Moving to preset...", 2000)

    def _ptz_preset_delete(self):
        if self._current_camera_id is None:
            return
        token = self._preset_combo.currentData()
        if not token:
            return
        ctrl = self._ptz_controllers.get(self._current_camera_id)
        if ctrl and ctrl.remove_preset(str(token)):
            self.status_bar.showMessage("Preset deleted", 2000)
            self._ptz_preset_refresh()
        else:
            self.status_bar.showMessage("Failed to delete preset", 2000)

    def _on_motion_changed(self, is_motion: bool):
        if is_motion:
            self._motion_count += 1
        self._motion_label.setText("🔴" if is_motion else "⚫")
        self._motion_count_label.setText(f"({self._motion_count})")
        self._motion_label.setStyleSheet(
            "color: #ef4444; padding: 2px 0;"
            if is_motion
            else "color: #555555; padding: 2px 0;"
        )

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
        self._motion_monitor.stop()
        self._stop_all()
        for ctrl in self._ptz_controllers.values():
            ctrl.cleanup()
        self._ptz_controllers.clear()
        # Clean up any remaining playlist temp files
        for path in self._playlist_files.values():
            try:
                os.unlink(path)
            except OSError:
                pass
        self._playlist_files.clear()
        super().closeEvent(event)


# ===========================================================================
# Cleanup — kill orphaned mpv processes on crash
# ===========================================================================

_process_registry: dict[int, subprocess.Popen] = {}
_playlist_registry: dict[int, str] = {}


def _kill_all_processes():
    """Kill all tracked mpv processes and clean up playlist temp files."""
    for cid, proc in list(_process_registry.items()):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _process_registry.clear()
    for path in _playlist_registry.values():
        try:
            os.unlink(path)
        except OSError:
            pass
    _playlist_registry.clear()


atexit.register(_kill_all_processes)
signal.signal(signal.SIGTERM, lambda *_: _kill_all_processes())
signal.signal(signal.SIGINT, lambda *_: _kill_all_processes())


# ===========================================================================
# App entry point
# ===========================================================================


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("tapitoCAM")
    app.setStyle("Fusion")

    app.setStyleSheet(DARK_THEME)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

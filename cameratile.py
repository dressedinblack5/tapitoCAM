#!/usr/bin/env python3
"""Per-camera ONVIF PTZ controller — synchronous core with threaded connection."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot


class PTZWorker(QObject):
    """Worker that runs ONVIF operations in a background thread."""

    connected = Signal(bool, str)  # success, error_message

    def __init__(self, ip: str, user: str, password: str):
        super().__init__()
        self.ip = ip
        self.user = user
        self.password = password
        self.ptz = None
        self.profile_token = None

    @Slot()
    def run(self):
        """Connect to ONVIF service. Emits connected(success, error)."""
        try:
            from onvif import ONVIFCamera

            cam = ONVIFCamera(self.ip, 2020, self.user, self.password)
            self.ptz = cam.create_ptz_service()
            configs = self.ptz.GetConfigurations()
            self.profile_token = configs[0].token if configs else None
            self.connected.emit(True, "")
        except Exception as e:
            self.cleanup()
            self.connected.emit(False, str(e))

    @Slot(float, float)
    def continuous_move(self, pan: float, tilt: float):
        if not self.ptz or not self.profile_token:
            return
        try:
            request = self.ptz.create_type("ContinuousMove")
            request.ProfileToken = self.profile_token
            request.Velocity = {
                "PanTilt": {
                    "x": float(pan),
                    "y": float(tilt),
                    "space": (
                        "http://www.onvif.org/ver10/tptz/"
                        "PanTiltSpaces/VelocityGenericSpace"
                    ),
                },
                "Zoom": {"x": 0.0},
            }
            self.ptz.ContinuousMove(request)
        except Exception:
            pass

    @Slot()
    def stop(self):
        if not self.ptz or not self.profile_token:
            return
        try:
            request = self.ptz.create_type("Stop")
            request.ProfileToken = self.profile_token
            request.PanTilt = True
            request.Zoom = True
            self.ptz.Stop(request)
        except Exception:
            pass

    def cleanup(self):
        self.ptz = None
        self.profile_token = None

    @property
    def is_connected(self) -> bool:
        return self.ptz is not None


class PTZController(QObject):
    """Thread-safe PTZ controller for one camera.

    Connection runs in a background thread to avoid blocking the GUI.
    PTZ commands (move, stop) are forwarded to the worker thread via signals.
    """

    # Signals to forward commands to the worker thread
    _move_requested = Signal(float, float)
    _stop_requested = Signal()

    def __init__(self):
        super().__init__()
        self._thread: QThread | None = None
        self._worker: PTZWorker | None = None

    def connect_async(self, ip: str, user: str, password: str, callback):
        """Start async connection. ``callback(success: bool, error: str)`` is called when done."""
        # Clean up previous thread if finished
        self.cleanup()

        self._thread = QThread()
        self._worker = PTZWorker(ip, user, password)
        self._worker.moveToThread(self._thread)

        # Wire signal forwarding
        self._move_requested.connect(self._worker.continuous_move)
        self._stop_requested.connect(self._worker.stop)

        self._worker.connected.connect(lambda ok, err: callback(ok, err))
        self._worker.connected.connect(self._on_connected_finished)

        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_connected_finished(self, success: bool, error: str):
        """Clean up thread after connection attempt completes."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    def continuous_move(self, pan: float, tilt: float):
        if self._worker:
            self._move_requested.emit(pan, tilt)

    def stop(self):
        if self._worker:
            self._stop_requested.emit()

    @property
    def is_connected(self) -> bool:
        return self._worker is not None and self._worker.is_connected

    def cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(1000)
            self._thread = None
        if self._worker:
            self._worker.cleanup()
            self._worker = None

#!/usr/bin/env python3
"""Per-camera ONVIF PTZ controller — async connection, direct PTZ commands."""

from __future__ import annotations

import threading

from PySide6.QtCore import QTimer


class PTZController:
    """PTZ controller for one camera.

    Initial ONVIF connection runs in a background ``threading.Thread``.
    After connection, PTZ commands (move, stop) are direct method calls
    in the calling thread — ONVIF-zeep uses plain HTTP/SOAP and is safe
    to call from the main thread.
    """

    def __init__(self):
        self.ptz = None
        self.profile_token = None
        self._thread: threading.Thread | None = None

    def connect_async(self, ip: str, user: str, password: str, callback):
        """Start ONVIF connection in a background thread.

        ``callback(success: bool, error: str)`` is invoked in the **main**
        thread when the connection attempt finishes.
        """

        def _run():
            try:
                from onvif import ONVIFCamera

                cam = ONVIFCamera(ip, 2020, user, password)
                self.ptz = cam.create_ptz_service()
                configs = self.ptz.GetConfigurations()
                self.profile_token = configs[0].token if configs else None
                ok, err = True, ""
            except Exception as e:
                self.cleanup()
                ok, err = False, str(e)

            # Hoist callback result to the main thread
            QTimer.singleShot(0, lambda: callback(ok, err))

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

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

    @property
    def is_connected(self) -> bool:
        return self.ptz is not None

    def cleanup(self):
        self.ptz = None
        self.profile_token = None
        self._thread = None
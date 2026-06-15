#!/usr/bin/env python3
"""Per-camera ONVIF PTZ controller — async connection, direct PTZ commands."""

from __future__ import annotations

import sys
import threading

from onvif import ONVIFCamera
from PySide6.QtCore import QTimer


class PTZController:
    """PTZ controller for one camera.

    Initial ONVIF connection runs in a background ``threading.Thread``.
    After connection, PTZ commands (move, stop) are direct method calls
    in the calling thread — ONVIF-zeep uses plain HTTP/SOAP and is safe
    to call from the main thread.
    """

    ONVIF_PORT = 2020

    def __init__(self):
        self.ptz = None
        self.profile_token = None
        self._thread: threading.Thread | None = None

    def _run_connect(
        self, host: str, user: str, password: str, callback
    ):
        """Synchronous ONVIF connect — runs in a background thread.

        Exposed as a separate method so tests can call it directly
        without going through ``threading.Thread``.
        """
        try:
            cam = ONVIFCamera(host, self.ONVIF_PORT, user, password)
            self.ptz = cam.create_ptz_service()

            # Verify PTZ support by fetching configurations
            configs = self.ptz.GetConfigurations()

            # The ProfileToken for ContinuousMove / Stop must come from
            # a Media profile, NOT from a PTZ configuration token.
            media = cam.create_media_service()
            profiles = media.GetProfiles()
            if profiles:
                self.profile_token = profiles[0].token
            elif configs:
                # Fallback: use the first PTZ config token (some cameras
                # accept this as a ProfileToken).
                self.profile_token = configs[0].token
            else:
                self.cleanup()
                QTimer.singleShot(
                    0,
                    lambda: callback(
                        False,
                        "No media profiles or PTZ configurations found",
                    ),
                )
                return

            ok, err = True, ""
        except Exception as e:
            self.cleanup()
            ok, err = False, str(e)

        QTimer.singleShot(0, lambda: callback(ok, err))

    def connect_async(self, host: str, user: str, password: str, callback):
        """Start ONVIF connection in a background thread.

        ``callback(success: bool, error: str)`` is invoked in the **main**
        thread when the connection attempt finishes.
        """
        self._thread = threading.Thread(
            target=self._run_connect,
            args=(host, user, password, callback),
            daemon=True,
        )
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
        except Exception as exc:
            print(
                f"[PTZ] ContinuousMove failed: {exc}",
                file=sys.stderr,
            )

    def stop(self):
        if not self.ptz or not self.profile_token:
            return
        try:
            request = self.ptz.create_type("Stop")
            request.ProfileToken = self.profile_token
            request.PanTilt = True
            request.Zoom = True
            self.ptz.Stop(request)
        except Exception as exc:
            print(
                f"[PTZ] Stop failed: {exc}",
                file=sys.stderr,
            )

    @property
    def is_connected(self) -> bool:
        return self.ptz is not None

    def cleanup(self):
        self.ptz = None
        self.profile_token = None
        self._thread = None

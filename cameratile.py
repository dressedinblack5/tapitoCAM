#!/usr/bin/env python3
"""Per-camera ONVIF PTZ controller — async connection, direct PTZ commands."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from onvif import ONVIFCamera
from PySide6.QtCore import QTimer


class PTZController:
    """PTZ controller for one camera.

    Initial ONVIF connection runs in a background ``threading.Thread``.
    After connection, PTZ commands (move, stop) are direct method calls
    in the calling thread — ONVIF-zeep uses plain HTTP/SOAP and is safe
    to call from the main thread.

    Parameters
    ----------
    on_error:
        Optional callback invoked with a human-readable error message
        whenever a PTZ command fails.  Called from the **same thread**
        that invoked the PTZ method (the main thread for GUI commands).
        Use ``functools.partial`` or a ``lambda`` to add context.
    """

    ONVIF_PORT = 2020

    def __init__(self, on_error: Callable[[str], None] | None = None):
        self.ptz = None
        self.profile_token = None
        self._thread: threading.Thread | None = None
        self._on_error = on_error
        self._has_zoom = False

    def _report_error(self, context: str, exc: Exception):
        """Log to stderr and forward to the optional callback."""
        msg = f"[PTZ] {context}: {exc}"
        print(msg, file=sys.stderr)
        if self._on_error is not None:
            self._on_error(msg)

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

            # Detect zoom support: ZoomLimits must exist and be non-None
            self._has_zoom = bool(
                configs
                and hasattr(configs[0], "ZoomLimits")
                and configs[0].ZoomLimits is not None
            )

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
                "Zoom": {
                    "x": 0.0,
                    "space": (
                        "http://www.onvif.org/ver10/tptz/"
                        "ZoomSpaces/VelocityGenericSpace"
                    ),
                },
            }
            self.ptz.ContinuousMove(request)
        except Exception as exc:
            self._report_error("ContinuousMove failed", exc)

    def continuous_zoom(self, velocity: float):
        if not self.ptz or not self.profile_token:
            return
        try:
            request = self.ptz.create_type("ContinuousMove")
            request.ProfileToken = self.profile_token
            request.Velocity = {
                "PanTilt": {
                    "x": 0.0,
                    "y": 0.0,
                    "space": (
                        "http://www.onvif.org/ver10/tptz/"
                        "PanTiltSpaces/VelocityGenericSpace"
                    ),
                },
                "Zoom": {
                    "x": float(velocity),
                    "space": (
                        "http://www.onvif.org/ver10/tptz/"
                        "ZoomSpaces/VelocityGenericSpace"
                    ),
                },
            }
            self.ptz.ContinuousMove(request)
        except Exception as exc:
            self._report_error("Zoom failed", exc)

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
            self._report_error("Stop failed", exc)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def get_presets(self) -> list[dict]:
        """Return presets as ``[{token, name}, ...]``. Empty list on error."""
        if not self.ptz or not self.profile_token:
            return []
        try:
            presets = self.ptz.GetPresets(self.profile_token)
            return [
                {"token": p.token, "name": getattr(p, "Name", str(p.token))}
                for p in presets
            ]
        except Exception:
            return []

    def goto_preset(self, preset_token: str):
        if not self.ptz or not self.profile_token:
            return
        try:
            request = self.ptz.create_type("GotoPreset")
            request.ProfileToken = self.profile_token
            request.PresetToken = preset_token
            self.ptz.GotoPreset(request)
        except Exception as exc:
            self._report_error("GotoPreset failed", exc)

    def set_preset(self, name: str) -> str | None:
        """Save current position as a preset. Returns the new preset token."""
        if not self.ptz or not self.profile_token:
            return None
        try:
            request = self.ptz.create_type("SetPreset")
            request.ProfileToken = self.profile_token
            request.PresetName = name
            result = self.ptz.SetPreset(request)
            if hasattr(result, "PresetToken"):
                return result.PresetToken
            # Some cameras return the preset token as a plain string
            if isinstance(result, str):
                return result
            return str(result) if result else None
        except Exception as exc:
            self._report_error("SetPreset failed", exc)
            return None

    def remove_preset(self, preset_token: str) -> bool:
        """Delete a preset. Returns True on success."""
        if not self.ptz or not self.profile_token:
            return False
        try:
            request = self.ptz.create_type("RemovePreset")
            request.ProfileToken = self.profile_token
            request.PresetToken = preset_token
            self.ptz.RemovePreset(request)
            return True
        except Exception as exc:
            self._report_error("RemovePreset failed", exc)
            return False

    @property
    def is_connected(self) -> bool:
        return self.ptz is not None

    @property
    def has_zoom(self) -> bool:
        """True if the camera exposes zoom limits in its PTZ configuration."""
        return self._has_zoom

    def cleanup(self):
        self.ptz = None
        self.profile_token = None
        self._thread = None

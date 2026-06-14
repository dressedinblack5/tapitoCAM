#!/usr/bin/env python3
"""Per-camera ONVIF PTZ controller — synchronous, no threads."""

class PTZController:
    """Synchronous ONVIF PTZ controller for one camera.

    All methods are blocking and meant to be called from the main (GUI)
    thread.  The initial connection may take 1–3 s; subsequent PTZ
    commands take milliseconds.
    """

    def __init__(self):
        self.ptz = None
        self.profile_token = None

    def connect(self, ip: str, user: str, password: str) -> bool:
        """Connect to the camera's ONVIF service.  Returns True on success."""
        try:
            from onvif import ONVIFCamera
            cam = ONVIFCamera(ip, 2020, user, password)
            self.ptz = cam.create_ptz_service()
            configs = self.ptz.GetConfigurations()
            self.profile_token = configs[0].token if configs else None
            return True
        except Exception:
            self.cleanup()
            return False

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

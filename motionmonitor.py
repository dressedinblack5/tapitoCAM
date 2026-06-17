#!/usr/bin/env python3
"""Motion detection via ONVIF PullPoint events. Uses onvif-zeep, keeps lxml for xs:any parsing."""

from __future__ import annotations

import datetime
import sys
import threading
import time

from lxml import etree
from onvif import ONVIFCamera
from PySide6.QtCore import QObject, Signal

_NS = {"tt": "http://www.onvif.org/ver10/schema"}

# Errors that mean the camera is definitively unreachable — stop retrying.
_FATAL_ERRORS = (
    "no route to host",
    "connection refused",
    "name or service not known",
    "network is unreachable",
)


class MotionMonitor(QObject):
    """Polls ONVIF PullPoint for motion events, emits signals.

    Signals emitted in the main thread:
      motion_changed(is_motion: bool)
      tamper_changed(is_tamper: bool)
      intrusion_changed(is_intrusion: bool)
      error_occurred(message: str)
    """

    motion_changed = Signal(bool)
    tamper_changed = Signal(bool)
    intrusion_changed = Signal(bool)
    error_occurred = Signal(str)

    POLL_TIMEOUT = 10
    _RENEW_BEFORE = 540  # seconds — re-subscribe before expiry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._cam: ONVIFCamera | None = None
        self._pullpoint = None
        self._sub_service = None
        self._last_motion: bool | None = None
        self._last_tamper: bool | None = None
        self._last_intrusion: bool | None = None
        self._thread: threading.Thread | None = None
        self._first_error_reported = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, ip: str, user: str, password: str):
        if self._active:
            return
        self._active = True
        self._first_error_reported = False

        try:
            self._cam = ONVIFCamera(ip, 2020, user, password, adjust_time=True)
        except Exception as exc:
            self._active = False
            self.error_occurred.emit(f"ONVIF init failed: {exc}")
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._active = False
        self._unsubscribe()
        self._cam = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _subscribe(self):
        """Create PullPoint subscription and bind services to its URL."""
        self._unsubscribe()

        evt = self._cam.create_events_service()
        sub = evt.CreatePullPointSubscription()
        sub_url = sub.SubscriptionReference.Address._value_1

        self._pullpoint = self._cam.create_onvif_service(
            "pullpoint", portType="PullPointSubscription"
        )
        self._pullpoint.ws_client.set_options(location=sub_url)

        self._sub_service = self._cam.create_onvif_service("subscription")
        self._sub_service.ws_client.set_options(location=sub_url)

        return time.monotonic()

    def _unsubscribe(self):
        if self._sub_service is None:
            return
        try:
            self._sub_service.Unsubscribe()
        except Exception:
            pass
        self._pullpoint = None
        self._sub_service = None

    def _run(self):
        sub_created = 0
        backoff = 1
        ip = ""
        try:
            # stash IP for error messages (ONVIFCamera doesn't expose it)
            ip = self._cam.xaddrs.get(
                "http://www.onvif.org/ver10/device/wsdl", ""
            ).split(":")[1].lstrip("/") or "?"
        except Exception:
            pass

        while self._active:
            try:
                if self._pullpoint is None or (
                    sub_created
                    and (time.monotonic() - sub_created) > self._RENEW_BEFORE
                ):
                    sub_created = self._subscribe()
                    backoff = 1

                self._poll()
            except Exception as exc:
                msg = str(exc).lower()
                fatal = any(e in msg for e in _FATAL_ERRORS)
                sub_limit = "unknown error: error" in msg or "fault: error" in msg

                if fatal:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        self.error_occurred.emit(f"Motion unavailable: {ip}")
                    self.stop()
                    return

                if sub_limit:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        print(f"[Motion] waiting for camera ({ip})...", file=sys.stderr)
                else:
                    print(f"[Motion] error ({ip}): {str(exc)[:120]}", file=sys.stderr)

                self._unsubscribe()
                for _ in range(min(backoff, 30)):
                    if not self._active:
                        return
                    time.sleep(1)
                backoff = min(backoff * 2, 60)

            if not self._active:
                return

    def _poll(self):
        if self._pullpoint is None:
            return

        msgs = self._pullpoint.PullMessages(
            Timeout=datetime.timedelta(seconds=self.POLL_TIMEOUT),
            MessageLimit=10,
        )
        for n in (msgs.NotificationMessage or []):
            msg_elem = n.Message._value_1
            if msg_elem is None:
                continue

            # Motion
            motion_el = msg_elem.find('.//tt:Data/tt:SimpleItem[@Name="IsMotion"]', _NS)
            if motion_el is not None:
                val = motion_el.get("Value", "false").lower() == "true"
                if self._last_motion != val:
                    self._last_motion = val
                    self.motion_changed.emit(val)
                continue

            # Tamper
            tamper_el = msg_elem.find('.//tt:Data/tt:SimpleItem[@Name="IsTamper"]', _NS)
            if tamper_el is not None:
                val = tamper_el.get("Value", "false").lower() == "true"
                if self._last_tamper != val:
                    self._last_tamper = val
                    self.tamper_changed.emit(val)
                continue

            # Intrusion
            for item in msg_elem.findall('.//tt:Data/tt:SimpleItem', _NS):
                name = item.get("Name", "")
                if "intrusion" in name.lower():
                    val = item.get("Value", "false").lower() == "true"
                    if self._last_intrusion != val:
                        self._last_intrusion = val
                        self.intrusion_changed.emit(val)
                    break

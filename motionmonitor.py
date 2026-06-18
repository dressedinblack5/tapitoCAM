#!/usr/bin/env python3
"""Motion detection via ONVIF PullPoint events."""

from __future__ import annotations

import datetime
import sys
import threading
import time

from lxml import etree
from onvif import ONVIFCamera
from PySide6.QtCore import QObject, Signal

_NS = {"tt": "http://www.onvif.org/ver10/schema"}

_FATAL_ERRORS = (
    "no route to host",
    "connection refused",
    "name or service not known",
    "network is unreachable",
)


class MotionMonitor(QObject):
    """Polls ONVIF PullPoint for motion events, emits motion_changed signal."""

    motion_changed = Signal(bool)
    error_occurred = Signal(str)

    POLL_TIMEOUT = 10
    _RENEW_BEFORE = 540

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._cam: ONVIFCamera | None = None
        self._pullpoint = None
        self._sub_service = None
        self._last_motion: bool | None = None
        self._thread: threading.Thread | None = None
        self._first_error_reported = False

    def start(self, ip: str, user: str, password: str):
        self.stop()  # kill any stale thread first
        self._active = True
        self._first_error_reported = False
        self._last_motion = None

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

    def _subscribe(self):
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

    def _stop_self(self):
        """Cleanup from within the worker thread (no thread join)."""
        self._active = False
        self._unsubscribe()
        self._cam = None

    def _run(self):
        sub_created = 0
        backoff = 1
        ip = ""
        try:
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

                if fatal:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        self.error_occurred.emit(f"Motion unavailable: {ip}")
                    self._stop_self()
                    return

                if "has no operation" in msg or "unexpected keyword argument" in msg:
                    self.error_occurred.emit("Motion not supported on this camera firmware")
                    self._stop_self()
                    return

                sub_limit = "unknown error: error" in msg
                if sub_limit:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        self.error_occurred.emit(
                            f"Motion: waiting for camera ({ip})..."
                        )
                else:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        print(f"[Motion] error ({ip}): {str(exc)[:120]}", file=sys.stderr)

                self._unsubscribe()
                for _ in range(min(backoff, 30)):
                    if not self._active:
                        return
                    time.sleep(1)
                backoff = min(backoff * 2, 60)

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

            el = msg_elem.find('.//tt:Data/tt:SimpleItem[@Name="IsMotion"]', _NS)
            if el is not None:
                val = el.get("Value", "false").lower() == "true"
                if self._last_motion != val:
                    self._last_motion = val
                    self.motion_changed.emit(val)

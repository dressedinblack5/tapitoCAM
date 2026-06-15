#!/usr/bin/env python3
"""Motion detection via ONVIF PullPoint events."""

from __future__ import annotations

import sys
import threading
import time

import requests
from lxml import etree
from PySide6.QtCore import QObject, Signal


_PULL_SOAP = """\
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <PullMessages xmlns="http://docs.oasis-open.org/wsn/b-2">
      <Timeout>PT{timeout}S</Timeout>
      <MessageLimit>10</MessageLimit>
    </PullMessages>
  </s:Body>
</s:Envelope>"""

_NS = {
    "wsnt": "http://docs.oasis-open.org/wsn/b-2",
    "tt": "http://www.onvif.org/ver10/schema",
}

# Errors that mean the camera is definitively unreachable — stop retrying.
_FATAL_ERRORS = (
    "No route to host",
    "Connection refused",
    "Name or service not known",
    "Network is unreachable",
)


class MotionMonitor(QObject):
    """Polls ONVIF PullPoint for motion events, emits signals.

    **Signals**

    ``motion_changed(is_motion: bool)``
        Fires when motion state changes (True = detected, False = cleared).
        Emitted in the **main** thread.

    ``error_occurred(message: str)``
        Fires when a fatal error occurs (camera unreachable, etc.).
        Emitted in the **main** thread.
    """

    motion_changed = Signal(bool)
    tamper_changed = Signal(bool)
    intrusion_changed = Signal(bool)
    error_occurred = Signal(str)

    POLL_TIMEOUT = 10
    _RENEW_BEFORE = 540  # seconds before subscription expiry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._sub_url: str | None = None
        self._session: requests.Session | None = None
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

        self._session = requests.Session()
        self._session.auth = requests.auth.HTTPDigestAuth(user, password)

        self._thread = threading.Thread(
            target=self._run, args=(ip, user, password), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._active = False
        if self._sub_url and self._session:
            try:
                self._unsubscribe()
            except Exception:
                pass
        self._sub_url = None
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run(self, ip: str, user: str, password: str):
        sub_created = 0
        backoff = 1

        while self._active:
            try:
                if self._sub_url is None or (
                    sub_created
                    and (time.monotonic() - sub_created) > self._RENEW_BEFORE
                ):
                    self._subscribe(ip, user, password)
                    sub_created = time.monotonic()
                    backoff = 1

                self._poll()
            except Exception as exc:
                msg = str(exc)
                fatal = any(e in msg for e in _FATAL_ERRORS)
                sub_limit = "Unknown error: error" in msg or "Fault: error" in msg

                if fatal:
                    # Camera unreachable — stop trying, inform user once
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        self.error_occurred.emit(f"Motion unavailable: {ip}")
                    self.stop()
                    return

                if sub_limit:
                    if not self._first_error_reported:
                        self._first_error_reported = True
                        print(
                            f"[Motion] waiting for camera ({ip})...",
                            file=sys.stderr,
                        )
                else:
                    print(
                        f"[Motion] error ({ip}): {msg[:120]}",
                        file=sys.stderr,
                    )

                self._sub_url = None
                for _ in range(min(backoff, 30)):
                    if not self._active:
                        return
                    time.sleep(1)
                backoff = min(backoff * 2, 60)

            if not self._active:
                return

    def _subscribe(self, ip: str, user: str, password: str):
        from onvif import ONVIFCamera

        cam = ONVIFCamera(ip, 2020, user, password)
        evt = cam.create_events_service()
        result = evt.CreatePullPointSubscription()

        ref = result.SubscriptionReference
        addr = None
        addr_attr = getattr(ref, "Address", None)
        if addr_attr is not None:
            raw = getattr(addr_attr, "_value_1", None)
            if isinstance(raw, str):
                addr = raw

        if not addr:
            raise RuntimeError("Failed to extract subscription address")

        self._sub_url = addr

    def _unsubscribe(self):
        if not self._sub_url or not self._session:
            return
        body = (
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
            '<s:Body>'
            '<Unsubscribe xmlns="http://docs.oasis-open.org/wsn/b-2"/>'
            '</s:Body></s:Envelope>'
        )
        self._session.post(
            self._sub_url,
            data=body,
            headers={"Content-Type": "application/soap+xml"},
            timeout=5,
        )

    def _poll(self):
        if not self._sub_url or not self._session:
            return

        body = _PULL_SOAP.format(timeout=self.POLL_TIMEOUT)
        r = self._session.post(
            self._sub_url,
            data=body,
            headers={"Content-Type": "application/soap+xml"},
            timeout=self.POLL_TIMEOUT + 5,
        )
        if r.status_code != 200:
            return

        root = etree.fromstring(r.content)
        for msg in root.findall(".//wsnt:NotificationMessage", _NS):
            # Motion
            motion_el = msg.find(
                './/tt:Data/tt:SimpleItem[@Name="IsMotion"]', _NS
            )
            if motion_el is not None:
                val = motion_el.get("Value", "false").lower() == "true"
                if self._last_motion != val:
                    self._last_motion = val
                    self.motion_changed.emit(val)
                continue

            # Tamper
            tamper_el = msg.find(
                './/tt:Data/tt:SimpleItem[@Name="IsTamper"]', _NS
            )
            if tamper_el is not None:
                val = tamper_el.get("Value", "false").lower() == "true"
                if self._last_tamper != val:
                    self._last_tamper = val
                    self.tamper_changed.emit(val)
                continue

            # Intrusion — look for any boolean SimpleItem
            for item in msg.findall('.//tt:Data/tt:SimpleItem', _NS):
                name = item.get("Name", "")
                if "Intrusion" in name or "intrusion" in name.lower():
                    val = item.get("Value", "false").lower() == "true"
                    if self._last_intrusion != val:
                        self._last_intrusion = val
                        self.intrusion_changed.emit(val)
                    break

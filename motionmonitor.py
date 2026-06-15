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


class MotionMonitor(QObject):
    """Polls ONVIF PullPoint for motion events, emits signals.

    **Signals**

    ``motion_changed(is_motion: bool)``
        Fires when motion state changes (True = detected, False = cleared).
        Emitted in the **main** thread.
    """

    motion_changed = Signal(bool)

    POLL_TIMEOUT = 10
    _RENEW_BEFORE = 540  # seconds before subscription expiry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._sub_url: str | None = None
        self._session: requests.Session | None = None
        self._last_motion: bool | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, ip: str, user: str, password: str):
        if self._active:
            return
        self._active = True

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
        backoff = 1  # start with 1 second, exponential up to 60

        while self._active:
            try:
                if self._sub_url is None or (
                    sub_created
                    and (time.monotonic() - sub_created) > self._RENEW_BEFORE
                ):
                    self._subscribe(ip, user, password)
                    sub_created = time.monotonic()
                    backoff = 1  # reset on success

                self._poll()
            except Exception as exc:
                msg = str(exc)
                if "Unknown error: error" in msg or "Fault: error" in msg:
                    # Camera limit: only one active subscription.
                    # Old session's subscription may still be alive.
                    print(
                        f"[MotionMonitor] subscription limit — "
                        f"retrying in {backoff}s",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[MotionMonitor] error: {exc}",
                        file=sys.stderr,
                    )
                self._sub_url = None
                for _ in range(backoff):
                    if not self._active:
                        return
                    time.sleep(1)
                backoff = min(backoff * 2, 60)

            # Periodically check liveness
            if not self._active:
                return

    def _subscribe(self, ip: str, user: str, password: str):
        from onvif import ONVIFCamera

        cam = ONVIFCamera(ip, 2020, user, password)
        evt = cam.create_events_service()
        result = evt.CreatePullPointSubscription()

        ref = result.SubscriptionReference
        addr = None
        raw = getattr(ref, "_value_1", None)
        if isinstance(raw, str):
            addr = raw
        elif hasattr(raw, "_value_1"):
            addr = raw._value_1
        elif isinstance(raw, dict):
            addr = raw.get("_value_1")

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
            motion_el = msg.find(
                './/tt:Data/tt:SimpleItem[@Name="IsMotion"]', _NS
            )
            if motion_el is None:
                continue
            is_motion = motion_el.get("Value", "false").lower() == "true"
            if is_motion != self._last_motion:
                self._last_motion = is_motion
                self.motion_changed.emit(is_motion)

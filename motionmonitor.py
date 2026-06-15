#!/usr/bin/env python3
"""Motion detection via ONVIF PullPoint events."""

from __future__ import annotations

import sys
import threading
import time

import requests
from lxml import etree
from PySide6.QtCore import QObject, Signal, QTimer


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

    # How long PullMessages blocks waiting for an event
    POLL_TIMEOUT = 10

    # How long to wait before reconnecting after a failure
    _RECONNECT_DELAY = 3

    # Subscription lifetime before renewal (camera default ~10 min)
    _RENEW_BEFORE = 540  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._sub_url: str | None = None
        self._session: requests.Session | None = None
        self._last_motion: bool | None = None
        self._poll_timer: QTimer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, ip: str, user: str, password: str):
        """Begin monitoring. Creates a PullPoint subscription and starts
        the background polling thread."""
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
        """Stop monitoring, tear down subscription, and wait for the
        background thread to finish."""
        self._active = False
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
        """Background thread entry point. Handles subscription lifecycle."""
        sub_created = 0  # monotonic subscription start time

        while self._active:
            try:
                if self._sub_url is None or (
                    sub_created
                    and (time.monotonic() - sub_created) > self._RENEW_BEFORE
                ):
                    self._subscribe(ip, user, password)
                    sub_created = time.monotonic()

                self._poll()
            except Exception as exc:
                print(
                    f"[MotionMonitor] error: {exc}",
                    file=sys.stderr,
                )
                self._sub_url = None
                # Wait before reconnecting
                for _ in range(self._RECONNECT_DELAY):
                    if not self._active:
                        return
                    time.sleep(1)

    def _subscribe(self, ip: str, user: str, password: str):
        """Create a PullPoint subscription and extract the endpoint URL."""
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

    def _poll(self):
        """Block up to POLL_TIMEOUT seconds waiting for events."""
        if not self._sub_url or not self._session:
            return

        body = _PULL_SOAP.format(timeout=self.POLL_TIMEOUT)
        r = self._session.post(
            self._sub_url,
            data=body,
            headers={"Content-Type": "application/soap+xml"},
            timeout=self.POLL_TIMEOUT + 5,
        )
        # Timeout / no events → empty response → wait for next poll
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

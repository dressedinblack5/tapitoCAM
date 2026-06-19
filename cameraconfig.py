#!/usr/bin/env python3
"""Configuration manager for multi-camera setup. Pure Python, no Qt."""

import base64
import contextlib
import ipaddress
import json
import os
from pathlib import Path

CONFIG_DIR_DEFAULT = Path.home() / ".config" / "tapitocam"
KEYRING_SERVICE = "tapitocam"


class ConfigManager:
    """Manages multiple camera configurations stored in a JSON file.

    The config file lives at ``~/.config/tapitocam/cameras.json`` and has the
    following schema::

        {
          "version": 1,
          "cameras": [
            {
              "id": 0,
              "name": "Camera 1",
              "username": "user",
              "password": "<base64-encoded>",
              "ip": "192.168.1.100",
              "quality": "hd"
            }
          ]
        }

    Passwords are **preferred** stored in the OS keyring via the ``keyring``
    library (GNOME Keyring, KDE Wallet, macOS Keychain, etc.).  The JSON file
    keeps a base64-encoded copy as a fallback when keyring is unavailable.
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else CONFIG_DIR_DEFAULT
        self.config_file = self.config_dir / "cameras.json"
        self._keyring = self._init_keyring()

    # ------------------------------------------------------------------
    # Keyring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _init_keyring():
        """Try to import keyring. Returns the module or None."""
        try:
            import keyring  # noqa: E402
            return keyring
        except ImportError:
            return None

    def _keyring_store(self, camera_id: int, password: str):
        """Store password in OS keyring. No-op if keyring is unavailable."""
        if self._keyring is None:
            return
        with contextlib.suppress(Exception):
            self._keyring.set_password(
                KEYRING_SERVICE, f"camera_{camera_id}", password
            )

    def _keyring_get(self, camera_id: int) -> str | None:
        """Retrieve password from OS keyring. Returns None on any failure."""
        if self._keyring is None:
            return None
        try:
            return self._keyring.get_password(
                KEYRING_SERVICE, f"camera_{camera_id}"
            )
        except Exception:
            return None

    def _keyring_delete(self, camera_id: int):
        """Remove password from OS keyring. No-op if keyring is unavailable."""
        if self._keyring is None:
            return
        with contextlib.suppress(Exception):
            self._keyring.delete_password(
                KEYRING_SERVICE, f"camera_{camera_id}"
            )

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load(self) -> list[dict]:
        """Read the camera list from the JSON config file.

        Returns an empty list if the file does not exist or is malformed.
        Passwords are resolved from the OS keyring when available,
        falling back to the base64-encoded field in JSON.
        """
        try:
            with open(self.config_file) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

        cameras = data.get("cameras", [])

        # Resolve passwords: keyring first, then base64 fallback
        for cam in cameras:
            cid = cam.get("id")
            if cid is None:
                continue
            keyring_pwd = self._keyring_get(cid)
            if keyring_pwd:
                cam["password"] = keyring_pwd
            else:
                # Decode the stored base64 password (backward compatible)
                encoded = cam.get("password", "")
                if encoded:
                    with contextlib.suppress(Exception):
                        cam["password"] = base64.b64decode(encoded).decode()
                # Migrate existing password into keyring for next time
                if self._keyring and cam.get("password"):
                    self._keyring_store(cid, cam["password"])

        return cameras

    def save(self, cameras: list[dict]) -> None:
        """Atomically write the camera list to the JSON config file.

        Passwords are stored in the OS keyring; a base64-encoded copy is
        kept in JSON for fallback when keyring is unavailable.
        """
        # Persist passwords to keyring
        for cam in cameras:
            cid = cam.get("id")
            pwd = cam.get("password")
            if cid is not None and pwd:
                self._keyring_store(cid, pwd)

        # Write JSON with base64-encoded passwords (fallback)
        stored = []
        for cam in cameras:
            copy = dict(cam)
            pwd = copy.get("password", "")
            if pwd:
                copy["password"] = base64.b64encode(pwd.encode()).decode()
            else:
                # Camera without password (shouldn't happen, but be safe)
                copy.pop("password", None)
            stored.append(copy)

        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"version": 1, "cameras": stored}, f, indent=2)
        os.replace(tmp, self.config_file)
        os.chmod(self.config_file, 0o600)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_camera(self, entry: dict) -> int:
        """Add a camera entry and return its auto-assigned id.

        The entry dict may contain any of the camera fields.  Required keys
        (username, password, ip) are validated via :meth:`validate_entry`.
        An empty or missing ``name`` defaults to ``"Camera {id}"``.
        """
        cameras = self.load()
        new_id = (max(c["id"] for c in cameras) + 1) if cameras else 0
        entry["id"] = new_id
        entry.setdefault("name", f"Camera {new_id}")
        if not entry.get("name", "").strip():
            entry["name"] = f"Camera {new_id}"
        entry.setdefault("quality", "hd")
        cameras.append(entry)
        self.save(cameras)
        return new_id

    def update_camera(self, camera_id: int, entry: dict) -> bool:
        """Update fields of an existing camera.  Returns True on success."""
        cameras = self.load()
        for i, cam in enumerate(cameras):
            if cam["id"] == camera_id:
                cameras[i].update(entry)
                cameras[i]["id"] = camera_id  # never change the id
                self.save(cameras)
                return True
        return False

    def remove_camera(self, camera_id: int) -> bool:
        """Remove a camera by id.  Returns True if found and removed."""
        cameras = self.load()
        before = len(cameras)
        cameras = [c for c in cameras if c["id"] != camera_id]
        if len(cameras) < before:
            self.save(cameras)
            self._keyring_delete(camera_id)
            return True
        return False

    def reorder_cameras(self, from_index: int, to_index: int) -> bool:
        cameras = self.load()
        if not (0 <= from_index < len(cameras) and 0 <= to_index < len(cameras)):
            return False
        item = cameras.pop(from_index)
        cameras.insert(to_index, item)
        for i, cam in enumerate(cameras):
            cam["id"] = i
        self.save(cameras)
        return True

    def get_camera(self, camera_id: int) -> dict | None:
        """Return a single camera dict or None."""
        cameras = self.load()
        for cam in cameras:
            if cam["id"] == camera_id:
                return cam
        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Return True if *ip* is a valid IPv4 address."""
        try:
            ipaddress.IPv4Address(ip)
            return True
        except (ipaddress.AddressValueError, ValueError):
            return False

    @staticmethod
    def validate_entry(entry: dict) -> tuple[bool, str]:
        """Validate a camera entry dict.

        Returns ``(True, "")`` on success or ``(False, "reason")`` on
        failure.
        """
        missing = [k for k in ("username", "password", "ip") if not entry.get(k)]
        if missing:
            return False, f"Missing fields: {', '.join(missing)}"
        try:
            ipaddress.IPv4Address(entry["ip"])
        except (ipaddress.AddressValueError, ValueError):
            return False, f"Invalid IP address: {entry['ip']}"
        return True, ""

#!/usr/bin/env python3
"""Configuration manager for multi-camera setup. Pure Python, no Qt."""

import base64
import json
import os
from pathlib import Path

from utils import validate_ip


CONFIG_DIR_DEFAULT = Path.home() / ".config" / "tapitocam"


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

    Passwords are stored base64-encoded using the same scheme as the original
    ``.tapitocam.env`` file for backward compatibility.
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else CONFIG_DIR_DEFAULT
        self.config_file = self.config_dir / "cameras.json"

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load(self) -> list[dict]:
        """Read the camera list from the JSON config file.

        Returns an empty list if the file does not exist or is malformed.
        """
        try:
            with open(self.config_file) as f:
                data = json.load(f)
            return data.get("cameras", [])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def save(self, cameras: list[dict]) -> None:
        """Atomically write the camera list to the JSON config file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"version": 1, "cameras": cameras}, f, indent=2)
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
            return True
        return False

    def get_camera(self, camera_id: int) -> dict | None:
        """Return a single camera dict or None."""
        cameras = self.load()
        for cam in cameras:
            if cam["id"] == camera_id:
                return cam
        return None

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    #: Name of the legacy single-camera config file.
    OLD_ENV_NAME = ".tapitocam.env"

    def migrate_from_env(self) -> bool:
        """Migrate the old single-camera ``.tapitocam.env`` to the new JSON
        format.

        Reads the old file, converts it to a single-entry JSON config, and
        deletes the old file.  Returns True when a migration actually
        happened, False if there was no old file to migrate.
        """
        old = self.config_dir / self.OLD_ENV_NAME
        if not old.exists():
            return False

        entry: dict[str, str | int] = {}
        with open(old) as f:
            for line in f:
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                val = value.strip()
                if key == "TAPO_USER":
                    entry["username"] = val
                elif key == "TAPO_PASS":
                    try:
                        entry["password"] = base64.b64decode(val).decode()
                    except Exception:
                        entry["password"] = val
                elif key == "TAPO_IP":
                    entry["ip"] = val

        if entry.get("username") and entry.get("password") and entry.get("ip"):
            self.add_camera(entry)

        old.unlink()
        return True

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Return True if *ip* is a valid IPv4 address."""
        return validate_ip(ip)

    @staticmethod
    def validate_entry(entry: dict) -> tuple[bool, str]:
        """Validate a camera entry dict.

        Returns ``(True, "")`` on success or ``(False, "reason")`` on
        failure.
        """
        missing = [k for k in ("username", "password", "ip") if not entry.get(k)]
        if missing:
            return False, f"Missing fields: {', '.join(missing)}"
        if not validate_ip(entry["ip"]):
            return False, f"Invalid IP address: {entry['ip']}"
        return True, ""

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    @staticmethod
    def encode_password(password: str) -> str:
        """Base64-encode a password (match existing scheme)."""
        return base64.b64encode(password.encode()).decode()

    @staticmethod
    def decode_password(encoded: str) -> str:
        """Base64-decode a password."""
        return base64.b64decode(encoded).decode()

#!/usr/bin/env python3
"""Unit tests for the cameraconfig module."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from cameraconfig import ConfigManager


class TestConfigManager(unittest.TestCase):
    """Test CRUD operations, validation, and migration."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self._tmpdir.name)
        self.cfg = ConfigManager(self.config_dir)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def test_load_empty_when_no_file(self):
        """Loading with no config file returns an empty list."""
        cameras = self.cfg.load()
        self.assertEqual(cameras, [])

    def test_save_and_load_roundtrip(self):
        """Save then load returns identical data."""
        expected = [
            {"id": 0, "name": "Cam A", "username": "u1", "password": "p1",
             "ip": "10.0.0.1", "quality": "hd"},
        ]
        self.cfg.save(expected)
        result = self.cfg.load()
        self.assertEqual(result, expected)

    def test_load_malformed_json_returns_empty(self):
        """Malformed JSON file results in an empty list (graceful)."""
        self.cfg.config_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.config_file.write_text("{bad json")
        cameras = self.cfg.load()
        self.assertEqual(cameras, [])

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def test_add_camera_assigns_ids(self):
        """add_camera assigns sequential ids starting from 0."""
        id0 = self.cfg.add_camera(
            {"username": "u", "password": "p", "ip": "10.0.0.1"}
        )
        self.assertEqual(id0, 0)

        id1 = self.cfg.add_camera(
            {"username": "u2", "password": "p2", "ip": "10.0.0.2"}
        )
        self.assertEqual(id1, 1)

    def test_add_camera_defaults_name(self):
        """Blank name defaults to 'Camera {id}'."""
        cid = self.cfg.add_camera(
            {"username": "u", "password": "p", "ip": "10.0.0.1"}
        )
        cam = self.cfg.get_camera(cid)
        self.assertEqual(cam["name"], f"Camera {cid}")

    def test_add_camera_default_quality(self):
        """Default quality is 'hd'."""
        cid = self.cfg.add_camera(
            {"username": "u", "password": "p", "ip": "10.0.0.1"}
        )
        cam = self.cfg.get_camera(cid)
        self.assertEqual(cam["quality"], "hd")

    def test_add_with_explicit_name(self):
        """Explicit name is preserved."""
        cid = self.cfg.add_camera(
            {"username": "u", "password": "p", "ip": "10.0.0.1",
             "name": "Front Door"}
        )
        cam = self.cfg.get_camera(cid)
        self.assertEqual(cam["name"], "Front Door")

    def test_update_camera(self):
        """update_camera modifies fields and preserves id."""
        cid = self.cfg.add_camera(
            {"username": "u", "password": "p", "ip": "10.0.0.1"}
        )
        ok = self.cfg.update_camera(cid, {"name": "Updated", "ip": "10.0.0.99"})
        self.assertTrue(ok)
        cam = self.cfg.get_camera(cid)
        self.assertEqual(cam["name"], "Updated")
        self.assertEqual(cam["ip"], "10.0.0.99")
        self.assertEqual(cam["id"], cid)  # id unchanged

    def test_update_nonexistent_returns_false(self):
        """Updating a non-existent camera returns False."""
        ok = self.cfg.update_camera(999, {"name": "nope"})
        self.assertFalse(ok)

    def test_remove_camera(self):
        """remove_camera removes by id and does not affect others."""
        id0 = self.cfg.add_camera(
            {"username": "u1", "password": "p1", "ip": "10.0.0.1"}
        )
        id1 = self.cfg.add_camera(
            {"username": "u2", "password": "p2", "ip": "10.0.0.2"}
        )
        ok = self.cfg.remove_camera(id0)
        self.assertTrue(ok)
        self.assertIsNone(self.cfg.get_camera(id0))
        self.assertIsNotNone(self.cfg.get_camera(id1))
        self.assertEqual(len(self.cfg.load()), 1)

    def test_remove_nonexistent_returns_false(self):
        """Removing a non-existent camera returns False."""
        ok = self.cfg.remove_camera(999)
        self.assertFalse(ok)

    def test_get_camera_returns_none_for_missing(self):
        """get_camera returns None for unknown id."""
        cam = self.cfg.get_camera(42)
        self.assertIsNone(cam)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_validate_ip_valid(self):
        self.assertTrue(ConfigManager.validate_ip("192.168.1.1"))
        self.assertTrue(ConfigManager.validate_ip("0.0.0.0"))
        self.assertTrue(ConfigManager.validate_ip("255.255.255.255"))

    def test_validate_ip_invalid(self):
        self.assertFalse(ConfigManager.validate_ip("256.1.1.1"))
        self.assertFalse(ConfigManager.validate_ip("1.2.3"))
        self.assertFalse(ConfigManager.validate_ip("abc.def.ghi.jkl"))
        self.assertFalse(ConfigManager.validate_ip(""))
        self.assertFalse(ConfigManager.validate_ip("10.0.0.1.5"))

    def test_validate_entry_valid(self):
        ok, msg = ConfigManager.validate_entry(
            {"username": "u", "password": "p", "ip": "10.0.0.1"}
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_validate_entry_missing_fields(self):
        ok, msg = ConfigManager.validate_entry(
            {"username": "", "password": "p", "ip": "10.0.0.1"}
        )
        self.assertFalse(ok)
        self.assertIn("Missing", msg)

    def test_validate_entry_bad_ip(self):
        ok, msg = ConfigManager.validate_entry(
            {"username": "u", "password": "p", "ip": "999.999.999.999"}
        )
        self.assertFalse(ok)
        self.assertIn("Invalid IP", msg)

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    def test_password_roundtrip(self):
        original = "My$ecureP@ss!"
        encoded = ConfigManager.encode_password(original)
        decoded = ConfigManager.decode_password(encoded)
        self.assertEqual(decoded, original)

    def test_password_matches_existing_scheme(self):
        """Ensure the encoding matches the existing scheme from
        ``tapitocam_gui.py``:
            ``base64.b64encode(password.encode()).decode()``
        """
        password = "test123"
        expected = base64.b64encode(password.encode()).decode()
        self.assertEqual(ConfigManager.encode_password(password), expected)

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def test_migrate_from_env_no_file(self):
        """migrate_from_env returns False when no old env file exists."""
        result = self.cfg.migrate_from_env()
        self.assertFalse(result)

    def test_migrate_from_env_creates_camera(self):
        """migrate_from_env reads the old env and creates a camera entry."""
        env_file = self.config_dir / ".tapitocam.env"
        env_file.write_text(
            "TAPO_USER=admin\n"
            "TAPO_PASS={}\n"
            "TAPO_IP=192.168.1.100\n".format(
                base64.b64encode(b"secret").decode()
            )
        )

        result = self.cfg.migrate_from_env()
        self.assertTrue(result)
        self.assertFalse(env_file.exists())  # old file deleted

        cameras = self.cfg.load()
        self.assertEqual(len(cameras), 1)
        self.assertEqual(cameras[0]["username"], "admin")
        self.assertEqual(cameras[0]["password"], "secret")
        self.assertEqual(cameras[0]["ip"], "192.168.1.100")


if __name__ == "__main__":
    unittest.main()

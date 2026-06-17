#!/usr/bin/env python3
"""Tests for the shared utils module."""

import os
import unittest

from utils import (
    get_mpv_playlist_command,
    is_auth_error,
    is_mpv_connection_error,
    sanitize_onvif_error,
    write_rtsp_playlist,
)


class TestAuthError(unittest.TestCase):
    """Test is_auth_error pattern matching."""

    def test_auth_401(self):
        self.assertTrue(is_auth_error("RTSP error: 401 Unauthorized"))

    def test_auth_401_naked(self):
        self.assertTrue(is_auth_error("401"))

    def test_auth_unauthorized(self):
        self.assertTrue(is_auth_error("Unauthorized"))

    def test_auth_authentication_failed(self):
        self.assertTrue(is_auth_error("Authentication failed"))

    def test_auth_invalid_credentials(self):
        self.assertTrue(is_auth_error("Invalid credentials"))

    def test_auth_access_denied(self):
        self.assertTrue(is_auth_error("access denied"))

    def test_auth_login_failed(self):
        self.assertTrue(is_auth_error("login failed"))

    def test_auth_wrong_password(self):
        self.assertTrue(is_auth_error("wrong password"))

    def test_auth_not_matching_normal_text(self):
        self.assertFalse(is_auth_error("Connection timed out"))

    def test_auth_empty_string(self):
        self.assertFalse(is_auth_error(""))

    def test_auth_case_insensitive(self):
        self.assertTrue(is_auth_error("ACCESS DENIED"))


class TestMpvConnectionError(unittest.TestCase):
    """Test is_mpv_connection_error pattern matching."""

    def test_connection_refused(self):
        self.assertTrue(is_mpv_connection_error("Connection refused"))

    def test_no_route(self):
        self.assertTrue(is_mpv_connection_error("No route to host"))

    def test_not_matching_auth(self):
        self.assertFalse(is_mpv_connection_error("401 Unauthorized"))

    def test_empty_string(self):
        self.assertFalse(is_mpv_connection_error(""))


# ---------------------------------------------------------------------------
# Playlist helpers
# ---------------------------------------------------------------------------


class TestPlaylistHelpers(unittest.TestCase):
    """Test RTSP playlist file creation and mpv command building."""

    def test_write_rtsp_playlist_creates_file(self):
        path = write_rtsp_playlist("rtsp://user:pass@1.2.3.4/stream1")
        try:
            self.assertTrue(os.path.isfile(path))
            with open(path) as f:
                content = f.read()
            self.assertIn("rtsp://user:pass@1.2.3.4/stream1", content)
        finally:
            os.unlink(path)

    def test_write_rtsp_playlist_permissions(self):
        path = write_rtsp_playlist("rtsp://user:pass@1.2.3.4/stream1")
        try:
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)
        finally:
            os.unlink(path)

    def test_get_mpv_playlist_command_includes_playlist_flag(self):
        cmd = get_mpv_playlist_command("Front Door", "/tmp/test.m3u")
        self.assertEqual(cmd[0], "mpv")
        self.assertIn("--playlist=/tmp/test.m3u", cmd)
        # Must NOT contain the URL directly
        self.assertNotIn("rtsp://", " ".join(cmd))

    def test_get_mpv_playlist_command_title(self):
        cmd = get_mpv_playlist_command("Camera 1", "/tmp/test.m3u")
        title_arg = next(a for a in cmd if a.startswith("--title="))
        self.assertIn("tapitoCAM", title_arg)
        self.assertIn("Camera 1", title_arg)


# ---------------------------------------------------------------------------
# ONVIF error sanitizer
# ---------------------------------------------------------------------------


class TestSanitizeOnvifError(unittest.TestCase):
    """Test sanitize_onvif_error strips credential-like patterns."""

    def test_strips_url_credentials(self):
        msg = "Fault: http://admin:secret@192.168.1.100:2020/onvif/device_service"
        sanitized = sanitize_onvif_error(msg)
        self.assertNotIn("admin", sanitized)
        self.assertNotIn("secret", sanitized)
        self.assertIn("***:***@", sanitized)

    def test_strips_password_param(self):
        msg = "HTTPError: password=mysecret"
        sanitized = sanitize_onvif_error(msg)
        self.assertNotIn("mysecret", sanitized)
        self.assertIn("password=***", sanitized)

    def test_strips_passwd_param(self):
        msg = "Error: passwd=secret123"
        sanitized = sanitize_onvif_error(msg)
        self.assertIn("passwd=***", sanitized)

    def test_preserves_safe_text(self):
        msg = "Connection refused"
        sanitized = sanitize_onvif_error(msg)
        self.assertEqual(sanitized, "Connection refused")

    def test_truncates_long_messages(self):
        msg = "x" * 200
        sanitized = sanitize_onvif_error(msg)
        self.assertLessEqual(len(sanitized), 150)

    def test_replaces_newlines(self):
        msg = "Error:\nline1\nline2"
        sanitized = sanitize_onvif_error(msg)
        self.assertNotIn("\n", sanitized)

    def test_password_case_insensitive(self):
        msg = "error: PASSWORD=hunter2"
        sanitized = sanitize_onvif_error(msg)
        self.assertNotIn("hunter2", sanitized)


if __name__ == "__main__":
    unittest.main()
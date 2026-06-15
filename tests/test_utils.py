#!/usr/bin/env python3
"""Tests for the shared utils module."""

import unittest

from utils import is_auth_error, is_mpv_connection_error, validate_ip


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


class TestValidateIP(unittest.TestCase):
    """Test validate_ip function."""

    def test_valid_ip(self):
        self.assertTrue(validate_ip("192.168.1.1"))

    def test_invalid_ip_octet(self):
        self.assertFalse(validate_ip("256.1.1.1"))

    def test_invalid_ip_format(self):
        self.assertFalse(validate_ip("not.an.ip"))


if __name__ == "__main__":
    unittest.main()
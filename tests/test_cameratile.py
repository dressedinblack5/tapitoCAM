#!/usr/bin/env python3
"""Tests for the PTZ controller module."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication

from cameratile import PTZController


class TestPTZController(unittest.TestCase):
    """Test PTZ controller with mocked ONVIF."""

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.ctrl = PTZController()

    # --- State ---

    def test_is_connected_false_initially(self):
        self.assertFalse(self.ctrl.is_connected)

    def test_cleanup_resets_state(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.cleanup()
        self.assertIsNone(self.ctrl.ptz)
        self.assertIsNone(self.ctrl.profile_token)

    def test_cleanup_idempotent(self):
        self.ctrl.cleanup()
        self.ctrl.cleanup()  # should not raise

    # --- continuous_move ---

    def test_continuous_move_creates_request(self):
        mock_request = MagicMock()
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "test-token"
        self.ctrl.ptz.create_type.return_value = mock_request

        self.ctrl.continuous_move(0.3, 0.0)

        self.ctrl.ptz.create_type.assert_called_once_with("ContinuousMove")
        self.assertEqual(mock_request.ProfileToken, "test-token")
        self.assertAlmostEqual(mock_request.Velocity["PanTilt"]["x"], 0.3)
        self.assertAlmostEqual(mock_request.Velocity["PanTilt"]["y"], 0.0)
        self.ctrl.ptz.ContinuousMove.assert_called_once_with(mock_request)

    def test_continuous_move_noop_when_not_connected(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = None
        self.ctrl.continuous_move(0.3, 0.0)
        self.ctrl.ptz.create_type.assert_not_called()

    def test_continuous_move_noop_when_no_ptz(self):
        self.ctrl.continuous_move(0.3, 0.0)

    # --- stop ---

    def test_stop_creates_request(self):
        mock_request = MagicMock()
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "test-token"
        self.ctrl.ptz.create_type.return_value = mock_request

        self.ctrl.stop()

        self.ctrl.ptz.create_type.assert_called_once_with("Stop")
        self.assertEqual(mock_request.ProfileToken, "test-token")
        self.assertTrue(mock_request.PanTilt)
        self.assertTrue(mock_request.Zoom)
        self.ctrl.ptz.Stop.assert_called_once_with(mock_request)

    def test_stop_noop_when_not_connected(self):
        self.ctrl.stop()

    # --- async connect ---

    @patch("cameratile.QTimer")
    @patch("cameratile.threading.Thread")
    def test_connect_async_starts_thread(self, mock_thread, mock_timer):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        callback = MagicMock()
        self.ctrl.connect_async("10.0.0.1", "user", "pass", callback)
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
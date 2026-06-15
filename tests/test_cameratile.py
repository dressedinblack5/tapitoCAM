#!/usr/bin/env python3
"""Tests for the PTZ controller module."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication

from cameratile import PTZController, PTZWorker


class TestPTZWorker(unittest.TestCase):
    """Test PTZWorker core logic with mocked ONVIF."""

    @classmethod
    def setUpClass(cls):
        if not QCoreApplication.instance():
            cls.app = QCoreApplication(sys.argv)
        else:
            cls.app = QCoreApplication.instance()

    def setUp(self):
        self.worker = PTZWorker("10.0.0.1", "user", "pass")
        self.worker.ptz = MagicMock()
        self.worker.profile_token = "test-token"

    def test_continuous_move_creates_request(self):
        """continuous_move creates the expected ONVIF request."""
        mock_request = MagicMock()
        self.worker.ptz.create_type.return_value = mock_request

        self.worker.continuous_move(0.3, 0.0)

        self.worker.ptz.create_type.assert_called_once_with("ContinuousMove")
        self.assertEqual(mock_request.ProfileToken, "test-token")
        self.assertAlmostEqual(mock_request.Velocity["PanTilt"]["x"], 0.3)
        self.assertAlmostEqual(mock_request.Velocity["PanTilt"]["y"], 0.0)
        self.worker.ptz.ContinuousMove.assert_called_once_with(mock_request)

    def test_continuous_move_no_profile(self):
        """continuous_move is a no-op when not connected."""
        worker = PTZWorker("10.0.0.1", "u", "p")
        worker.ptz = MagicMock()
        worker.profile_token = None

        worker.continuous_move(0.3, 0.0)
        worker.ptz.create_type.assert_not_called()

    def test_stop_creates_request(self):
        """stop creates the expected Stop request."""
        mock_request = MagicMock()
        self.worker.ptz.create_type.return_value = mock_request

        self.worker.stop()

        self.worker.ptz.create_type.assert_called_once_with("Stop")
        self.assertEqual(mock_request.ProfileToken, "test-token")
        self.assertTrue(mock_request.PanTilt)
        self.assertTrue(mock_request.Zoom)
        self.worker.ptz.Stop.assert_called_once_with(mock_request)

    def test_stop_no_profile(self):
        """stop is a no-op when not connected."""
        worker = PTZWorker("10.0.0.1", "u", "p")
        worker.ptz = MagicMock()
        worker.profile_token = None

        worker.stop()
        worker.ptz.create_type.assert_not_called()

    def test_is_connected_true(self):
        """is_connected returns True when ptz is set."""
        self.assertTrue(self.worker.is_connected)

    def test_is_connected_false(self):
        """is_connected returns False when ptz is None."""
        worker = PTZWorker("10.0.0.1", "u", "p")
        self.assertFalse(worker.is_connected)

    def test_cleanup_resets_state(self):
        """cleanup clears ptz and profile_token."""
        self.worker.cleanup()
        self.assertIsNone(self.worker.ptz)
        self.assertIsNone(self.worker.profile_token)

    @patch("builtins.__import__")
    def test_run_success(self, mock_import):
        """run connects to ONVIF and emits connected(True)."""
        # Mock onvif module
        mock_onvif_module = MagicMock()
        mock_onvif_cam = MagicMock()
        mock_onvif_module.ONVIFCamera.return_value = mock_onvif_cam
        mock_ptz = MagicMock()
        mock_config = MagicMock()
        mock_config.token = "config-token"
        mock_ptz.GetConfigurations.return_value = [mock_config]
        mock_onvif_cam.create_ptz_service.return_value = mock_ptz

        def side_effect(name, *args, **kwargs):
            if name == "onvif":
                return mock_onvif_module
            return __import__(name, *args[1:], **kwargs)

        mock_import.side_effect = side_effect

        signals = []
        self.worker.connected.connect(lambda s, e: signals.append((s, e)))

        self.worker.run()

        self.assertEqual(signals, [(True, "")])
        self.assertEqual(self.worker.ptz, mock_ptz)
        self.assertEqual(self.worker.profile_token, "config-token")

    @patch("builtins.__import__")
    def test_run_failure(self, mock_import):
        """run emits connected(False, error) on exception."""

        def side_effect(name, *args, **kwargs):
            if name == "onvif":
                raise Exception("Connection refused")
            return __import__(name, *args[1:], **kwargs)

        mock_import.side_effect = side_effect

        signals = []
        self.worker.connected.connect(lambda s, e: signals.append((s, e)))

        self.worker.run()

        self.assertEqual(len(signals), 1)
        self.assertFalse(signals[0][0])
        self.assertIn("Connection refused", signals[0][1])


class TestPTZController(unittest.TestCase):
    """Test PTZController threading wrapper."""

    @classmethod
    def setUpClass(cls):
        if not QCoreApplication.instance():
            cls.app = QCoreApplication(sys.argv)
        else:
            cls.app = QCoreApplication.instance()

    def setUp(self):
        self.controller = PTZController()

    def test_is_connected_false_initially(self):
        """is_connected returns False before any connection."""
        self.assertFalse(self.controller.is_connected)

    def test_cleanup_no_thread(self):
        """cleanup is safe when no thread is running."""
        self.controller.cleanup()
        self.assertIsNone(self.controller._worker)

    def test_continuous_move_no_worker(self):
        """continuous_move is safe when no worker exists."""
        # Should not crash
        self.controller.continuous_move(0.3, 0.0)

    def test_stop_no_worker(self):
        """stop is safe when no worker exists."""
        # Should not crash
        self.controller.stop()


if __name__ == "__main__":
    unittest.main()

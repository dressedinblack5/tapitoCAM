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

    def test_continuous_move_prints_exception(self):
        """Exception in ContinuousMove is printed to stderr, not swallowed."""
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.ContinuousMove.side_effect = RuntimeError("boom")

        with patch("sys.stderr") as mock_stderr:
            self.ctrl.continuous_move(0.3, 0.0)
            written = "".join(
                c.args[0] for c in mock_stderr.write.call_args_list
            )
            self.assertIn("[PTZ]", written)
            self.assertIn("boom", written)

    def test_continuous_move_does_not_raise(self):
        """Exception in ContinuousMove is caught, not propagated."""
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.ContinuousMove.side_effect = RuntimeError("boom")
        self.ctrl.continuous_move(0.3, 0.0)  # must not raise

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

    def test_stop_prints_exception(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.Stop.side_effect = RuntimeError("stop-boom")

        with patch("sys.stderr") as mock_stderr:
            self.ctrl.stop()
            written = "".join(
                c.args[0] for c in mock_stderr.write.call_args_list
            )
            self.assertIn("[PTZ]", written)
            self.assertIn("stop-boom", written)

    def test_stop_does_not_raise(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.Stop.side_effect = RuntimeError("boom")
        self.ctrl.stop()  # must not raise

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

    @patch("cameratile.QTimer")
    @patch("cameratile.ONVIFCamera")
    def test_connect_async_uses_media_profile_token(self, mock_cam_class, mock_timer):
        """connect_async gets the token from GetProfiles, not GetConfigurations."""
        mock_media = MagicMock()
        mock_profile = MagicMock()
        mock_profile.token = "media-token-123"
        mock_media.GetProfiles.return_value = [mock_profile]

        mock_ptz = MagicMock()
        mock_config = MagicMock()
        mock_config.token = "cfg-token-456"
        mock_ptz.GetConfigurations.return_value = [mock_config]

        mock_cam = MagicMock()
        mock_cam.create_media_service.return_value = mock_media
        mock_cam.create_ptz_service.return_value = mock_ptz
        mock_cam_class.return_value = mock_cam

        callback = MagicMock()
        self.ctrl._run_connect("10.0.0.1", "u", "p", callback)

        self.assertEqual(self.ctrl.profile_token, "media-token-123")
        self.assertEqual(self.ctrl.ptz, mock_ptz)

    @patch("cameratile.QTimer")
    @patch("cameratile.ONVIFCamera")
    def test_connect_async_falls_back_to_ptz_config_token(self, mock_cam_class, mock_timer):
        """When GetProfiles returns empty, fall back to GetConfigurations token."""
        mock_media = MagicMock()
        mock_media.GetProfiles.return_value = []

        mock_ptz = MagicMock()
        mock_config = MagicMock()
        mock_config.token = "cfg-token-789"
        mock_ptz.GetConfigurations.return_value = [mock_config]

        mock_cam = MagicMock()
        mock_cam.create_media_service.return_value = mock_media
        mock_cam.create_ptz_service.return_value = mock_ptz
        mock_cam_class.return_value = mock_cam

        callback = MagicMock()
        self.ctrl._run_connect("10.0.0.1", "u", "p", callback)

        self.assertEqual(self.ctrl.profile_token, "cfg-token-789")

    @patch("cameratile.QTimer")
    @patch("cameratile.ONVIFCamera")
    def test_connect_async_no_profiles_no_configs(self, mock_cam_class, mock_timer):
        """When both profiles and configs are empty, callback fires with False."""
        mock_media = MagicMock()
        mock_media.GetProfiles.return_value = []

        mock_ptz = MagicMock()
        mock_ptz.GetConfigurations.return_value = []

        mock_cam = MagicMock()
        mock_cam.create_media_service.return_value = mock_media
        mock_cam.create_ptz_service.return_value = mock_ptz
        mock_cam_class.return_value = mock_cam

        callback = MagicMock()
        self.ctrl._run_connect("10.0.0.1", "u", "p", callback)

        # QTimer.singleShot(0, lambda: callback(False, ...))
        args, _ = mock_timer.singleShot.call_args
        args[1]()
        callback.assert_called_once_with(
            False, "No media profiles or PTZ configurations found"
        )


    # --- continuous_zoom ---

    def test_continuous_zoom_creates_request(self):
        mock_request = MagicMock()
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "test-token"
        self.ctrl.ptz.create_type.return_value = mock_request

        self.ctrl.continuous_move(zoom=0.3)

        self.ctrl.ptz.create_type.assert_called_once_with("ContinuousMove")
        self.assertEqual(mock_request.ProfileToken, "test-token")
        self.assertAlmostEqual(mock_request.Velocity["Zoom"]["x"], 0.3)
        self.assertEqual(mock_request.Velocity["PanTilt"]["x"], 0.0)
        self.assertEqual(mock_request.Velocity["PanTilt"]["y"], 0.0)
        self.ctrl.ptz.ContinuousMove.assert_called_once_with(mock_request)

    def test_continuous_zoom_noop_when_not_connected(self):
        self.ctrl.continuous_move(zoom=0.3)  # must not raise

    # --- presets ---

    def test_get_presets_returns_list(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        mock_preset = MagicMock()
        mock_preset.token = "preset1"
        mock_preset.Name = "View 1"
        self.ctrl.ptz.GetPresets.return_value = [mock_preset]

        result = self.ctrl.get_presets()
        self.ctrl.ptz.GetPresets.assert_called_once_with("tok")
        self.assertEqual(result, [{"token": "preset1", "name": "View 1"}])

    def test_get_presets_empty_when_not_connected(self):
        result = self.ctrl.get_presets()
        self.assertEqual(result, [])

    def test_get_presets_handles_exception(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.GetPresets.side_effect = RuntimeError("boom")
        result = self.ctrl.get_presets()
        self.assertEqual(result, [])

    def test_goto_preset_creates_request(self):
        mock_request = MagicMock()
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.create_type.return_value = mock_request

        self.ctrl.goto_preset("preset1")
        self.ctrl.ptz.create_type.assert_called_once_with("GotoPreset")
        self.assertEqual(mock_request.ProfileToken, "tok")
        self.assertEqual(mock_request.PresetToken, "preset1")
        self.ctrl.ptz.GotoPreset.assert_called_once_with(mock_request)

    def test_goto_preset_noop_when_not_connected(self):
        self.ctrl.goto_preset("preset1")  # must not raise

    def test_set_preset_creates_request(self):
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.PresetToken = "newtoken"
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.create_type.return_value = mock_request
        self.ctrl.ptz.SetPreset.return_value = mock_response

        result = self.ctrl.set_preset("My Preset")
        self.ctrl.ptz.create_type.assert_called_once_with("SetPreset")
        self.assertEqual(mock_request.ProfileToken, "tok")
        self.assertEqual(mock_request.PresetName, "My Preset")
        self.ctrl.ptz.SetPreset.assert_called_once_with(mock_request)
        self.assertEqual(result, "newtoken")

    def test_set_preset_noop_when_not_connected(self):
        result = self.ctrl.set_preset("test")
        self.assertIsNone(result)

    def test_set_preset_handles_exception(self):
        self.ctrl.ptz = MagicMock()
        self.ctrl.profile_token = "tok"
        self.ctrl.ptz.SetPreset.side_effect = RuntimeError("boom")
        result = self.ctrl.set_preset("test")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

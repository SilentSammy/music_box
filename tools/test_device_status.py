"""Host checks for Wi-Fi ownership and non-blocking hardware test sequencing."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

APP = Path(__file__).resolve().parents[1] / "music_box"
sys.path.insert(0, str(APP))
import device_status


def clock():
    return types.SimpleNamespace(ticks_ms=lambda: 1000,
                                 ticks_diff=lambda a, b: a - b,
                                 ticks_add=lambda a, b: a + b)


class WifiTests(unittest.TestCase):
    def setUp(self):
        self.network = types.ModuleType("network")
        self.network.STA_IF = 0
        self.wlan = MagicMock()
        self.wlan.isconnected.return_value = False
        self.network.WLAN = MagicMock(return_value=self.wlan)
        self.platform = types.ModuleType("platform_services")
        self.platform.start_wifi_setup = MagicMock()
        self.platform.installation_context = lambda: {"current_version": "0.1.5"}
        self.patcher = patch.dict(sys.modules, {"network": self.network,
                                               "platform_services": self.platform})
        self.patcher.start()
        self.time_patch = patch.object(device_status, "time", clock())
        self.time_patch.start()

    def tearDown(self):
        self.time_patch.stop()
        self.patcher.stop()

    def test_framework_radio_is_not_disconnected_by_app(self):
        probe = device_status.WifiProbe()
        self.platform.start_wifi_setup.assert_called_once()
        self.wlan.connect.assert_not_called()
        self.wlan.isconnected.return_value = True
        probe.update(2000)
        self.assertEqual(probe.result, "OK")
        self.wlan.isconnected.return_value = False
        probe.update(50000)
        self.assertEqual(probe.result, "OK")
        probe.close()
        self.wlan.disconnect.assert_not_called()
        self.wlan.active.assert_not_called()

    def test_offline_probe_times_out_without_blocking(self):
        probe = device_status.WifiProbe()
        probe.update(46000)
        self.assertEqual(probe.result, "Failed/offline")

    def test_current_network_and_framework_version(self):
        self.assertEqual(device_status.wifi_network(), "Offline")
        self.wlan.isconnected.return_value = True
        self.wlan.config.return_value = b"SammyPC"
        self.assertEqual(device_status.wifi_network(), "SammyPC")
        self.assertEqual(device_status.installed_version(), "0.1.5")

    def test_standalone_install_has_no_framework_version(self):
        with patch.dict(sys.modules, {"platform_services": None}):
            self.assertIsNone(device_status.installed_version())

    def test_standalone_credentials_and_cleanup(self):
        secrets = types.ModuleType("wifi_secrets")
        secrets.SSID, secrets.PASSWORD = "test-network", "test-password"
        with patch.dict(sys.modules, {"platform_services": None, "wifi_secrets": secrets}):
            probe = device_status.WifiProbe()
        self.assertTrue(probe.owns_connection)
        self.wlan.connect.assert_called_once_with("test-network", "test-password")
        probe.close()
        self.wlan.disconnect.assert_called_once()
        self.wlan.active.assert_called_with(False)


class HardwareTests(unittest.TestCase):
    def test_four_buzzers_led_sensors_and_cleanup(self):
        machine = types.ModuleType("machine")
        machine.Pin = MagicMock()
        status = types.ModuleType("device_status")
        status.WifiProbe = MagicMock()
        status.WifiProbe.return_value.result = "OK"
        spec = importlib.util.spec_from_file_location("hardware_test_host", APP / "hardware_test.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"machine": machine, "device_status": status}):
            spec.loader.exec_module(module)
        module.time = clock()
        display, audio, imu = MagicMock(), MagicMock(), MagicMock()
        audio.voices = [MagicMock() for _ in range(4)]
        imu.read_motion.return_value = ((0.1, 0.2, 1.0), (1.0, 2.0, 3.0))
        test = module.HardwareTest(display, audio, imu, 75)
        for now in (1000, 2000, 3000, 4000, 5000):
            test.update(now)
        self.assertEqual([call.args[3] for call in audio.preview_note.call_args_list], [0, 1, 2, 3])
        self.assertEqual(imu.read_motion.call_count, 5)
        values = [call.args[0] for call in machine.Pin.return_value.value.call_args_list]
        self.assertIn(0, values)
        self.assertIn(1, values)
        test.close()
        audio.stop.assert_called_once()
        machine.Pin.return_value.value.assert_called_with(1)
        status.WifiProbe.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

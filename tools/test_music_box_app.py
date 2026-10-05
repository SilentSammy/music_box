"""Host regression tests for calibration, settings, menus and REPL exit."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

APP = Path(__file__).resolve().parents[1] / "music_box"
sys.path.insert(0, str(APP))
from settings import Settings


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.directory.name)
        names = ("machine", "animation_engine", "melody_balls", "mpu6050",
                 "now_playing_overlay", "quadrature_encoder", "song_player",
                 "ssd1306_driver")
        self.modules = {name: MagicMock() for name in names}
        self.modules["song_player"].FLAG_BEAT = 1
        self.modules["song_player"].FLAG_MEASURE = 2
        self.modules["song_player"].FLAG_TEMPO = 4
        self.modules["song_player"].FLAG_TIME_SIGNATURE = 8
        self.modules["song_player"].FLAG_NOTE_ONSET = 32
        self.modules["song_player"].FLAG_MELODY_ONSET = 64
        self.imu = self.modules["mpu6050"].MPU6050.return_value
        self.imu.calibrate_accel.return_value = (0.01, -0.02, 0.03)
        self.audio = self.modules["song_player"].SongPlayer.return_value
        self.audio.voices = [MagicMock() for _ in range(4)]
        self.display = self.modules["ssd1306_driver"].SSD1306.return_value
        self.display.width = 128
        self.encoder = self.modules["quadrature_encoder"].Encoder.return_value
        self.encoder.take_delta.return_value = 0
        self.encoder.take_presses.return_value = 0
        self.patcher = patch.dict(sys.modules, self.modules)
        self.patcher.start()
        spec = importlib.util.spec_from_file_location("music_box_test_main", APP / "main.py")
        self.main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main)

    def tearDown(self):
        self.patcher.stop()
        os.chdir(self.cwd)
        self.directory.cleanup()

    def test_first_boot_saves_calibration_and_default_volume(self):
        app = self.main.MusicBoxApp()
        self.assertEqual(app.volume, 75)
        self.imu.calibrate_accel.assert_called_once()
        with open("settings.json") as source:
            self.assertEqual(json.load(source)["imu_accel_offset"], [0.01, -0.02, 0.03])
        self.main.MusicBoxApp()
        self.imu.calibrate_accel.assert_called_once()
        self.assertEqual(self.imu.accel_offset, (0.01, -0.02, 0.03))

    def test_saved_volume_and_manual_recalibration(self):
        settings = Settings()
        settings.set("volume", 40)
        settings.set("imu_accel_offset", [0.1, 0.2, 0.3])
        settings.save()
        app = self.main.MusicBoxApp()
        self.assertEqual(app.volume, 40)
        self.imu.calibrate_accel.assert_not_called()
        app.recalibrate_imu()
        self.imu.calibrate_accel.assert_called_once()
        self.assertEqual(Settings().imu_calibration(), (0.01, -0.02, 0.03))

    def test_invalid_calibration_requires_new_sample(self):
        for value in (None, [], [1, 2], [1, 2, "bad"], [0, 0, float("nan")], [0, 0, 99]):
            settings = Settings()
            settings.set("imu_accel_offset", value)
            self.assertIsNone(settings.imu_calibration())

    def test_menu_has_exit_and_only_one_maps(self):
        app = self.main.MusicBoxApp()
        self.assertIn("Exit to REPL", [label for label, _ in app.main_menu])
        self.assertEqual([title for title, _, _ in self.main.SONGS].count("Maps"), 1)
        self.assertFalse(any("No anim" in title for title, _, _ in self.main.SONGS))

    def test_exit_releases_hardware(self):
        app = self.main.MusicBoxApp()
        app.exit_to_repl()
        self.assertTrue(app.exit_requested)
        self.audio.stop.assert_called_once()
        for voice in self.audio.voices:
            voice.deinit.assert_called_once()
        for pin in (self.encoder.clk, self.encoder.dt, self.encoder.sw):
            pin.irq.assert_called_once_with(handler=None)

    def test_framework_exit_bypasses_crash_and_keyboard_handlers(self):
        app = MagicMock(exit_requested=True)
        with patch.object(self.main, "MusicBoxApp", return_value=app):
            with patch.dict(sys.modules, {"platform_services": types.ModuleType("platform_services")}):
                with self.assertRaises(BaseException) as raised:
                    self.main.main()
        self.assertNotIsInstance(raised.exception, (Exception, KeyboardInterrupt, SystemExit))


if __name__ == "__main__":
    unittest.main()

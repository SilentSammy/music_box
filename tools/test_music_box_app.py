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
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(APP))
from settings import Settings
import build_update_source


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.directory.name)
        names = ("machine", "animation_engine", "melody_balls", "mpu6050",
                 "now_playing_overlay", "quadrature_encoder", "song_player",
                 "song_snake", "spinning_heart", "ssd1306_driver")
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
        self.main.time = MagicMock()
        self.main.time.ticks_ms.return_value = 1000

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
        self.assertTrue({"Animals", "Sunday Morning", "This Love",
                         "She Will Be Loved", "Stereo Hearts"}.issubset(
            {title for title, _, _ in self.main.SONGS}
        ))
        songs = {title: has_melody for title, _path, has_melody in self.main.SONGS}
        self.assertTrue(all(songs[title] for title in
                            ("Animals", "Sunday Morning", "This Love")))
        self.assertFalse(songs["She Will Be Loved"])
        self.assertFalse(songs["Stereo Hearts"])

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

    def test_playback_has_no_individual_buzzer_controls(self):
        app = self.main.MusicBoxApp()
        for play in (app.play_merry_go_round, app.play_maps,
                     app.play_she_will_be_loved, app.play_stereo_hearts):
            self.audio.set_voice_filter.reset_mock()
            self.display.text.reset_mock()
            play()
            self.audio.set_voice_filter.assert_called_once_with(None)
            app.draw_playing()
            texts = [call.args[0] for call in self.display.text.call_args_list]
            self.assertNotIn("Output:", texts)
            self.assertNotIn("All buzzers", texts)
            self.assertFalse(any(text.startswith("Buzzer ") for text in texts))

    def test_mii_channel_uses_song_snake_without_text_overlay(self):
        app = self.main.MusicBoxApp()
        engine = app.animation_engine
        app.play_mii_channel()
        engine.push.assert_called_once_with(
            self.modules["song_snake"].SongSnake.return_value
        )
        self.modules["now_playing_overlay"].NowPlayingOverlay.assert_not_called()

    def test_animals_uses_song_snake(self):
        app = self.main.MusicBoxApp()
        engine = app.animation_engine
        app.play_animals()
        engine.push.assert_called_once_with(
            self.modules["song_snake"].SongSnake.return_value
        )

    def test_song_without_annotations_uses_spinning_heart(self):
        app = self.main.MusicBoxApp()
        engine = app.animation_engine
        app.play_she_will_be_loved()
        engine.push.assert_called_once_with(
            self.modules["spinning_heart"].SpinningHeart.return_value
        )
        self.assertTrue(app.animated_playback)

    def test_about_displays_version_network_and_custom_text(self):
        app = self.main.MusicBoxApp()
        app.settings.set("about_text", "Para mi Carly. Con amor, Samu <3")
        status = types.ModuleType("device_status")
        status.installed_version = lambda: "0.1.5"
        status.wifi_network = lambda: "SammyPC"
        with patch.dict(sys.modules, {"device_status": status}):
            self.display.text.reset_mock()
            app.open_about()
        texts = [call.args[0] for call in self.display.text.call_args_list]
        self.assertIn("Version:0.1.5", texts)
        self.assertIn("WiFi:SammyPC", texts)
        self.assertIn("<3", texts)

        status.installed_version = lambda: None
        self.display.text.reset_mock()
        app.open_about()
        self.assertIn("Version:None", [call.args[0]
                                       for call in self.display.text.call_args_list])

    def test_splash_uses_custom_message_and_then_opens_menu(self):
        app = self.main.MusicBoxApp()
        self.assertEqual(app.screen, "splash")
        texts = [call.args[0] for call in self.display.text.call_args_list]
        self.assertIn("MUSIC_BOX", texts)
        self.assertIn("Para mi Carly.", texts)
        self.assertIn("Con amor, Samu", texts)
        self.assertIn("<3", texts)

        self.main.time.ticks_diff.return_value = 0
        self.display.text.reset_mock()
        app.update()
        self.assertEqual(app.screen, "menu")
        self.assertIn("Play song", [call.args[0]
                                     for call in self.display.text.call_args_list])

    def test_splash_wraps_long_words_to_display_width(self):
        self.assertEqual(
            self.main.wrap_display_text("abcdefghijklmnopq", 16),
            ["abcdefghijklmnop", "q"],
        )

    def test_hardware_screen_returns_to_menu_and_cleans_up(self):
        app = self.main.MusicBoxApp()
        module = types.ModuleType("hardware_test")
        module.HardwareTest = MagicMock()
        with patch.dict(sys.modules, {"hardware_test": module}):
            app.open_hardware_test()
        self.assertEqual(app.screen, "hardware")
        app.update()
        module.HardwareTest.return_value.update.assert_called_once_with(1000)
        self.encoder.take_presses.return_value = 1
        app.update()
        module.HardwareTest.return_value.close.assert_called_once()
        self.assertEqual(app.screen, "menu")
        self.assertIsNone(app.hardware_test)


class SettingsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.directory.name)
        self.previous = Path("previous").resolve()
        self.previous.mkdir()
        self.platform = types.ModuleType("platform_services")
        self.platform.installation_context = lambda: {"previous_path": str(self.previous)}
        self.patcher = patch.dict(sys.modules, {"platform_services": self.platform})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        os.chdir(self.cwd)
        self.directory.cleanup()

    def write_previous(self, value):
        (self.previous / "settings.json").write_text(json.dumps(value), encoding="utf-8")

    def test_migrate_legacy_values_add_defaults_and_drop_retired_keys(self):
        self.write_previous({"version": 1, "volume": 35,
                             "imu_accel_offset": [0.1, 0.2, 0.3], "retired": 42})
        original = (self.previous / "settings.json").read_bytes()
        settings = Settings()
        self.assertEqual(settings.get("version"), 2)
        self.assertEqual(settings.get("volume"), 35)
        self.assertEqual(settings.imu_calibration(), (0.1, 0.2, 0.3))
        self.assertEqual(settings.get("about_text"), "Para mi Carly. Con amor, Samu <3")
        self.assertNotIn("retired", settings.data)
        self.assertTrue(Path("settings.json").exists())
        self.assertEqual((self.previous / "settings.json").read_bytes(), original)

    def test_existing_local_settings_take_priority(self):
        self.write_previous({"version": 1, "volume": 10})
        Path("settings.json").write_text(json.dumps({"version": 2, "volume": 90,
                                                     "about_text": "My message <3"}))
        settings = Settings()
        self.assertEqual(settings.get("volume"), 90)
        self.assertEqual(settings.get("about_text"), "My message <3")

    def test_corrupt_local_imports_previous_and_invalid_values_use_defaults(self):
        Path("settings.json").write_text("{broken")
        self.write_previous({"volume": "bad", "imu_accel_offset": [0], "about_text": 1})
        settings = Settings()
        self.assertEqual(settings.get("volume"), 75)
        self.assertIsNone(settings.imu_calibration())
        self.assertEqual(settings.get("about_text"), "Para mi Carly. Con amor, Samu <3")

    def test_missing_previous_creates_settings(self):
        self.assertEqual(Settings().get("version"), 2)
        self.assertTrue(Path("settings.json").exists())

    def test_future_schema_is_not_blindly_imported(self):
        self.write_previous({"version": 999, "volume": 10})
        self.assertEqual(Settings().get("volume"), 75)

    def test_settings_and_secrets_are_excluded_from_feed(self):
        for name in ("settings.json", "settings.json.tmp", "wifi_secrets.py",
                     "pymakr.conf", "main.py"):
            Path(name).touch()
        files = {str(relative) for _, relative in build_update_source.deployable_files(Path("."))}
        self.assertEqual(files, {"main.py"})


if __name__ == "__main__":
    unittest.main()

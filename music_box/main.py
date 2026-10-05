"""Music Box application entry point."""
from machine import I2C, Pin
import time

from animation_engine import AnimationEngine
from events import (
    BEAT,
    MEASURE,
    MELODY_ONSET,
    NOTE_ONSET,
    SONG_ENDED,
    SONG_STARTED,
    TEMPO_CHANGED,
    TIME_SIGNATURE_CHANGED,
    Event,
)
from melody_balls import MelodyBalls
from menu import Menu
from mpu6050 import MPU6050
from now_playing_overlay import NowPlayingOverlay
from quadrature_encoder import Encoder
from song_player import (
    FLAG_BEAT,
    FLAG_MEASURE,
    FLAG_MELODY_ONSET,
    FLAG_NOTE_ONSET,
    FLAG_TEMPO,
    FLAG_TIME_SIGNATURE,
    SongPlayer,
)
from settings import Settings
from ssd1306_driver import SSD1306


I2C_ID = 0
SDA_PIN = 6
SCL_PIN = 7

ENCODER_CLK_PIN = 3
ENCODER_DT_PIN = 1
ENCODER_SW_PIN = 0

VOLUME_STEP = 5
PREVIEW_NOTE = 72
PREVIEW_DURATION_MS = 250
ANIMATION_FPS = 10
OLED_PAGE_GUARD_MS = 5
PLAYBACK_LOOP_SLEEP_MS = 2
IDLE_LOOP_SLEEP_MS = 20

SONGS = (
    ("He's a Pirate", "songs/hes_a_pirate.song", True),
    ("Merry-Go-Round", "songs/merry_go_round.song", False),
    ("Mii Channel", "songs/mii_channel.song", True),
    ("Super Mario", "songs/super_mario_world.song", True),
    ("Maps", "songs/maps.song", True),
)
ANIMATIONS_ENABLED = True
PLAYBACK_OUTPUTS = (
    "All buzzers",
    "Buzzer 1",
    "Buzzer 2",
    "Buzzer 3",
    "Buzzer 4",
)


class AnimationHardware:
    def __init__(self, display, encoder, imu):
        self.display = display
        self.encoder = encoder
        self.imu = imu
        # MPU6050 has no magnetometer; this slot accepts an optional driver.
        self.magnetometer = None


class MusicBoxApp:
    def __init__(self):
        self.settings = Settings()
        i2c = I2C(I2C_ID, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400_000)
        self.display = SSD1306(i2c)
        self.encoder = Encoder(
            clk_pin=ENCODER_CLK_PIN,
            dt_pin=ENCODER_DT_PIN,
            sw_pin=ENCODER_SW_PIN,
        )
        self.audio = SongPlayer()
        self._deferred_song_events = []
        self.imu = None
        self.imu_offset = None
        self.animation_engine = None
        if ANIMATIONS_ENABLED:
            self.imu = MPU6050(i2c)
            self.imu_offset = self.settings.imu_calibration()
            if self.imu_offset is None:
                self.calibrate_imu()
            else:
                self.imu.accel_offset = self.imu_offset
            print("MPU6050 acceleration offset:", self.imu_offset)
            animation_hardware = AnimationHardware(
                self.display,
                self.encoder,
                self.imu,
            )
            self.animation_engine = AnimationEngine(
                animation_hardware,
                self.audio.state,
                frames_per_second=ANIMATION_FPS,
                service_callback=self._service_audio_during_display,
                render_guard=self._animation_frame_allowed,
            )
        self.volume = self.settings.get("volume")
        self.exit_requested = False
        self.screen = "menu"
        self.song_title = None
        self.animated_playback = False
        self.playback_output_index = 0
        self.playback_output_selection = True

        self.main_menu = (
            ("Play song", self.open_song_menu),
            ("Volume", self.open_volume),
            ("Calibrate IMU", self.recalibrate_imu),
            ("Hardware test", self.do_nothing),
            ("Exit to REPL", self.exit_to_repl),
        )
        self.song_menu = (
            ("< Back", self.close_song_menu),
            (SONGS[0][0], self.play_hes_a_pirate),
            (SONGS[1][0], self.play_merry_go_round),
            (SONGS[2][0], self.play_mii_channel),
            (SONGS[3][0], self.play_super_mario),
            (SONGS[4][0], self.play_maps),
        )
        self.menu = Menu(self.display, self.main_menu)

    def do_nothing(self):
        pass

    def calibrate_imu(self):
        self.display.clear()
        self.display.text("Calibrating IMU", 8, 20)
        self.display.text("Keep device still", 0, 34)
        self.display.show()
        self.imu_offset = self.imu.calibrate_accel()
        self.settings.set("imu_accel_offset", self.imu_offset)
        self.settings.save()

    def recalibrate_imu(self):
        if self.imu is not None:
            self.calibrate_imu()
        self.menu.draw()

    def exit_to_repl(self):
        self.audio.stop()
        for voice in self.audio.voices:
            voice.deinit()
        for pin in (self.encoder.clk, self.encoder.dt, self.encoder.sw):
            pin.irq(handler=None)
        if self.animation_engine is not None:
            self.animation_engine.clear_layers()
        self.display.clear()
        self.display.text("REPL via USB", 16, 20)
        self.display.text("Reset to resume", 4, 34)
        self.display.show()
        self.exit_requested = True
        print("Music Box stopped. REPL via USB; reset to resume.")

    def open_song_menu(self):
        self.screen = "songs"
        self.menu.set_menu(self.song_menu)

    def close_song_menu(self):
        self.screen = "menu"
        self.menu.set_menu(self.main_menu)

    def play_hes_a_pirate(self):
        self.start_song(*SONGS[0])

    def play_merry_go_round(self):
        self.start_song(*SONGS[1])

    def play_mii_channel(self):
        self.start_song(*SONGS[2])

    def play_super_mario(self):
        self.start_song(*SONGS[3])

    def play_maps(self):
        self.start_song(*SONGS[4])

    def start_song(self, title, path, has_melody):
        self._deferred_song_events = []
        self.song_title = title
        self.screen = "playing"
        self.playback_output_index = 0
        self.playback_output_selection = path != "songs/merry_go_round.song"
        self.audio.set_voice_filter(None)
        self.animated_playback = bool(
            self.animation_engine is not None
            and has_melody
        )
        self.audio.start(path, self.settings.get("volume"), title)
        if self.animated_playback:
            now = time.ticks_ms()
            self.animation_engine.clear_layers()
            self.animation_engine.reset_clock(now)
            self.animation_engine.push(MelodyBalls())
            self.animation_engine.push(NowPlayingOverlay(title))
            self.animation_engine.post(
                Event(SONG_STARTED, 0, now, self.audio)
            )
            self._dispatch_song_events(now)
            self.animation_engine.step(now)
        else:
            self.draw_playing()

    def stop_song(self):
        self.audio.stop()
        self._deferred_song_events = []
        if self.animation_engine is not None:
            self.animation_engine.clear_layers()
        self.animated_playback = False
        self.song_title = None
        self.screen = "songs"
        self.menu.set_menu(self.song_menu)

    def draw_playing(self):
        display = self.display
        display.clear()
        display.text("NOW PLAYING", 20, 2)
        title_x = max(0, (display.width - len(self.song_title) * 8) // 2)
        display.text(self.song_title, title_x, 15)
        if self.playback_output_selection:
            display.text("Output:", 0, 29)
            output = PLAYBACK_OUTPUTS[self.playback_output_index]
            output_x = max(0, (display.width - len(output) * 8) // 2)
            display.text(output, output_x, 40)
        display.fill_rect(0, 52, display.width, 12, 1)
        display.text("Click: Stop", 20, 54, 0)
        display.show()

    def adjust_playback_output(self, delta):
        if not self.playback_output_selection:
            return
        self.playback_output_index = (
            self.playback_output_index + delta
        ) % len(PLAYBACK_OUTPUTS)
        voice_index = (
            None
            if self.playback_output_index == 0
            else self.playback_output_index - 1
        )
        self.audio.set_voice_filter(voice_index)
        self.draw_playing()

    def _service_audio_during_display(self):
        if not self.audio.playing:
            return
        self.audio.update(time.ticks_ms())
        if self.audio.record_events:
            self._deferred_song_events.extend(self.audio.record_events)

    def _animation_frame_allowed(self, now_ms):
        remaining_ms = self.audio.time_until_next_record(now_ms)
        return remaining_ms is None or remaining_ms > OLED_PAGE_GUARD_MS

    def _take_song_events(self):
        if not self._deferred_song_events:
            return self.audio.record_events
        events = self._deferred_song_events
        self._deferred_song_events = []
        if self.audio.record_events:
            events.extend(self.audio.record_events)
        return events

    def _dispatch_song_events(self, now_ms, records=None):
        if records is None:
            records = self.audio.record_events
        for song_ms, flags, _voices, melody in records:
            if flags & FLAG_BEAT:
                self.animation_engine.post(
                    Event(BEAT, song_ms, now_ms, self.audio)
                )
            if flags & FLAG_MEASURE:
                self.animation_engine.post(
                    Event(MEASURE, song_ms, now_ms, self.audio)
                )
            if flags & FLAG_NOTE_ONSET:
                self.animation_engine.post(
                    Event(NOTE_ONSET, song_ms, now_ms, self.audio)
                )
            if flags & FLAG_MELODY_ONSET:
                self.animation_engine.post(
                    Event(MELODY_ONSET, melody, now_ms, self.audio)
                )
            if flags & FLAG_TEMPO:
                self.animation_engine.post(
                    Event(TEMPO_CHANGED, self.audio.state.tempo_us, now_ms, self.audio)
                )
            if flags & FLAG_TIME_SIGNATURE:
                signature = (
                    self.audio.state.numerator,
                    self.audio.state.denominator,
                )
                self.animation_engine.post(
                    Event(TIME_SIGNATURE_CHANGED, signature, now_ms, self.audio)
                )

    def open_volume(self):
        self.volume = self.settings.get("volume")
        self.screen = "volume"
        self.draw_volume()

    def adjust_volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta * VOLUME_STEP))
        self.draw_volume()
        self.play_volume_preview()

    def play_volume_preview(self):
        self.audio.preview_note(
            PREVIEW_NOTE,
            self.volume,
            PREVIEW_DURATION_MS,
        )

    def close_volume(self):
        self.audio.stop()
        self.settings.set("volume", self.volume)
        self.settings.save()
        self.screen = "menu"
        self.menu.draw()

    def draw_volume(self):
        display = self.display
        display.clear()

        display.text("VOLUME", 40, 0)
        percentage = "%d%%" % self.volume
        display.text(
            percentage,
            (display.width - len(percentage) * 8) // 2,
            12,
        )

        bar_x = 8
        bar_y = 28
        bar_width = 112
        bar_height = 14
        inner_width = bar_width - 4
        display.fill_rect(bar_x, bar_y, bar_width, bar_height, 1)
        display.fill_rect(bar_x + 2, bar_y + 2, inner_width, bar_height - 4, 0)
        fill_width = round(inner_width * self.volume / 100)
        if fill_width:
            display.fill_rect(bar_x + 2, bar_y + 2, fill_width, bar_height - 4, 1)

        display.fill_rect(0, 52, display.width, 12, 1)
        display.text("Click: Back", 20, 54, 0)
        display.show()

    def update(self):
        now = time.ticks_ms()
        was_playing = self.audio.playing
        self.audio.update(now)

        if self.screen == "playing" and self.animated_playback:
            self._dispatch_song_events(now, self._take_song_events())
            if was_playing and not self.audio.playing:
                self.animation_engine.post(
                    Event(SONG_ENDED, self.audio.duration_ms, now, self.audio)
                )
            self.animation_engine.step(now)
            if not self.audio.playing or self.animation_engine.context.input.button_pressed:
                self.stop_song()
            return

        if self.screen == "playing" and was_playing and not self.audio.playing:
            self.stop_song()
            return

        delta = self.encoder.take_delta()
        if delta:
            if self.screen == "volume":
                self.adjust_volume(delta)
            elif self.screen == "playing":
                self.adjust_playback_output(delta)
            else:
                scroll = self.menu.scroll_down if delta > 0 else self.menu.scroll_up
                for _ in range(abs(delta)):
                    scroll()

        for _ in range(self.encoder.take_presses()):
            if self.screen == "volume":
                self.close_volume()
            elif self.screen == "playing":
                self.stop_song()
            else:
                self.menu.select()
            if self.exit_requested:
                break


def main(max_iterations=None):
    app = MusicBoxApp()
    iterations = 0
    while not app.exit_requested and (max_iterations is None or iterations < max_iterations):
        app.update()
        iterations += 1
        time.sleep_ms(
            PLAYBACK_LOOP_SLEEP_MS
            if app.screen == "playing"
            else IDLE_LOOP_SLEEP_MS
        )
    if app.exit_requested:
        try:
            import platform_services
        except ImportError:
            pass
        else:
            # Returning would leave the supervisor's keep-alive loop running.
            # KeyboardInterrupt disables its watchdog feeder; SystemExit resets
            # MicroPython. BaseException reaches REPL without either effect,
            # leaving background update checks and watchdog feeding active.
            raise BaseException("Music Box exited to REPL")
    return app


if __name__ == "__main__":
    main()

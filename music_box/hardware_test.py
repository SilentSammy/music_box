"""Live sensor, sequential buzzer, LED and Wi-Fi diagnostic screen."""
from machine import Pin
import time
from device_status import WifiProbe


class HardwareTest:
    def __init__(self, display, audio, imu, volume):
        self.display = display
        self.audio = audio
        self.imu = imu
        self.volume = volume
        self.led = Pin(8, Pin.OUT, value=1)  # Super Mini's LED is active-low.
        self.led_on = False
        now = time.ticks_ms()
        self.started = now
        self.next_led = now
        self.next_buzzer = now
        self.next_frame = now
        self.buzzer_index = 0
        self.wifi = WifiProbe()

    def update(self, now):
        self.wifi.update(now)
        if time.ticks_diff(now, self.next_led) >= 0:
            self.led_on = not self.led_on
            self.led.value(0 if self.led_on else 1)
            self.next_led = time.ticks_add(now, 250)
        if self.buzzer_index < len(self.audio.voices) and time.ticks_diff(now, self.next_buzzer) >= 0:
            self.audio.preview_note(72, self.volume, 500, self.buzzer_index)
            print("Hardware test: buzzer", self.buzzer_index + 1)
            self.buzzer_index += 1
            self.next_buzzer = time.ticks_add(now, 1000)
        if time.ticks_diff(now, self.next_frame) < 0:
            return
        self.next_frame = time.ticks_add(now, 200)
        display = self.display
        display.clear()
        gyro_page = (time.ticks_diff(now, self.started) // 2000) % 2
        label = "Gyro" if gyro_page else "Accel"
        done = (self.buzzer_index == len(self.audio.voices)
                and time.ticks_diff(now, self.next_buzzer) >= 0)
        buzzer = "done" if done else str(self.buzzer_index)
        display.text("Bz:%s %s" % (buzzer, label), 0, 0)
        display.text("WiFi:" + self.wifi.result, 0, 10)
        try:
            if self.imu is None:
                raise OSError("IMU unavailable")
            accel, gyro = self.imu.read_motion()
            values = gyro if gyro_page else accel
            for axis, name in enumerate(("X", "Y", "Z")):
                display.text("%s:%+.2f %s" % (name, values[axis], "d/s" if gyro_page else "g"), 0, 22 + axis * 10)
        except OSError:
            display.text("IMU unavailable", 0, 30)
        display.text("Click: Back", 20, 54)
        display.show()

    def close(self):
        self.audio.stop()
        self.led.value(1)
        self.wifi.close()

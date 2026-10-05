"""Shared access to every physical Music Box component."""
from machine import I2C, Pin, PWM

from mpu6050 import MPU6050
from quadrature_encoder import Encoder
from ssd1306_driver import SSD1306


I2C_ID = 0
SDA_PIN = 6
SCL_PIN = 7
OLED_ADDRESS = 0x3C
MPU_ADDRESS = 0x68

ENCODER_CLK_PIN = 3
ENCODER_DT_PIN = 1
ENCODER_SW_PIN = 0

BUZZER_PINS = (5, 9, 10, 20)
MAX_TONE_DUTY = 32_768


class Hardware:
    def __init__(self):
        self.i2c = I2C(
            I2C_ID,
            scl=Pin(SCL_PIN),
            sda=Pin(SDA_PIN),
            freq=400_000,
        )
        devices = self.i2c.scan()
        if OLED_ADDRESS not in devices:
            raise RuntimeError("SSD1306 not found at 0x3c")
        if MPU_ADDRESS not in devices:
            raise RuntimeError("MPU6050 not found at 0x68")

        self.display = SSD1306(self.i2c, address=OLED_ADDRESS)
        self.imu = MPU6050(self.i2c, address=MPU_ADDRESS)
        print("Calibrating MPU6050; keep the device still...")
        self.imu_offset = self.imu.calibrate_accel()
        print("MPU6050 acceleration offset:", self.imu_offset)
        # MPU6050 has no magnetometer. Attach an optional driver here later;
        # InputSampler will then expose its readings automatically.
        self.magnetometer = None
        self.encoder = Encoder(
            clk_pin=ENCODER_CLK_PIN,
            dt_pin=ENCODER_DT_PIN,
            sw_pin=ENCODER_SW_PIN,
        )
        self.buzzers = [
            PWM(Pin(pin), freq=440, duty_u16=0)
            for pin in BUZZER_PINS
        ]

    def set_tone(self, index, frequency, volume=1.0):
        """Play one buzzer with normalized, audio-tapered volume."""
        volume = max(0.0, min(1.0, volume))
        buzzer = self.buzzers[index]
        buzzer.freq(round(frequency))
        buzzer.duty_u16(round(MAX_TONE_DUTY * volume ** 3))

    def stop_tone(self, index):
        self.buzzers[index].duty_u16(0)

    def silence(self):
        for buzzer in self.buzzers:
            buzzer.duty_u16(0)

    def close(self):
        self.silence()
        for buzzer in self.buzzers:
            buzzer.deinit()

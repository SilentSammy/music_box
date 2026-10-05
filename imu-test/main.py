"""Display calibrated MPU6050 acceleration on an SSD1306 OLED."""
from machine import I2C, Pin
import math
import time

from mpu6050 import MPU6050
from ssd1306_driver import SSD1306


I2C_ID = 0
SDA_PIN = 6
SCL_PIN = 7
OLED_ADDRESS = 0x3C
MPU_ADDRESS = 0x68


def show_lines(display, lines):
    display.clear()
    for row, line in enumerate(lines[:8]):
        display.text(line, 0, row * 8)
    display.show()


def main(max_updates=None):
    i2c = I2C(I2C_ID, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400_000)
    devices = i2c.scan()
    if OLED_ADDRESS not in devices:
        raise RuntimeError("SSD1306 not found at 0x3c")

    display = SSD1306(i2c, address=OLED_ADDRESS)
    if MPU_ADDRESS not in devices:
        show_lines(display, ("MPU6050 ERROR", "Not found: 0x68"))
        raise RuntimeError("MPU6050 not found at 0x68")

    mpu = MPU6050(i2c, address=MPU_ADDRESS)

    def calibration_progress(sample, total):
        show_lines(
            display,
            (
                "Calibrating IMU",
                "Keep it still",
                "and level",
                "%d%%" % (sample * 100 // total),
            ),
        )

    offset = mpu.calibrate(progress=calibration_progress)
    print("MPU6050 accel offset (g):", offset)

    # Light smoothing makes the display readable without hiding normal motion.
    filtered = list(mpu.read_accel())
    alpha = 0.25
    updates = 0

    while max_updates is None or updates < max_updates:
        acceleration = mpu.read_accel()
        for axis in range(3):
            filtered[axis] += alpha * (acceleration[axis] - filtered[axis])

        magnitude = math.sqrt(sum(value * value for value in filtered))
        show_lines(
            display,
            (
                "MPU6050 ACCEL",
                "X: %+7.3f g" % filtered[0],
                "Y: %+7.3f g" % filtered[1],
                "Z: %+7.3f g" % filtered[2],
                "|a|: %6.3f g" % magnitude,
            ),
        )
        updates += 1
        time.sleep_ms(100)

    print("Displayed", updates, "calibrated samples")


if __name__ == "__main__":
    main()

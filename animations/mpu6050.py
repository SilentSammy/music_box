"""Small MPU6050 accelerometer and gyroscope driver for MicroPython."""
import struct
import time


class MPU6050:
    ADDRESS = 0x68
    WHO_AM_I = 0x75
    PWR_MGMT_1 = 0x6B
    SMPLRT_DIV = 0x19
    CONFIG = 0x1A
    GYRO_CONFIG = 0x1B
    ACCEL_CONFIG = 0x1C
    ACCEL_XOUT_H = 0x3B
    GYRO_XOUT_H = 0x43
    ACCEL_SCALE = 16384.0
    GYRO_SCALE = 131.0

    def __init__(self, i2c, address=ADDRESS):
        self.i2c = i2c
        self.address = address
        self.accel_offset = (0.0, 0.0, 0.0)

        identity = self._read(self.WHO_AM_I, 1)[0]
        if identity not in (0x68, 0x69):
            raise RuntimeError("unexpected MPU6050 identity: 0x%02x" % identity)

        self._write(self.PWR_MGMT_1, 0x01)
        time.sleep_ms(100)
        self._write(self.CONFIG, 0x03)
        self._write(self.SMPLRT_DIV, 0x09)
        self._write(self.GYRO_CONFIG, 0x00)
        self._write(self.ACCEL_CONFIG, 0x00)

    def _read(self, register, count):
        return self.i2c.readfrom_mem(self.address, register, count)

    def _write(self, register, value):
        self.i2c.writeto_mem(self.address, register, bytes((value,)))

    def read_raw_accel(self):
        return struct.unpack(">hhh", self._read(self.ACCEL_XOUT_H, 6))

    def read_accel(self):
        raw = self.read_raw_accel()
        return tuple(
            raw[axis] / self.ACCEL_SCALE - self.accel_offset[axis]
            for axis in range(3)
        )

    def read_gyro(self):
        raw = struct.unpack(">hhh", self._read(self.GYRO_XOUT_H, 6))
        return tuple(value / self.GYRO_SCALE for value in raw)

    def calibrate_accel(self, samples=200, delay_ms=5):
        sums = [0, 0, 0]
        for _ in range(samples):
            values = self.read_raw_accel()
            for axis in range(3):
                sums[axis] += values[axis]
            time.sleep_ms(delay_ms)
        averages = tuple(total / samples / self.ACCEL_SCALE for total in sums)
        self.accel_offset = (averages[0], averages[1], averages[2] - 1.0)
        return self.accel_offset

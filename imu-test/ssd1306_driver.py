"""Minimal SSD1306 I2C OLED driver for a 128x64 monochrome display."""
import framebuf


_INIT_CMDS = (
    0xAE,
    0x20, 0x00,
    0xB0,
    0xC8,
    0x00,
    0x10,
    0x40,
    0x81, 0x7F,
    0xA1,
    0xA6,
    0xA8, 0x3F,
    0xA4,
    0xD3, 0x00,
    0xD5, 0x80,
    0xD9, 0xF1,
    0xDA, 0x12,
    0xDB, 0x40,
    0x8D, 0x14,
    0xAF,
)


class SSD1306:
    def __init__(self, i2c, width=128, height=64, address=0x3C):
        self.i2c = i2c
        self.width = width
        self.height = height
        self.address = address
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        self.fb = framebuf.FrameBuffer(
            self.buffer, width, height, framebuf.MONO_VLSB
        )
        for command in _INIT_CMDS:
            self._write_command(command)
        self.clear()
        self.show()

    def _write_command(self, command):
        self.i2c.writeto(self.address, bytes((0x80, command)))

    def clear(self):
        self.fb.fill(0)

    def text(self, value, x, y, color=1):
        self.fb.text(value, x, y, color)

    def show(self):
        for page in range(self.pages):
            self._write_command(0xB0 | page)
            self._write_command(0x00)
            self._write_command(0x10)
            start = page * self.width
            self.i2c.writeto(
                self.address,
                b"\x40" + self.buffer[start:start + self.width],
            )

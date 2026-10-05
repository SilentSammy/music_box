"""Minimal SSD1306 I2C OLED driver (128x64, monochrome).

Validated against real hardware: SCL=GPIO7, SDA=GPIO6, addr=0x3C.
Subclasses nothing fancy -- wraps a framebuf.FrameBuffer so all the
standard draw primitives (text, pixel, line, rect, fill_rect, ...)
are available as self.fb.<method>(...), with a few convenience
wrappers below for the ones the menu needs.
"""
import framebuf

_INIT_CMDS = (
    0xAE,        # display off
    0x20, 0x00,  # memory addressing mode = horizontal
    0xB0,        # page start address
    0xC8,        # COM output scan direction remapped
    0x00,        # low column address
    0x10,        # high column address
    0x40,        # start line address
    0x81, 0x7F,  # contrast
    0xA1,        # segment re-map
    0xA6,        # normal display (not inverted)
    0xA8, 0x3F,  # multiplex ratio (64-1)
    0xA4,        # output follows RAM
    0xD3, 0x00,  # display offset
    0xD5, 0x80,  # display clock divide
    0xD9, 0xF1,  # pre-charge period
    0xDA, 0x12,  # COM pins configuration
    0xDB, 0x40,  # VCOMH deselect level
    0x8D, 0x14,  # charge pump enable
    0xAF,        # display on
)


class SSD1306:
    def __init__(self, i2c, width=128, height=64, addr=0x3C):
        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        self.fb = framebuf.FrameBuffer(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes([0x80, cmd]))

    def _write_data(self, buf):
        self.i2c.writeto(self.addr, b"\x40" + buf)

    def _init_display(self):
        for cmd in _INIT_CMDS:
            self._write_cmd(cmd)
        self.clear()
        self.show()

    def clear(self):
        self.fb.fill(0)

    def show(self):
        # Send the whole buffer, one page (8 pixel rows) at a time.
        for page in range(self.pages):
            self._write_cmd(0xB0 | page)
            self._write_cmd(0x00)
            self._write_cmd(0x10)
            self._write_data(self.buffer[page * self.width:(page + 1) * self.width])

    def text(self, s, x, y, color=1):
        self.fb.text(s, x, y, color)

    def fill_rect(self, x, y, w, h, color):
        self.fb.fill_rect(x, y, w, h, color)

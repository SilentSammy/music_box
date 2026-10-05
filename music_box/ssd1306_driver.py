"""Minimal SSD1306 I2C driver for the 128x64 monochrome OLED."""
import framebuf


_INIT_COMMANDS = (
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
        self.framebuffer = framebuf.FrameBuffer(
            self.buffer,
            width,
            height,
            framebuf.MONO_VLSB,
        )

        for command in _INIT_COMMANDS:
            self._write_command(command)
        self.clear()
        self.show()

    def _write_command(self, command):
        self.i2c.writeto(self.address, bytes((0x80, command)))

    def clear(self):
        self.framebuffer.fill(0)

    def pixel(self, x, y, color=1):
        self.framebuffer.pixel(x, y, color)

    def line(self, x1, y1, x2, y2, color=1):
        self.framebuffer.line(x1, y1, x2, y2, color)

    def circle(self, center_x, center_y, radius, color=1):
        x = radius
        y = 0
        error = 1 - radius
        while x >= y:
            points = (
                (center_x + x, center_y + y),
                (center_x + y, center_y + x),
                (center_x - y, center_y + x),
                (center_x - x, center_y + y),
                (center_x - x, center_y - y),
                (center_x - y, center_y - x),
                (center_x + y, center_y - x),
                (center_x + x, center_y - y),
            )
            for point_x, point_y in points:
                self._safe_pixel(point_x, point_y, color)
            y += 1
            if error < 0:
                error += 2 * y + 1
            else:
                x -= 1
                error += 2 * (y - x) + 1

    def _safe_pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.framebuffer.pixel(x, y, color)

    def sparkle(self, center_x, center_y, radius, color=1, variant=0):
        variant %= 7
        if variant == 0:
            self._sparkle_filled(center_x, center_y, radius, color, 3)
        elif variant == 1:
            self._sparkle_diagonal(center_x, center_y, radius, color)
        elif variant == 2:
            self._sparkle_rays(center_x, center_y, radius, color)
        elif variant == 3:
            self._sparkle_diamond(center_x, center_y, radius, color)
        elif variant == 4:
            self._sparkle_burst(center_x, center_y, radius, color)
        elif variant == 5:
            self._sparkle_filled(center_x, center_y, radius, color, 2)
        else:
            self._sparkle_web(center_x, center_y, radius, color)

    def _sparkle_filled(self, center_x, center_y, radius, color, exponent):
        divisor = radius ** (exponent - 1)
        for offset_y in range(-radius, radius + 1):
            remaining = radius - abs(offset_y)
            half_width = (
                remaining ** exponent + divisor // 2
            ) // divisor
            for offset_x in range(-half_width, half_width + 1):
                self._safe_pixel(center_x + offset_x, center_y + offset_y, color)

    def _sparkle_diagonal(self, center_x, center_y, radius, color):
        for offset in range(-radius, radius + 1):
            self._safe_pixel(center_x + offset, center_y + offset, color)
            self._safe_pixel(center_x + offset, center_y - offset, color)
        for x, y in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            self._safe_pixel(center_x + x, center_y + y, color)

    def _sparkle_rays(self, center_x, center_y, radius, color):
        diagonal = max(1, radius - 2)
        for offset in range(-radius, radius + 1):
            self._safe_pixel(center_x + offset, center_y, color)
            self._safe_pixel(center_x, center_y + offset, color)
        for offset in range(-diagonal, diagonal + 1):
            self._safe_pixel(center_x + offset, center_y + offset, color)
            self._safe_pixel(center_x + offset, center_y - offset, color)

    def _sparkle_diamond(self, center_x, center_y, radius, color):
        for offset_x in range(-radius, radius + 1):
            offset_y = radius - abs(offset_x)
            self._safe_pixel(center_x + offset_x, center_y + offset_y, color)
            self._safe_pixel(center_x + offset_x, center_y - offset_y, color)
        self._safe_pixel(center_x, center_y, color)

    def _sparkle_burst(self, center_x, center_y, radius, color):
        core = max(1, radius // 3)
        for y in range(-core, core + 1):
            for x in range(-core, core + 1):
                self._safe_pixel(center_x + x, center_y + y, color)
        for distance in range(core + 1, radius + 1):
            self._safe_pixel(center_x + distance, center_y, color)
            self._safe_pixel(center_x - distance, center_y, color)
            self._safe_pixel(center_x, center_y + distance, color)
            self._safe_pixel(center_x, center_y - distance, color)
        for distance in range(core + 1, radius):
            for sign_x, sign_y in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                self._safe_pixel(
                    center_x + sign_x * distance,
                    center_y + sign_y * distance,
                    color,
                )

    def _sparkle_web(self, center_x, center_y, radius, color):
        self.circle(center_x, center_y, max(1, radius - 2), color)
        for offset in range(-radius, radius + 1):
            self._safe_pixel(center_x + offset, center_y, color)
            self._safe_pixel(center_x, center_y + offset, color)
        diagonal = max(1, radius - 1)
        for sign_x, sign_y in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            for distance in range(1, diagonal + 1):
                self._safe_pixel(
                    center_x + sign_x * distance,
                    center_y + sign_y * distance,
                    color,
                )

    def text(self, value, x, y, color=1):
        self.framebuffer.text(value, x, y, color)

    def fill_rect(self, x, y, width, height, color):
        self.framebuffer.fill_rect(x, y, width, height, color)

    def show(self, service_callback=None):
        for page in range(self.pages):
            self._write_command(0xB0 | page)
            self._write_command(0x00)
            self._write_command(0x10)
            start = page * self.width
            self.i2c.writeto(
                self.address,
                b"\x40" + self.buffer[start:start + self.width],
            )
            if service_callback is not None:
                service_callback()

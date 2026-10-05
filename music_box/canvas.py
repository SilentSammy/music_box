"""Draw-only view of the OLED framebuffer; intentionally has no show()."""


class Canvas:
    __slots__ = ("_display", "width", "height", "buffer", "framebuffer")

    def __init__(self, display):
        self._display = display
        self.width = display.width
        self.height = display.height
        self.buffer = display.buffer
        self.framebuffer = display.framebuffer

    def clear(self):
        self._display.clear()

    def pixel(self, x, y, color=1):
        self._display.pixel(x, y, color)

    def line(self, x1, y1, x2, y2, color=1):
        self._display.line(x1, y1, x2, y2, color)

    def circle(self, center_x, center_y, radius, color=1):
        self._display.circle(center_x, center_y, radius, color)

    def sparkle(self, center_x, center_y, radius, color=1, variant=0):
        self._display.sparkle(center_x, center_y, radius, color, variant)

    def text(self, value, x, y, color=1):
        self._display.text(value, x, y, color)

    def fill_rect(self, x, y, width, height, color):
        self._display.fill_rect(x, y, width, height, color)

"""Reusable centered caption layer."""
from animation import Animation


class CaptionOverlay(Animation):
    def __init__(self, text=""):
        self.text = text

    def set_text(self, value):
        changed = value != self.text
        self.text = value
        return changed

    def render(self, canvas, context):
        if not self.text:
            return
        value = str(self.text)[: canvas.width // 8]
        banner_height = 12
        y = canvas.height - banner_height
        canvas.fill_rect(0, y, canvas.width, banner_height, 1)
        x = max(0, (canvas.width - len(value) * 8) // 2)
        canvas.text(value, x, y + 2, 0)

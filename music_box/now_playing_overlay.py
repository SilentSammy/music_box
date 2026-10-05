"""Minimal transparent now-playing text rendered as a top layer."""
from animation import Animation


class NowPlayingOverlay(Animation):
    def __init__(self, title):
        self.title = title

    def render(self, canvas, context):
        heading = "NOW PLAYING"
        heading_x = (canvas.width - len(heading) * 8) // 2
        canvas.text(heading, heading_x, 4, 1)

        title = self.title[: canvas.width // 8]
        title_x = max(0, (canvas.width - len(title) * 8) // 2)
        canvas.text(title, title_x, 24, 1)

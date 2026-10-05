"""Static gallery for comparing monochrome snowflake sprites."""
from animation import Animation


class SnowflakeGallery(Animation):
    opaque = True

    CENTERS = (
        (16, 16),
        (48, 16),
        (80, 16),
        (112, 16),
        (16, 48),
        (48, 48),
        (80, 48),
        (112, 48),
    )

    def render(self, canvas, context):
        for variant, (x, y) in enumerate(self.CENTERS):
            canvas.snowflake(x, y, 7, 1, variant)

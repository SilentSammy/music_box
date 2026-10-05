"""Procedural rotating wireframe animation."""
import math

from animation import Animation


class RotatingCube(Animation):
    opaque = True
    ROTATIONS_PER_SECOND = 0.12

    _VERTICES = (
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    )
    _EDGES = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )

    def __init__(self):
        self.angle = 0.0

    def on_enter(self, context):
        self.angle = 0.0

    def update(self, context):
        self.angle += (
            context.dt_ms
            * self.ROTATIONS_PER_SECOND
            * 2
            * math.pi
            / 1000
        )
        return bool(context.dt_ms)

    def render(self, canvas, context):
        cos_z = math.cos(self.angle)
        sin_z = math.sin(self.angle)
        cos_x = math.cos(self.angle * 0.63 + 0.55)
        sin_x = math.sin(self.angle * 0.63 + 0.55)
        points = []

        for x, y, z in self._VERTICES:
            rotated_x = x * cos_z - y * sin_z
            rotated_y = x * sin_z + y * cos_z
            tilted_y = rotated_y * cos_x - z * sin_x
            depth = rotated_y * sin_x + z * cos_x
            scale = 38 / (4 + depth)
            points.append(
                (
                    round(canvas.width / 2 + rotated_x * scale),
                    round(canvas.height / 2 + tilted_y * scale),
                )
            )

        for start, end in self._EDGES:
            canvas.line(
                points[start][0],
                points[start][1],
                points[end][0],
                points[end][1],
                1,
            )

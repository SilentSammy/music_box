"""Measure-synchronized, IMU-driven sparkle animation."""
import math
import random

from animation import Animation, EVENT_DIRTY
from events import MEASURE, NOTE_ONSET


class BouncingSparkles(Animation):
    opaque = True

    MAX_CURRENT_SPARKLES = 5
    RADIUS_PX = 5
    DISPLAY_DIAGONAL_CM = 0.95 * 2.54
    MIN_SPEED_CM_S = 0.5
    MAX_SPEED_CM_S = 2.0
    STANDARD_GRAVITY_CM_S2 = 980.665
    GRAVITY_FRACTION = 0.04
    GRAVITY_SMOOTHING = 0.25
    RESTITUTION = 1.0
    MAX_PHYSICS_STEP_S = 0.01
    SPARKLE_VARIANTS = 7

    def __init__(self):
        self.sparkles = []
        self.waiting_for_first_note = False
        self.gravity_x = 0.0
        self.gravity_y = 0.0

    def on_enter(self, context):
        canvas = context.canvas
        aspect_ratio = canvas.width / canvas.height
        self.screen_height_cm = self.DISPLAY_DIAGONAL_CM / math.sqrt(
            aspect_ratio * aspect_ratio + 1
        )
        self.screen_width_cm = self.screen_height_cm * aspect_ratio
        self.cm_per_pixel_x = self.screen_width_cm / canvas.width
        self.cm_per_pixel_y = self.screen_height_cm / canvas.height
        self.radius_cm = self.RADIUS_PX * self.cm_per_pixel_x
        self.sparkles = []
        self.waiting_for_first_note = False
        self.gravity_x = 0.0
        self.gravity_y = 0.0

    def on_exit(self, context):
        self.sparkles = []

    def on_event(self, event, context):
        if event.type == MEASURE:
            self.waiting_for_first_note = True
        elif event.type == NOTE_ONSET and self.waiting_for_first_note:
            self.waiting_for_first_note = False
            self._spawn(event.value)
            return EVENT_DIRTY
        return 0

    def update(self, context):
        if context.input.imu_updated:
            self._update_gravity(context.input.accel)
        remaining = min(context.dt_ms, 200) / 1000
        while remaining > 0:
            step = min(remaining, self.MAX_PHYSICS_STEP_S)
            self._move(step)
            remaining -= step
        return bool(self.sparkles and context.dt_ms)

    def _spawn(self, song_position_ms):
        radius = self.radius_cm
        sparkle = {
            "x": self._random_between(radius, self.screen_width_cm - radius),
            "y": self._random_between(radius, self.screen_height_cm - radius),
            "vx": 0.0,
            "vy": 0.0,
            "born_at": song_position_ms,
            "delete": False,
            "exiting": False,
            "style": random.getrandbits(16) % self.SPARKLE_VARIANTS,
        }
        speed = self._random_between(self.MIN_SPEED_CM_S, self.MAX_SPEED_CM_S)
        angle = self._random_between(0.0, 2 * math.pi)
        sparkle["vx"] = speed * math.cos(angle)
        sparkle["vy"] = speed * math.sin(angle)
        self.sparkles.append(sparkle)

        current = [item for item in self.sparkles if not item["delete"]]
        if len(current) > self.MAX_CURRENT_SPARKLES:
            current[0]["delete"] = True

    def _random_between(self, low, high):
        return low + random.getrandbits(16) / 65535 * (high - low)

    def _update_gravity(self, acceleration):
        mpu_x, mpu_y, _mpu_z = acceleration
        scale = self.STANDARD_GRAVITY_CM_S2 * self.GRAVITY_FRACTION
        target_x = -mpu_y * scale
        target_y = -mpu_x * scale
        alpha = self.GRAVITY_SMOOTHING
        self.gravity_x += alpha * (target_x - self.gravity_x)
        self.gravity_y += alpha * (target_y - self.gravity_y)

    def _move(self, elapsed_seconds):
        low = self.radius_cm
        high_x = self.screen_width_cm - self.radius_cm
        high_y = self.screen_height_cm - self.radius_cm
        survivors = []
        for sparkle in self.sparkles:
            if not sparkle["exiting"]:
                sparkle["vx"] += self.gravity_x * elapsed_seconds
                sparkle["vy"] += self.gravity_y * elapsed_seconds
            sparkle["x"] += sparkle["vx"] * elapsed_seconds
            sparkle["y"] += sparkle["vy"] * elapsed_seconds

            if sparkle["delete"]:
                if (
                    sparkle["x"] <= low
                    or sparkle["x"] >= high_x
                    or sparkle["y"] <= low
                    or sparkle["y"] >= high_y
                ):
                    sparkle["exiting"] = True
                outside = (
                    sparkle["x"] < -self.radius_cm
                    or sparkle["x"] > self.screen_width_cm + self.radius_cm
                    or sparkle["y"] < -self.radius_cm
                    or sparkle["y"] > self.screen_height_cm + self.radius_cm
                )
                if not outside:
                    survivors.append(sparkle)
                continue

            if sparkle["x"] <= low:
                sparkle["x"] = low + (low - sparkle["x"])
                sparkle["vx"] = abs(sparkle["vx"]) * self.RESTITUTION
            elif sparkle["x"] >= high_x:
                sparkle["x"] = high_x - (sparkle["x"] - high_x)
                sparkle["vx"] = -abs(sparkle["vx"]) * self.RESTITUTION
            if sparkle["y"] <= low:
                sparkle["y"] = low + (low - sparkle["y"])
                sparkle["vy"] = abs(sparkle["vy"]) * self.RESTITUTION
            elif sparkle["y"] >= high_y:
                sparkle["y"] = high_y - (sparkle["y"] - high_y)
                sparkle["vy"] = -abs(sparkle["vy"]) * self.RESTITUTION
            survivors.append(sparkle)
        self.sparkles = survivors

    def render(self, canvas, context):
        for sparkle in self.sparkles:
            canvas.sparkle(
                round(sparkle["x"] / self.cm_per_pixel_x),
                round(sparkle["y"] / self.cm_per_pixel_y),
                self.RADIUS_PX,
                1,
                sparkle["style"],
            )

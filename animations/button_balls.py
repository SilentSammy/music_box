"""Spawn IMU-driven bouncing balls with depth represented by size."""
import random

from animation import Animation, EVENT_CONSUMED, EVENT_DIRTY
from events import BUTTON_PRESSED


class ButtonBalls(Animation):
    opaque = True

    MAX_BALLS = 4
    BALL_RADIUS_PX = 6
    MIN_RADIUS_PX = 1.0
    XY_ACCEL_PX_S2_PER_G = 140.0
    DEPTH_ACCEL_PX_S2_PER_G = 20.0
    GRAVITY_SMOOTHING = 0.20
    RESTITUTION = 1.0
    MAX_ELAPSED_MS = 100
    MAX_PHYSICS_STEP_S = 0.01

    def __init__(self):
        self.balls = []
        self.order_index = None
        self.spawn_order = ()
        self.width = 0
        self.height = 0
        self.max_radius = self.BALL_RADIUS_PX
        self.gravity_x = 0.0
        self.gravity_y = 0.0
        self.gravity_z = 0.0

    def on_enter(self, context):
        self.width = context.canvas.width
        self.height = context.canvas.height
        self.max_radius = max(
            self.MIN_RADIUS_PX,
            min(self.width, self.height) / 2.0 - 1.0,
        )
        self.balls = []
        self.gravity_x = 0.0
        self.gravity_y = 0.0
        self.gravity_z = 0.0
        self._choose_order()

    def _orders(self):
        slots = tuple(range(self.MAX_BALLS))
        middle_out = tuple(
            sorted(slots, key=lambda index: (abs(2 * index - self.MAX_BALLS + 1), index))
        )
        edges_in = []
        left = 0
        right = self.MAX_BALLS - 1
        while left <= right:
            edges_in.append(left)
            if right != left:
                edges_in.append(right)
            left += 1
            right -= 1
        return (
            slots,
            tuple(reversed(slots)),
            middle_out,
            tuple(edges_in),
        )

    def _choose_order(self):
        orders = self._orders()
        if self.order_index is None or len(orders) == 1:
            candidate = random.getrandbits(8) % len(orders)
        else:
            candidate = random.getrandbits(8) % (len(orders) - 1)
            if candidate >= self.order_index:
                candidate += 1
        self.order_index = candidate
        self.spawn_order = orders[candidate]

    def on_event(self, event, context):
        if event.type != BUTTON_PRESSED:
            return 0

        if len(self.balls) >= self.MAX_BALLS:
            self._choose_order()
            self.balls = []
        self._spawn_ball()
        return EVENT_DIRTY | EVENT_CONSUMED

    def _spawn_ball(self):
        slot = self.spawn_order[len(self.balls)]
        self.balls.append({
            "x": (slot + 1) * self.width / (self.MAX_BALLS + 1),
            "y": self.height / 2.0,
            "vx": 0.0,
            "vy": 0.0,
            "radius": float(self.BALL_RADIUS_PX),
            "radius_velocity": 0.0,
        })

    def _update_gravity(self, acceleration):
        mpu_x, mpu_y, mpu_z = acceleration
        alpha = self.GRAVITY_SMOOTHING
        target_x = -mpu_y * self.XY_ACCEL_PX_S2_PER_G
        target_y = -mpu_x * self.XY_ACCEL_PX_S2_PER_G
        target_z = -mpu_z * self.DEPTH_ACCEL_PX_S2_PER_G
        self.gravity_x += alpha * (target_x - self.gravity_x)
        self.gravity_y += alpha * (target_y - self.gravity_y)
        self.gravity_z += alpha * (target_z - self.gravity_z)

    @staticmethod
    def _reflect(value, velocity, low, high):
        if high <= low:
            return (low + high) / 2.0, 0.0
        while value < low or value > high:
            if value < low:
                value = low + (low - value)
                velocity = abs(velocity)
            elif value > high:
                value = high - (value - high)
                velocity = -abs(velocity)
        return value, velocity

    def _move(self, elapsed_s):
        for ball in self.balls:
            ball["vx"] += self.gravity_x * elapsed_s
            ball["vy"] += self.gravity_y * elapsed_s
            ball["radius_velocity"] += self.gravity_z * elapsed_s

            ball["x"] += ball["vx"] * elapsed_s
            ball["y"] += ball["vy"] * elapsed_s
            ball["radius"] += ball["radius_velocity"] * elapsed_s

            radius, radius_velocity = self._reflect(
                ball["radius"],
                ball["radius_velocity"] * self.RESTITUTION,
                self.MIN_RADIUS_PX,
                self.max_radius,
            )
            ball["radius"] = radius
            ball["radius_velocity"] = radius_velocity

            ball["x"], ball["vx"] = self._reflect(
                ball["x"],
                ball["vx"] * self.RESTITUTION,
                radius,
                self.width - 1.0 - radius,
            )
            ball["y"], ball["vy"] = self._reflect(
                ball["y"],
                ball["vy"] * self.RESTITUTION,
                radius,
                self.height - 1.0 - radius,
            )

    def update(self, context):
        if context.input.imu_updated:
            self._update_gravity(context.input.accel)

        remaining = min(context.dt_ms, self.MAX_ELAPSED_MS) / 1000.0
        while remaining > 0.0:
            step = min(remaining, self.MAX_PHYSICS_STEP_S)
            self._move(step)
            remaining -= step
        return bool(self.balls and context.dt_ms)

    def render(self, canvas, context):
        for ball in self.balls:
            canvas.circle(
                round(ball["x"]),
                round(ball["y"]),
                max(1, round(ball["radius"])),
                1,
            )

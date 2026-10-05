"""IMU-driven snow-globe animation with drag and terminal velocity."""
import math
import random

from animation import Animation


class FallingSnow(Animation):
    opaque = True

    SPAWN_INTERVAL_MS = 450
    MAX_FLAKES = 24
    ENTRY_TIMEOUT_MS = 4000
    MIN_RADIUS_PX = 3
    MAX_RADIUS_PX = 7
    MIN_INITIAL_SPEED_PX_S = 2.0
    MAX_INITIAL_SPEED_PX_S = 6.0
    MIN_TERMINAL_SPEED_PX_S = 18.0
    MAX_TERMINAL_SPEED_PX_S = 28.0

    # IMU acceleration is reported in g. These constants turn it into
    # display-scale motion rather than literal physical-size motion.
    GRAVITY_ACCEL_PX_S2 = 38.0
    SHAKE_ACCEL_PX_S2 = 90.0
    MAX_SHAKE_G = 1.5
    SHAKE_JERK_DEAD_ZONE_G = 0.08
    SHAKE_IMPULSE_PX_S_PER_G = 10.0
    MAX_SHAKE_IMPULSE_PX_S = 12.0
    DRAG_PER_S = 1.6

    GRAVITY_FILTER = 0.06
    TILT_DEAD_ZONE_G = 0.08
    FLAT_HOLD_MS = 1000
    FLAT_BLEND_MS = 1500
    FALLBACK_GRAVITY_G = 0.45

    MIN_SWAY_ACCEL_PX_S2 = 4.0
    MAX_SWAY_ACCEL_PX_S2 = 10.0
    MIN_SWAY_PERIOD_S = 1.8
    MAX_SWAY_PERIOD_S = 4.5
    MAX_ELAPSED_MS = 100
    VARIANT_COUNT = 8

    def __init__(self):
        self.flakes = []
        self.width = 0
        self.height = 0
        self.filtered_gravity_x = 0.0
        self.filtered_gravity_y = 0.0
        self.shake_x = 0.0
        self.shake_y = 0.0
        self.previous_raw_x = None
        self.previous_raw_y = None
        self.shake_impulse_x = 0.0
        self.shake_impulse_y = 0.0
        self.effective_gravity_x = 0.0
        self.effective_gravity_y = self.FALLBACK_GRAVITY_G
        self.last_gravity_x = 0.0
        self.last_gravity_y = self.FALLBACK_GRAVITY_G
        self.flat_ms = 0

    def on_enter(self, context):
        self.width = context.canvas.width
        self.height = context.canvas.height
        self.flakes = []
        self.filtered_gravity_x = 0.0
        self.filtered_gravity_y = 0.0
        self.shake_x = 0.0
        self.shake_y = 0.0
        self.previous_raw_x = None
        self.previous_raw_y = None
        self.shake_impulse_x = 0.0
        self.shake_impulse_y = 0.0
        self.effective_gravity_x = 0.0
        self.effective_gravity_y = self.FALLBACK_GRAVITY_G
        self.last_gravity_x = 0.0
        self.last_gravity_y = self.FALLBACK_GRAVITY_G
        self.flat_ms = 0
        self._spawn()
        context.scheduler.every(
            self.SPAWN_INTERVAL_MS,
            self._on_spawn_timer,
            owner=self,
            catch_up=False,
        )

    def on_exit(self, context):
        self.flakes = []

    def _on_spawn_timer(self, event, context):
        if len(self.flakes) < self.MAX_FLAKES:
            self._spawn()
            return True
        return False

    def _random_between(self, low, high):
        return low + random.getrandbits(16) / 65535 * (high - low)

    def _spawn(self):
        radius = self.MIN_RADIUS_PX + (
            random.getrandbits(8)
            % (self.MAX_RADIUS_PX - self.MIN_RADIUS_PX + 1)
        )
        # The branched artwork can reach one pixel beyond its nominal radius.
        extent = 2 * max(2, radius // 2) + 1
        direction_x, direction_y = self._gravity_direction()
        x, y = self._upstream_position(direction_x, direction_y, extent)
        initial_speed = self._random_between(
            self.MIN_INITIAL_SPEED_PX_S,
            self.MAX_INITIAL_SPEED_PX_S,
        )
        period = self._random_between(
            self.MIN_SWAY_PERIOD_S,
            self.MAX_SWAY_PERIOD_S,
        )
        self.flakes.append({
            "x": x,
            "y": y,
            "vx": direction_x * initial_speed,
            "vy": direction_y * initial_speed,
            "entered": False,
            "age_ms": 0,
            "radius": radius,
            "extent": extent,
            "terminal_speed": self._random_between(
                self.MIN_TERMINAL_SPEED_PX_S,
                self.MAX_TERMINAL_SPEED_PX_S,
            ),
            "shake_response": self._random_between(0.85, 1.15),
            "sway_accel": self._random_between(
                self.MIN_SWAY_ACCEL_PX_S2,
                self.MAX_SWAY_ACCEL_PX_S2,
            ),
            "phase": self._random_between(0.0, 2.0 * math.pi),
            "angular_speed": 2.0 * math.pi / period,
            "style": random.getrandbits(8) % self.VARIANT_COUNT,
        })

    def _gravity_direction(self):
        magnitude = math.sqrt(
            self.effective_gravity_x * self.effective_gravity_x
            + self.effective_gravity_y * self.effective_gravity_y
        )
        if magnitude < 0.001:
            return 0.0, 1.0
        return (
            self.effective_gravity_x / magnitude,
            self.effective_gravity_y / magnitude,
        )

    def _upstream_position(self, direction_x, direction_y, extent):
        outside = extent + 1.0
        if abs(direction_x) > abs(direction_y):
            y = self._random_between(extent, self.height - extent)
            x = -outside if direction_x > 0 else self.width + outside
        else:
            x = self._random_between(extent, self.width - extent)
            y = -outside if direction_y > 0 else self.height + outside
        return x, y

    def _read_imu(self, acceleration):
        mpu_x, mpu_y, _mpu_z = acceleration
        # Both axes are negated for the physical MPU/display orientation.
        raw_x = -mpu_y
        raw_y = -mpu_x
        if self.previous_raw_x is not None:
            jerk_x = raw_x - self.previous_raw_x
            jerk_y = raw_y - self.previous_raw_y
            jerk_magnitude = math.sqrt(jerk_x * jerk_x + jerk_y * jerk_y)
            if jerk_magnitude > self.SHAKE_JERK_DEAD_ZONE_G:
                active_jerk = jerk_magnitude - self.SHAKE_JERK_DEAD_ZONE_G
                impulse_scale = (
                    active_jerk
                    * self.SHAKE_IMPULSE_PX_S_PER_G
                    / jerk_magnitude
                )
                impulse_x = jerk_x * impulse_scale
                impulse_y = jerk_y * impulse_scale
                impulse_magnitude = math.sqrt(
                    impulse_x * impulse_x + impulse_y * impulse_y
                )
                if impulse_magnitude > self.MAX_SHAKE_IMPULSE_PX_S:
                    limit_scale = (
                        self.MAX_SHAKE_IMPULSE_PX_S / impulse_magnitude
                    )
                    impulse_x *= limit_scale
                    impulse_y *= limit_scale
                self.shake_impulse_x += impulse_x
                self.shake_impulse_y += impulse_y
        self.previous_raw_x = raw_x
        self.previous_raw_y = raw_y

        alpha = self.GRAVITY_FILTER
        self.filtered_gravity_x += alpha * (
            raw_x - self.filtered_gravity_x
        )
        self.filtered_gravity_y += alpha * (
            raw_y - self.filtered_gravity_y
        )
        self.shake_x = raw_x - self.filtered_gravity_x
        self.shake_y = raw_y - self.filtered_gravity_y

        shake_magnitude = math.sqrt(
            self.shake_x * self.shake_x + self.shake_y * self.shake_y
        )
        if shake_magnitude > self.MAX_SHAKE_G:
            scale = self.MAX_SHAKE_G / shake_magnitude
            self.shake_x *= scale
            self.shake_y *= scale

    def _update_effective_gravity(self, elapsed_ms):
        gravity_x = self.filtered_gravity_x
        gravity_y = self.filtered_gravity_y
        magnitude = math.sqrt(gravity_x * gravity_x + gravity_y * gravity_y)

        if magnitude >= self.TILT_DEAD_ZONE_G:
            self.flat_ms = 0
            if magnitude > 1.0:
                gravity_x /= magnitude
                gravity_y /= magnitude
            self.last_gravity_x = gravity_x
            self.last_gravity_y = gravity_y
            self.effective_gravity_x = gravity_x
            self.effective_gravity_y = gravity_y
            return

        self.flat_ms += elapsed_ms
        if self.flat_ms <= self.FLAT_HOLD_MS:
            self.effective_gravity_x = self.last_gravity_x
            self.effective_gravity_y = self.last_gravity_y
            return

        blend = min(
            1.0,
            (self.flat_ms - self.FLAT_HOLD_MS) / self.FLAT_BLEND_MS,
        )
        self.effective_gravity_x = self.last_gravity_x * (1.0 - blend)
        self.effective_gravity_y = (
            self.last_gravity_y * (1.0 - blend)
            + self.FALLBACK_GRAVITY_G * blend
        )

    def update(self, context):
        if context.input.imu_updated:
            self._read_imu(context.input.accel)

        elapsed_ms = min(context.dt_ms, self.MAX_ELAPSED_MS)
        if elapsed_ms <= 0:
            return False
        self._update_effective_gravity(elapsed_ms)
        elapsed_s = elapsed_ms / 1000.0
        direction_x, direction_y = self._gravity_direction()
        perpendicular_x = -direction_y
        perpendicular_y = direction_x
        gravity_ax = self.effective_gravity_x * self.GRAVITY_ACCEL_PX_S2
        gravity_ay = self.effective_gravity_y * self.GRAVITY_ACCEL_PX_S2
        shake_ax = self.shake_x * self.SHAKE_ACCEL_PX_S2
        shake_ay = self.shake_y * self.SHAKE_ACCEL_PX_S2
        shake_impulse_x = self.shake_impulse_x
        shake_impulse_y = self.shake_impulse_y
        self.shake_impulse_x = 0.0
        self.shake_impulse_y = 0.0
        drag = max(0.0, 1.0 - self.DRAG_PER_S * elapsed_s)
        survivors = []

        for flake in self.flakes:
            flake["age_ms"] += elapsed_ms
            flake["phase"] += flake["angular_speed"] * elapsed_s
            sway = flake["sway_accel"] * math.sin(flake["phase"])
            flake["vx"] += (
                gravity_ax + shake_ax + perpendicular_x * sway
            ) * elapsed_s
            flake["vy"] += (
                gravity_ay + shake_ay + perpendicular_y * sway
            ) * elapsed_s
            shake_response = flake["shake_response"]
            flake["vx"] += shake_impulse_x * shake_response
            flake["vy"] += shake_impulse_y * shake_response
            flake["vx"] *= drag
            flake["vy"] *= drag
            self._limit_velocity(flake)
            flake["x"] += flake["vx"] * elapsed_s
            flake["y"] += flake["vy"] * elapsed_s
            if not flake["entered"]:
                flake["entered"] = self._intersects_screen(flake)
                if flake["entered"] or flake["age_ms"] < self.ENTRY_TIMEOUT_MS:
                    survivors.append(flake)
            elif not self._fully_outside(flake):
                survivors.append(flake)

        self.flakes = survivors
        return bool(self.flakes)

    def _limit_velocity(self, flake):
        speed = math.sqrt(
            flake["vx"] * flake["vx"] + flake["vy"] * flake["vy"]
        )
        if speed > flake["terminal_speed"]:
            scale = flake["terminal_speed"] / speed
            flake["vx"] *= scale
            flake["vy"] *= scale

    def _fully_outside(self, flake):
        extent = flake["extent"]
        return (
            flake["x"] + extent < 0
            or flake["x"] - extent > self.width
            or flake["y"] + extent < 0
            or flake["y"] - extent > self.height
        )

    def _intersects_screen(self, flake):
        extent = flake["extent"]
        return (
            flake["x"] + extent >= 0
            and flake["x"] - extent < self.width
            and flake["y"] + extent >= 0
            and flake["y"] - extent < self.height
        )

    def render(self, canvas, context):
        for flake in self.flakes:
            canvas.snowflake(
                round(flake["x"]),
                round(flake["y"]),
                flake["radius"],
                1,
                flake["style"],
            )

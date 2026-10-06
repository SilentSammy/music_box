"""IMU-oriented heart with damped rotational inertia."""
import math

from animation import Animation


class SpinningHeart(Animation):
    """Keep a heart upright against X/Y gravity while allowing it to swing."""

    opaque = True

    GRAVITY_FILTER = 0.16
    TILT_DEAD_ZONE_G = 0.08
    SPRING_PER_S2 = 30.0
    DAMPING_PER_S = 5.0
    GYRO_DRIVE_PER_S = 5.0
    MAX_ANGULAR_SPEED = 4.0 * math.pi
    MAX_ELAPSED_MS = 100
    MAX_PHYSICS_STEP_S = 0.01

    HEART_POINTS = (
        (0.0, -5.0),
        (-4.0, -10.0),
        (-9.0, -10.0),
        (-13.0, -6.0),
        (-13.0, -1.0),
        (-10.0, 5.0),
        (0.0, 14.0),
        (10.0, 5.0),
        (13.0, -1.0),
        (13.0, -6.0),
        (9.0, -10.0),
        (4.0, -10.0),
    )

    def __init__(self):
        self.center_x = 0
        self.center_y = 0
        self.angle = 0.0
        self.target_angle = 0.0
        self.angular_velocity = 0.0
        self.gyro_rate = 0.0
        self.gravity_x = 0.0
        self.gravity_y = 0.0

    def on_enter(self, context):
        self.center_x = context.canvas.width // 2
        self.center_y = context.canvas.height // 2
        self.angle = 0.0
        self.target_angle = 0.0
        self.angular_velocity = 0.0
        self.gyro_rate = 0.0
        self.gravity_x = 0.0
        self.gravity_y = 0.0

    @staticmethod
    def _wrap_angle(angle):
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def _read_imu(self, acceleration, gyroscope):
        mpu_x, mpu_y, _mpu_z = acceleration
        raw_x = -mpu_y
        raw_y = -mpu_x
        alpha = self.GRAVITY_FILTER
        self.gravity_x += alpha * (raw_x - self.gravity_x)
        self.gravity_y += alpha * (raw_y - self.gravity_y)

        magnitude = math.sqrt(
            self.gravity_x * self.gravity_x
            + self.gravity_y * self.gravity_y
        )
        if magnitude >= self.TILT_DEAD_ZONE_G:
            self.target_angle = math.atan2(
                -self.gravity_x,
                self.gravity_y,
            )
        else:
            self.target_angle = 0.0
        self.gyro_rate = -gyroscope[2] * math.pi / 180.0

    def _step(self, elapsed_s):
        error = self._wrap_angle(self.target_angle - self.angle)
        angular_acceleration = (
            self.SPRING_PER_S2 * error
            - self.DAMPING_PER_S * self.angular_velocity
            + self.GYRO_DRIVE_PER_S * self.gyro_rate
        )
        self.angular_velocity += angular_acceleration * elapsed_s
        self.angular_velocity = max(
            -self.MAX_ANGULAR_SPEED,
            min(self.MAX_ANGULAR_SPEED, self.angular_velocity),
        )
        self.angle = self._wrap_angle(
            self.angle + self.angular_velocity * elapsed_s
        )

    def update(self, context):
        if context.input.imu_updated:
            self._read_imu(context.input.accel, context.input.gyro)
        remaining = min(context.dt_ms, self.MAX_ELAPSED_MS) / 1000.0
        if remaining <= 0.0:
            return False
        while remaining > 0.0:
            step = min(remaining, self.MAX_PHYSICS_STEP_S)
            self._step(step)
            remaining -= step
        return True

    def _rotated_points(self, scale=1.0):
        cosine = math.cos(self.angle)
        sine = math.sin(self.angle)
        points = []
        for source_x, source_y in self.HEART_POINTS:
            source_x *= scale
            source_y *= scale
            points.append((
                round(self.center_x + source_x * cosine - source_y * sine),
                round(self.center_y + source_x * sine + source_y * cosine),
            ))
        return points

    @staticmethod
    def _draw_loop(canvas, points):
        previous_x, previous_y = points[-1]
        for point_x, point_y in points:
            canvas.line(previous_x, previous_y, point_x, point_y, 1)
            previous_x, previous_y = point_x, point_y

    def render(self, canvas, context):
        self._draw_loop(canvas, self._rotated_points(1.0))
        self._draw_loop(canvas, self._rotated_points(0.72))
        canvas.pixel(self.center_x, self.center_y + 1, 1)

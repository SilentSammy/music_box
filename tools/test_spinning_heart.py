"""Host tests for the IMU-driven spinning-heart animation."""
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock


APP = Path(__file__).resolve().parents[1] / "animations"
sys.path.insert(0, str(APP))

from spinning_heart import SpinningHeart


def context(accel=(0.0, 0.0, 1.0), gyro=(0.0, 0.0, 0.0),
            dt_ms=0, imu_updated=True):
    return types.SimpleNamespace(
        canvas=types.SimpleNamespace(width=128, height=64),
        input=types.SimpleNamespace(
            accel=accel,
            gyro=gyro,
            imu_updated=imu_updated,
        ),
        dt_ms=dt_ms,
    )


class SpinningHeartTests(unittest.TestCase):
    def heart(self):
        heart = SpinningHeart()
        heart.on_enter(context())
        return heart

    def test_display_down_gravity_keeps_heart_upright(self):
        heart = self.heart()
        for _ in range(20):
            heart._read_imu((-1.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(heart.target_angle, 0.0, places=5)

    def test_display_right_gravity_points_heart_left(self):
        heart = self.heart()
        for _ in range(20):
            heart._read_imu((0.0, -1.0, 0.0), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(heart.target_angle, -math.pi / 2.0, places=5)

    def test_flat_device_defaults_to_screen_up(self):
        heart = self.heart()
        heart.target_angle = 1.0
        heart._read_imu((0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
        self.assertEqual(heart.target_angle, 0.0)

    def test_gyro_kick_creates_rotation(self):
        heart = self.heart()
        heart._read_imu((0.0, 0.0, 1.0), (0.0, 0.0, 120.0))
        heart._step(0.02)
        self.assertLess(heart.angular_velocity, 0.0)

    def test_displaced_heart_oscillates_and_settles(self):
        heart = self.heart()
        heart.angle = 1.0
        crossed_upright = False
        previous = heart.angle
        for _ in range(800):
            heart._step(0.01)
            if previous * heart.angle < 0.0:
                crossed_upright = True
            previous = heart.angle
        self.assertTrue(crossed_upright)
        self.assertLess(abs(heart.angle), 0.001)
        self.assertLess(abs(heart.angular_velocity), 0.001)

    def test_render_draws_two_closed_outlines(self):
        heart = self.heart()
        canvas = MagicMock()
        heart.render(canvas, context())
        self.assertEqual(
            canvas.line.call_count,
            len(heart.HEART_POINTS) * 2,
        )
        canvas.pixel.assert_called_once()


if __name__ == "__main__":
    unittest.main()

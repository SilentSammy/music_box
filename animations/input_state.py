"""One consistent hardware-input snapshot per engine iteration."""
import time

from events import BUTTON_PRESSED, BUTTON_RELEASED, ENCODER, Event


class InputState:
    __slots__ = (
        "timestamp_ms",
        "encoder_position",
        "encoder_delta",
        "button_down",
        "button_pressed",
        "button_released",
        "button_held_ms",
        "accel",
        "gyro",
        "magnetometer",
        "imu_updated",
    )

    def __init__(self):
        self.timestamp_ms = 0
        self.encoder_position = 0
        self.encoder_delta = 0
        self.button_down = False
        self.button_pressed = False
        self.button_released = False
        self.button_held_ms = 0
        self.accel = (0.0, 0.0, 1.0)
        self.gyro = (0.0, 0.0, 0.0)
        self.magnetometer = None
        self.imu_updated = False


class InputSampler:
    IMU_INTERVAL_MS = 20

    def __init__(self, hardware):
        self.hardware = hardware
        self.state = InputState()
        self._last_imu_read = time.ticks_add(
            time.ticks_ms(),
            -self.IMU_INTERVAL_MS,
        )
        self._button_down_since = None

    def sample(self, now_ms):
        state = self.state
        state.timestamp_ms = now_ms
        state.encoder_delta = self.hardware.encoder.take_delta()
        state.encoder_position += state.encoder_delta
        state.button_pressed = bool(self.hardware.encoder.take_presses())
        state.button_released = False
        state.imu_updated = False
        events = []

        was_down = state.button_down
        state.button_down = self.hardware.encoder.button_down()
        if state.button_down and not was_down:
            state.button_pressed = True
        elif was_down and not state.button_down:
            state.button_released = True

        if state.button_pressed:
            self._button_down_since = now_ms
            events.append(Event(BUTTON_PRESSED, True, now_ms))
        if state.button_released:
            events.append(Event(BUTTON_RELEASED, False, now_ms))
            self._button_down_since = None

        if state.button_down and self._button_down_since is not None:
            state.button_held_ms = max(
                0,
                time.ticks_diff(now_ms, self._button_down_since),
            )
        else:
            state.button_held_ms = 0

        if state.encoder_delta:
            events.append(Event(ENCODER, state.encoder_delta, now_ms))

        if time.ticks_diff(now_ms, self._last_imu_read) >= self.IMU_INTERVAL_MS:
            self._last_imu_read = now_ms
            state.accel = self.hardware.imu.read_accel()
            state.gyro = self.hardware.imu.read_gyro()
            magnetometer = self.hardware.magnetometer
            state.magnetometer = (
                magnetometer.read_magnetometer()
                if magnetometer is not None
                else None
            )
            state.imu_updated = True

        return state, events

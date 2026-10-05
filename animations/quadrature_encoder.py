"""IRQ-driven rotary encoder with a debounced pushbutton."""
import machine
from machine import Pin
import time


_QUADRATURE_TRANSITIONS = (
    0, -1, 1, 0,
    1, 0, 0, -1,
    -1, 0, 0, 1,
    0, 1, -1, 0,
)


class Encoder:
    def __init__(
        self,
        clk_pin,
        dt_pin,
        sw_pin,
        debounce_ms=35,
        detent_ms=3,
    ):
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)

        now = time.ticks_ms()
        self._position = 0
        self._rotation_accumulator = 0
        self._last_state = self.clk.value() * 2 + self.dt.value()
        self._debounce_ms = debounce_ms
        self._detent_ms = detent_ms
        self._last_detent_time = time.ticks_add(now, -detent_ms)
        self._button_raw = self.sw.value()
        self._button_stable = self._button_raw
        self._button_changed_at = now
        self._presses = 0

        edges = Pin.IRQ_RISING | Pin.IRQ_FALLING
        self.clk.irq(trigger=edges, handler=self._on_rotate)
        self.dt.irq(trigger=edges, handler=self._on_rotate)
        self.sw.irq(trigger=edges, handler=self._on_button_edge)

    def _on_rotate(self, pin):
        state = self.clk.value() * 2 + self.dt.value()
        transition = _QUADRATURE_TRANSITIONS[self._last_state * 4 + state]
        if transition:
            self._rotation_accumulator += transition
            if abs(self._rotation_accumulator) >= 4:
                now = time.ticks_ms()
                if time.ticks_diff(now, self._last_detent_time) >= self._detent_ms:
                    self._position += (
                        1 if self._rotation_accumulator > 0 else -1
                    )
                    self._last_detent_time = now
                self._rotation_accumulator = 0
        elif state != self._last_state:
            self._rotation_accumulator = 0
        self._last_state = state

    def _on_button_edge(self, pin):
        now = time.ticks_ms()
        raw = self.sw.value()
        if raw != self._button_raw:
            self._button_raw = raw
            self._button_changed_at = now

    def _poll_button(self):
        now = time.ticks_ms()
        raw = self.sw.value()
        if raw != self._button_raw:
            self._button_raw = raw
            self._button_changed_at = now
        if (
            raw != self._button_stable
            and time.ticks_diff(now, self._button_changed_at)
            >= self._debounce_ms
        ):
            self._button_stable = raw
            if raw == 0:
                self._presses += 1

    def button_down(self):
        self._poll_button()
        return self._button_stable == 0

    def take_delta(self):
        irq_state = machine.disable_irq()
        delta = self._position
        self._position = 0
        machine.enable_irq(irq_state)
        return delta

    def take_presses(self):
        self._poll_button()
        presses = self._presses
        self._presses = 0
        return presses

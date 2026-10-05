"""Rotary encoder (KY-040 style) with debounced pushbutton.

Validated wiring: CLK=GPIO3, DT=GPIO4, SW=GPIO5, all Pin.IN + Pin.PULL_UP.

Rotation is decoded with a Gray-code state-transition table: state is
clk.value()*2 + dt.value() (0-3), and we only count a step when we land
on state 3 coming from state 2 (CW) or state 1 (CCW). This ignores
switch-bounce noise on its own -- no extra debounce timer needed for
rotation. The button's bounce is unrelated to the quadrature signal, so
it gets its own simple time-based debounce.
"""
from machine import Pin
import time


class Encoder:
    def __init__(self, clk_pin, dt_pin, sw_pin, debounce_ms=150):
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)

        self.position = 0
        self.presses = 0
        self._last_state = self.clk.value() * 2 + self.dt.value()
        self._debounce_ms = debounce_ms
        self._last_press_time = time.ticks_ms()

        self.clk.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self._on_rotate)
        self.dt.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self._on_rotate)
        self.sw.irq(trigger=Pin.IRQ_FALLING, handler=self._on_press)

    def _on_rotate(self, pin):
        state = self.clk.value() * 2 + self.dt.value()
        if state == 3:
            if self._last_state == 2:
                self.position += 1
            elif self._last_state == 1:
                self.position -= 1
        self._last_state = state

    def _on_press(self, pin):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_press_time) > self._debounce_ms:
            self.presses += 1
            self._last_press_time = now

    def take_delta(self):
        """Net position change since the last call; resets the counter."""
        d = self.position
        self.position = 0
        return d

    def take_presses(self):
        """Number of button presses since the last call; resets the counter."""
        p = self.presses
        self.presses = 0
        return p

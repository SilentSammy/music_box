"""Animation stack, input/event loop, compositing, and OLED flushing."""
import time

from animation import AnimationContext, EVENT_CONSUMED, EVENT_DIRTY
from canvas import Canvas
from input_state import InputSampler
from scheduler import Scheduler


class AnimationEngine:
    def __init__(self, hardware, frames_per_second=20):
        self.hardware = hardware
        self.canvas = Canvas(hardware.display)
        self.scheduler = Scheduler()
        self.input_sampler = InputSampler(hardware)
        self.context = AnimationContext(
            self.input_sampler.state,
            self.canvas,
            self.scheduler,
            hardware,
        )
        self.layers = []
        self.frame_interval_ms = max(1, 1000 // frames_per_second)
        self.last_update = time.ticks_ms()
        self.next_frame = self.last_update
        self.dirty = True
        self.closed = False

    def push(self, animation):
        self.layers.append(animation)
        animation.on_enter(self.context)
        self.dirty = True
        return animation

    def pop(self):
        if not self.layers:
            return None
        animation = self.layers.pop()
        self.scheduler.cancel_owner(animation)
        animation.on_exit(self.context)
        self.dirty = True
        return animation

    def post(self, event):
        self.dirty = self._dispatch_event(event) or self.dirty

    def invalidate(self):
        self.dirty = True

    def _dispatch_event(self, event):
        dirty = False
        for animation in reversed(self.layers):
            result = animation.on_event(event, self.context) or 0
            dirty = bool(result & EVENT_DIRTY) or dirty
            if result & EVENT_CONSUMED or animation.blocks_input:
                break
        return dirty

    def _first_updating_layer(self):
        for index in range(len(self.layers) - 1, -1, -1):
            if self.layers[index].pauses_below:
                return index
        return 0

    def _first_rendering_layer(self):
        for index in range(len(self.layers) - 1, -1, -1):
            animation = self.layers[index]
            if animation.visible and animation.opaque:
                return index
        return 0

    def _update(self, now_ms):
        context = self.context
        context.now_ms = now_ms
        context.dt_ms = max(0, time.ticks_diff(now_ms, self.last_update))
        self.last_update = now_ms

        state, events = self.input_sampler.sample(now_ms)
        context.input = state
        for event in events:
            self.dirty = self._dispatch_event(event) or self.dirty

        self.dirty = self.scheduler.update(now_ms, context) or self.dirty
        start = self._first_updating_layer()
        for animation in self.layers[start:]:
            self.dirty = bool(animation.update(context)) or self.dirty

    def _render(self):
        self.canvas.clear()
        start = self._first_rendering_layer()
        for animation in self.layers[start:]:
            if animation.visible:
                animation.render(self.canvas, self.context)
        self.hardware.display.show()
        self.dirty = False

    def run(self, max_frames=None):
        frames = 0
        while max_frames is None or frames < max_frames:
            now_ms = time.ticks_ms()
            self._update(now_ms)
            if (
                self.dirty
                and time.ticks_diff(now_ms, self.next_frame) >= 0
            ):
                self._render()
                frames += 1
                self.next_frame = time.ticks_add(
                    now_ms,
                    self.frame_interval_ms,
                )
            time.sleep_ms(5)
        return frames

    def close(self):
        if self.closed:
            return
        while self.layers:
            self.pop()
        self.canvas.clear()
        self.hardware.display.show()
        self.hardware.close()
        self.closed = True

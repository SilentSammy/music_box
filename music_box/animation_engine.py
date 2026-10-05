"""Embeddable animation stack for Music Box playback screens."""
import time

from animation import AnimationContext, EVENT_CONSUMED, EVENT_DIRTY
from canvas import Canvas
from input_state import InputSampler
from scheduler import Scheduler


class AnimationEngine:
    def __init__(
        self,
        hardware,
        song_state,
        frames_per_second=20,
        service_callback=None,
        render_guard=None,
    ):
        self.hardware = hardware
        self.canvas = Canvas(hardware.display)
        self.scheduler = Scheduler()
        self.input_sampler = InputSampler(hardware)
        self.context = AnimationContext(
            self.input_sampler.state,
            song_state,
            self.canvas,
            self.scheduler,
            hardware,
        )
        self.layers = []
        self.frame_interval_ms = max(1, 1000 // frames_per_second)
        self.service_callback = service_callback
        self.render_guard = render_guard
        self.last_update = time.ticks_ms()
        self.next_frame = self.last_update
        self.dirty = False

    def reset_clock(self, now_ms=None):
        if now_ms is None:
            now_ms = time.ticks_ms()
        self.last_update = now_ms
        self.next_frame = now_ms
        self.input_sampler.reset(now_ms)
        self.dirty = True

    def push(self, animation):
        self.layers.append(animation)
        animation.on_enter(self.context)
        self.dirty = True
        return animation

    def clear_layers(self):
        while self.layers:
            animation = self.layers.pop()
            self.scheduler.cancel_owner(animation)
            animation.on_exit(self.context)
        self.dirty = False

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

    def step(self, now_ms=None):
        if now_ms is None:
            now_ms = time.ticks_ms()
        context = self.context
        context.now_ms = now_ms
        context.dt_ms = max(0, time.ticks_diff(now_ms, self.last_update))
        self.last_update = now_ms

        state, events = self.input_sampler.sample(now_ms)
        context.input = state
        for event in events:
            self.dirty = self._dispatch_event(event) or self.dirty

        self.dirty = self.scheduler.update(now_ms, context) or self.dirty
        start = 0
        for index in range(len(self.layers) - 1, -1, -1):
            if self.layers[index].pauses_below:
                start = index
                break
        for animation in self.layers[start:]:
            self.dirty = bool(animation.update(context)) or self.dirty

        if self.dirty and time.ticks_diff(now_ms, self.next_frame) >= 0:
            if self.render_guard is not None and not self.render_guard(now_ms):
                return False
            self._render()
            self.next_frame = time.ticks_add(now_ms, self.frame_interval_ms)
            return True
        return False

    def _render(self):
        self.canvas.clear()
        start = 0
        for index in range(len(self.layers) - 1, -1, -1):
            layer = self.layers[index]
            if layer.visible and layer.opaque:
                start = index
                break
        for animation in self.layers[start:]:
            if animation.visible:
                animation.render(self.canvas, self.context)
        self.hardware.display.show(self.service_callback)
        self.dirty = False

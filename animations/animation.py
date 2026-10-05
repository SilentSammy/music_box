"""Base animation and shared frame context."""


EVENT_DIRTY = 0x01
EVENT_CONSUMED = 0x02


class AnimationContext:
    __slots__ = (
        "now_ms",
        "dt_ms",
        "input",
        "canvas",
        "scheduler",
        "hardware",
    )

    def __init__(self, input_state, canvas, scheduler, hardware):
        self.now_ms = 0
        self.dt_ms = 0
        self.input = input_state
        self.canvas = canvas
        self.scheduler = scheduler
        self.hardware = hardware


class Animation:
    """Minimal lifecycle shared by full animations and overlay layers."""

    opaque = False
    blocks_input = False
    pauses_below = False
    visible = True

    def on_enter(self, context):
        pass

    def on_exit(self, context):
        pass

    def on_event(self, event, context):
        return 0

    def update(self, context):
        return False

    def render(self, canvas, context):
        pass

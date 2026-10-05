"""Small event objects used by the animation engine."""


TIMER = 1
ENCODER = 2
BUTTON_PRESSED = 3
BUTTON_RELEASED = 4
BEAT = 5
MEASURE = 6
SONG_STARTED = 7
SONG_ENDED = 8


class Event:
    __slots__ = ("type", "value", "timestamp_ms", "source")

    def __init__(self, event_type, value=None, timestamp_ms=0, source=None):
        self.type = event_type
        self.value = value
        self.timestamp_ms = timestamp_ms
        self.source = source

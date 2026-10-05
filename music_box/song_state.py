"""Shared, read-only-by-convention song state for animations."""


class SongState:
    __slots__ = (
        "playing",
        "title",
        "path",
        "started_at",
        "position_ms",
        "duration_ms",
        "tempo_us",
        "numerator",
        "denominator",
        "ticks_per_beat",
        "beat_index",
        "measure_index",
        "voices",
        "melody_note",
        "melody_velocity",
        "melody_level",
        "event_flags",
    )

    def __init__(self):
        self.reset()

    def reset(self, title=None, path=None):
        self.playing = False
        self.title = title
        self.path = path
        self.started_at = None
        self.position_ms = 0
        self.duration_ms = 0
        self.tempo_us = 500_000
        self.numerator = 4
        self.denominator = 4
        self.ticks_per_beat = 0
        self.beat_index = -1
        self.measure_index = -1
        self.voices = ((0, 0, 0),) * 4
        self.melody_note = 0
        self.melody_velocity = 0
        self.melody_level = 0
        self.event_flags = 0

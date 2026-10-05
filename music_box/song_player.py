"""Non-blocking four-voice passive-buzzer song playback."""
from machine import Pin, PWM
import math
import struct
import time

from song_state import SongState


BUZZER_PINS = (5, 9, 10, 20)
MAX_TONE_DUTY = 32_768

MAGIC = b"MSNG"
FORMAT_VERSION = 3
VOICE_COUNT = 4
HEADER_FORMAT = ">4sBBHHII"
HEADER_SIZE = 18
RECORD_FORMAT_V2 = ">IBIBB12B"
RECORD_FORMAT_V3 = ">IBIBB15B"
RECORD_SIZE_V2 = 23
RECORD_SIZE_V3 = 26

FLAG_BEAT = 0x01
FLAG_MEASURE = 0x02
FLAG_TEMPO = 0x04
FLAG_TIME_SIGNATURE = 0x08
FLAG_END = 0x10
FLAG_NOTE_ONSET = 0x20
FLAG_MELODY_ONSET = 0x40


def note_frequency(note):
    return round(440 * math.pow(2, (note - 69) / 12))


def volume_duty(volume):
    """Match the cubic response used by the Music Box volume preview."""
    normalized = max(0, min(100, volume)) / 100
    return round(MAX_TONE_DUTY * normalized ** 3)


class SongPlayer:
    def __init__(self, pins=BUZZER_PINS):
        self.pins = pins
        self.voices = [PWM(Pin(pin), freq=440, duty_u16=0) for pin in pins]
        self._frequencies = [440] * len(pins)
        self.song = None
        self.deadline = None
        self.master_duty = 0
        self.playing = False
        self.previewing = False
        self.started_at = None
        self.next_record = None
        self.records_remaining = 0
        self.record_events = []
        self.state = SongState()
        self.record_format = RECORD_FORMAT_V3
        self.record_size = RECORD_SIZE_V3
        # None plays every voice; 0-3 isolates one physical buzzer.
        self.voice_filter = None

        # Timing information exposed for future synchronized animations.
        self.event_flags = 0
        self.position_ms = 0
        self.duration_ms = 0
        self.tempo_us = 500_000
        self.numerator = 4
        self.denominator = 4
        self.ticks_per_beat = 0

    def silence(self):
        for voice in self.voices:
            voice.duty_u16(0)

    def set_voice_filter(self, voice_index=None):
        if voice_index is not None and not 0 <= voice_index < VOICE_COUNT:
            raise ValueError("voice index must be 0-3 or None")
        self.voice_filter = voice_index
        if self.playing:
            self._apply_voices(self.state.voices)

    def _apply_voices(self, voices):
        # Release changed channels before assigning new frequencies. On C3 all
        # four timers may already be occupied; freq() can seek a fifth timer.
        changed = []
        for index, (note, _unused, level) in enumerate(voices):
            enabled = self.voice_filter is None or self.voice_filter == index
            if enabled and note and level:
                frequency = note_frequency(note)
                if frequency != self._frequencies[index]:
                    self.voices[index].deinit()
                    changed.append((index, frequency))
        for index, frequency in changed:
            self.voices[index] = PWM(Pin(self.pins[index]), freq=frequency, duty_u16=0)
            self._frequencies[index] = frequency
        for index, output in enumerate(self.voices):
            note, _unused, level = voices[index]
            enabled = self.voice_filter is None or self.voice_filter == index
            if enabled and note and level:
                output.duty_u16(self.master_duty * level // 127)
            else:
                output.duty_u16(0)

    def start(self, path, volume, title=None):
        self.stop()
        self.song = open(path, "rb")
        header = self.song.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE:
            self.stop()
            raise ValueError("Incomplete song header")
        (
            magic,
            version,
            voice_count,
            record_size,
            self.ticks_per_beat,
            self.records_remaining,
            self.duration_ms,
        ) = struct.unpack(HEADER_FORMAT, header)
        if (
            magic != MAGIC
            or version not in (2, FORMAT_VERSION)
            or voice_count != VOICE_COUNT
            or (
                version == 2 and record_size != RECORD_SIZE_V2
            )
            or (
                version == FORMAT_VERSION and record_size != RECORD_SIZE_V3
            )
        ):
            self.stop()
            raise ValueError("Unsupported song format")
        self.record_format = (
            RECORD_FORMAT_V2 if version == 2 else RECORD_FORMAT_V3
        )
        self.record_size = record_size

        self.master_duty = volume_duty(volume)
        self.started_at = time.ticks_ms()
        self.position_ms = 0
        self.event_flags = 0
        self.record_events = []
        self.state.reset(title, path)
        self.state.playing = True
        self.state.started_at = self.started_at
        self.state.duration_ms = self.duration_ms
        self.state.ticks_per_beat = self.ticks_per_beat
        self.playing = True
        self._read_next_record()
        self.update(self.started_at)

    def preview_note(self, note, volume, duration_ms=250, voice_index=0):
        if not 0 <= voice_index < len(self.voices):
            raise ValueError("invalid preview buzzer")
        self.stop()
        frequency = note_frequency(note)
        if self._frequencies[voice_index] != frequency:
            self.voices[voice_index].deinit()
            self.voices[voice_index] = PWM(Pin(self.pins[voice_index]), freq=frequency, duty_u16=0)
            self._frequencies[voice_index] = frequency
        self.voices[voice_index].duty_u16(volume_duty(volume))
        self.previewing = True
        self.deadline = time.ticks_add(time.ticks_ms(), duration_ms)

    def update(self, now_ms=None):
        self.event_flags = 0
        self.record_events = []
        self.state.event_flags = 0
        if now_ms is None:
            now_ms = time.ticks_ms()
        if self.deadline is None:
            pass
        else:
            if time.ticks_diff(now_ms, self.deadline) >= 0 and self.previewing:
                self.silence()
                self.previewing = False
                self.deadline = None

        if not self.playing:
            return

        elapsed_ms = max(0, time.ticks_diff(now_ms, self.started_at))
        self.position_ms = min(elapsed_ms, self.duration_ms)
        self.state.position_ms = self.position_ms
        while self.next_record is not None and self.next_record[0] <= elapsed_ms:
            record = self.next_record
            self.event_flags |= record[1]
            self.tempo_us = record[2]
            self.numerator = record[3]
            self.denominator = record[4]

            voice_data = record[5:17]
            voices = tuple(
                tuple(voice_data[index:index + 3])
                for index in range(0, len(voice_data), 3)
            )
            melody = record[17:20] if len(record) >= 20 else (0, 0, 0)
            self.record_events.append((record[0], record[1], voices, melody))
            self.state.event_flags |= record[1]
            self.state.tempo_us = self.tempo_us
            self.state.numerator = self.numerator
            self.state.denominator = self.denominator
            self.state.voices = voices
            self.state.melody_note = melody[0]
            self.state.melody_velocity = melody[1]
            self.state.melody_level = melody[2]
            if record[1] & FLAG_BEAT:
                self.state.beat_index += 1
            if record[1] & FLAG_MEASURE:
                self.state.measure_index += 1
            self._apply_voices(voices)

            ended = bool(record[1] & FLAG_END)
            self._read_next_record()
            if ended or self.next_record is None:
                self._finish_song()
                break

    def time_until_next_record(self, now_ms=None):
        if not self.playing or self.next_record is None:
            return None
        if now_ms is None:
            now_ms = time.ticks_ms()
        elapsed_ms = max(0, time.ticks_diff(now_ms, self.started_at))
        return self.next_record[0] - elapsed_ms

    def _read_next_record(self):
        if not self.records_remaining:
            self.next_record = None
            return
        packed = self.song.read(self.record_size)
        if len(packed) != self.record_size:
            self.stop()
            raise ValueError("Incomplete song record")
        self.next_record = struct.unpack(self.record_format, packed)
        self.records_remaining -= 1

    def _finish_song(self):
        self.silence()
        if self.song is not None:
            self.song.close()
            self.song = None
        self.playing = False
        self.state.playing = False
        self.state.position_ms = self.duration_ms
        self.next_record = None
        self.started_at = None

    def stop(self):
        self.silence()
        if self.song is not None:
            self.song.close()
            self.song = None
        self.playing = False
        self.previewing = False
        self.deadline = None
        self.started_at = None
        self.next_record = None
        self.records_remaining = 0
        self.event_flags = 0
        self.record_events = []
        self.state.reset()

    def close(self):
        self.stop()
        for voice in self.voices:
            voice.deinit()

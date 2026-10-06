"""Interactively play and isolate every separable MIDI component.

A component is a note-bearing (source track, MIDI channel) pair. This separates
different channels within format-0/single-track files and also separates tracks
that reuse the same channel.

Examples:
    python tools/play_midi_channels.py "mid/Maroon_5This_Love.mid"
    python tools/play_midi_channels.py song.mid --port 1 --no-loop
    python tools/play_midi_channels.py --list-ports

The screen assigns one key to every discovered component. Other controls:
[ and ] cycle playback speed, Space pauses, z restarts, a mutes/unmutes all,
l toggles looping, and x/Esc quits.
Terminal input is read one key at a time without blocking playback.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
import os
import sys
import time

import mido


# Lower/upper-case variants are distinct keys. Reserve all transport controls.
COMPONENT_KEYS = (
    "1234567890qwertyuiopsdfghjkcvbnm,./;-="
    "!@#$%^&*()QWERTYUIOPSDFGHJKCVBNM<>?:{}+_"
)

PLAYBACK_SPEEDS = (-2.0, -1.0, 0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


@dataclass(frozen=True)
class Component:
    index: int
    key: str
    track: int
    channel: int
    name: str
    notes: int
    programs: tuple[int, ...]


@dataclass(frozen=True)
class TimedMessage:
    seconds: float
    message: mido.Message
    component: int | None


def discover_components(midi: mido.MidiFile) -> list[Component]:
    raw = []
    for track_index, track in enumerate(midi.tracks):
        name = next(
            (message.name for message in track if message.type == "track_name"),
            "Track %d" % (track_index + 1),
        )
        channels = defaultdict(lambda: {"notes": 0, "programs": set()})
        for message in track:
            channel = getattr(message, "channel", None)
            if channel is None:
                continue
            if message.type == "program_change":
                channels[channel]["programs"].add(message.program)
            elif message.type == "note_on" and message.velocity:
                channels[channel]["notes"] += 1
        for channel, details in sorted(channels.items()):
            if details["notes"]:
                raw.append((track_index, channel, name, details))
    if len(raw) > len(COMPONENT_KEYS):
        raise ValueError(
            "MIDI has %d components but this terminal key map supports %d"
            % (len(raw), len(COMPONENT_KEYS))
        )
    return [
        Component(
            index=index,
            key=COMPONENT_KEYS[index],
            track=track,
            channel=channel,
            name=name,
            notes=details["notes"],
            programs=tuple(sorted(details["programs"])),
        )
        for index, (track, channel, name, details) in enumerate(raw)
    ]


def timed_messages(
    midi: mido.MidiFile, components: list[Component]
) -> tuple[list[TimedMessage], float]:
    """Resolve tempo while retaining each message's source track and channel."""
    source_map = {
        (component.track, component.channel): component.index
        for component in components
    }
    absolute = []
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        for order, message in enumerate(track):
            tick += message.time
            absolute.append((tick, track_index, order, message))
    absolute.sort(key=lambda item: (item[0], item[1], item[2]))

    tempo = 500_000
    previous_tick = 0
    elapsed = 0.0
    result = []
    for tick, track_index, _order, message in absolute:
        elapsed += mido.tick2second(
            tick - previous_tick, midi.ticks_per_beat, tempo
        )
        previous_tick = tick
        if message.type == "set_tempo":
            tempo = message.tempo
        elif not message.is_meta:
            channel = getattr(message, "channel", None)
            component = source_map.get((track_index, channel))
            result.append(TimedMessage(
                elapsed, message.copy(time=0), component
            ))
    return result, elapsed


class NonBlockingKeys(AbstractContextManager):
    """Raw single-key input on Windows and POSIX, restored on every exit path."""
    def __enter__(self):
        if os.name == "nt":
            import msvcrt
            self._msvcrt = msvcrt
        else:
            import termios
            import tty
            self._termios = termios
            self._fd = sys.stdin.fileno()
            self._original = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def read(self):
        if os.name == "nt":
            if not self._msvcrt.kbhit():
                return None
            key = self._msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                if self._msvcrt.kbhit():
                    self._msvcrt.getwch()
                return None
            return key
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def __exit__(self, *exc_info):
        if os.name != "nt":
            self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._original)
        return False


class MidiPlayer:
    def __init__(self, output, events, duration, components, loop=True):
        self.output = output
        self.events = events
        self.duration = duration
        self.components = components
        self.key_map = {component.key: component.index for component in components}
        self.enabled = [True] * len(components)
        self.active = [defaultdict(int) for _ in components]
        self.loop = loop
        self.paused = False
        self.finished = False
        self.index = 0
        self.position = 0.0
        self.speed_index = PLAYBACK_SPEEDS.index(1.0)
        self.last_clock = time.monotonic()
        self.reverse_messages = self._make_reverse_messages()

    @property
    def speed(self):
        return PLAYBACK_SPEEDS[self.speed_index]

    def _make_reverse_messages(self):
        """Create the note action needed when each event is crossed backward."""
        pending = defaultdict(list)
        result = [None] * len(self.events)
        for index, event in enumerate(self.events):
            message = event.message
            if event.component is None or message.type not in ("note_on", "note_off"):
                continue
            key = (event.component, message.note)
            is_on = message.type == "note_on" and message.velocity > 0
            if is_on:
                pending[key].append(message.velocity)
                result[index] = mido.Message(
                    "note_off", channel=message.channel, note=message.note,
                    velocity=0,
                )
            else:
                velocity = pending[key].pop(0) if pending[key] else 64
                result[index] = mido.Message(
                    "note_on", channel=message.channel, note=message.note,
                    velocity=velocity,
                )
        return result

    def send(self, message):
        raw = message.bytes()
        if message.type == "sysex":
            self.output.write_sys_ex(0, bytes(raw))
        elif len(raw) == 1:
            self.output.write_short(raw[0])
        elif len(raw) == 2:
            self.output.write_short(raw[0], raw[1])
        else:
            self.output.write_short(raw[0], raw[1], raw[2])

    def panic(self, channel=None):
        channels = range(16) if channel is None else (channel,)
        for value in channels:
            for control in (64, 120, 123):
                self.output.write_short(0xB0 | value, control, 0)

    def _other_enabled_note(self, component_index, note):
        channel = self.components[component_index].channel
        return any(
            index != component_index
            and self.enabled[index]
            and component.channel == channel
            and self.active[index].get(note, 0)
            for index, component in enumerate(self.components)
        )

    def _process_event(self, event):
        message = event.message
        component_index = event.component
        if component_index is None:
            self.send(message)
            return
        enabled = self.enabled[component_index]
        if message.type == "note_on" and message.velocity:
            self.active[component_index][message.note] += 1
            if enabled:
                self.send(message)
            return
        if message.type == "note_off" or (
            message.type == "note_on" and not message.velocity
        ):
            count = self.active[component_index].get(message.note, 0)
            if count > 1:
                self.active[component_index][message.note] = count - 1
            elif count:
                del self.active[component_index][message.note]
            if enabled and not self._other_enabled_note(component_index, message.note):
                self.send(message)
            return
        # Keep setup current while muted. Suppress expressive messages that
        # would alter another component sharing the same MIDI channel.
        if enabled or message.type in ("program_change", "control_change"):
            self.send(message)

    def _process_reverse_event(self, event_index):
        message = self.reverse_messages[event_index]
        if message is None:
            return
        event = self.events[event_index]
        component_index = event.component
        enabled = self.enabled[component_index]
        if message.type == "note_on":
            self.active[component_index][message.note] += 1
            if enabled:
                self.send(message)
            return
        count = self.active[component_index].get(message.note, 0)
        if count > 1:
            self.active[component_index][message.note] = count - 1
        elif count:
            del self.active[component_index][message.note]
        if enabled and not self._other_enabled_note(component_index, message.note):
            self.send(message)

    def _restore_notes(self):
        """Resume notes spanning the current position after a transport stop."""
        sounding = [defaultdict(list) for _ in self.components]
        for event in self.events[:self.index]:
            message = event.message
            if event.component is None or message.type not in ("note_on", "note_off"):
                continue
            notes = sounding[event.component][message.note]
            if message.type == "note_on" and message.velocity:
                notes.append(message.velocity)
            elif notes:
                notes.pop(0)

        self.active = [defaultdict(int) for _ in self.components]
        sent = set()
        for component_index, notes in enumerate(sounding):
            component = self.components[component_index]
            for note, velocities in notes.items():
                if not velocities:
                    continue
                self.active[component_index][note] = len(velocities)
                key = (component.channel, note)
                if self.enabled[component_index] and key not in sent:
                    self.send(mido.Message(
                        "note_on", channel=component.channel, note=note,
                        velocity=velocities[-1],
                    ))
                    sent.add(key)

    def _seek(self, position, restore=False):
        from bisect import bisect_right

        self.panic()
        self.active = [defaultdict(int) for _ in self.components]
        self.position = min(self.duration, max(0.0, position))
        self.index = bisect_right(
            [event.seconds for event in self.events], self.position
        )
        self.last_clock = time.monotonic()
        self.finished = False
        if restore and self.speed and not self.paused:
            self._restore_notes()

    def toggle_component(self, component_index):
        self.enabled[component_index] = not self.enabled[component_index]
        if self.enabled[component_index]:
            return
        component = self.components[component_index]
        for note in tuple(self.active[component_index]):
            if not self._other_enabled_note(component_index, note):
                self.output.write_short(0x80 | component.channel, note, 0)
        if not any(
            self.enabled[index] and other.channel == component.channel
            for index, other in enumerate(self.components)
        ):
            self.panic(component.channel)

    def toggle_all(self):
        turn_on = not any(self.enabled)
        self.enabled[:] = [turn_on] * len(self.components)
        if not turn_on:
            self.panic()

    def restart(self):
        self._seek(0.0)

    def toggle_pause(self):
        if self.paused:
            self.paused = False
            self.last_clock = time.monotonic()
            if self.speed:
                self._restore_notes()
        else:
            self.paused = True
            self.panic()
            self.active = [defaultdict(int) for _ in self.components]

    def cycle_speed(self, change):
        self.speed_index = (self.speed_index + change) % len(PLAYBACK_SPEEDS)
        self.panic()
        self.active = [defaultdict(int) for _ in self.components]
        self.last_clock = time.monotonic()
        if self.speed and not self.paused:
            self._restore_notes()

    def update(self):
        if self.paused or self.finished:
            return
        now = time.monotonic()
        elapsed = now - self.last_clock
        self.last_clock = now
        speed = self.speed
        if not speed:
            return
        new_position = self.position + elapsed * speed
        if speed > 0:
            target = min(new_position, self.duration)
            while self.index < len(self.events) and self.events[self.index].seconds <= target:
                self._process_event(self.events[self.index])
                self.index += 1
            self.position = target
            if new_position >= self.duration:
                if self.loop:
                    self._seek(0.0)
                else:
                    self.panic()
                    self.finished = True
        else:
            target = max(new_position, 0.0)
            while self.index > 0 and self.events[self.index - 1].seconds > target:
                self.index -= 1
                self._process_reverse_event(self.index)
            self.position = target
            if new_position <= 0.0:
                if self.loop:
                    self._seek(self.duration)
                else:
                    self.panic()
                    self.finished = True

    def handle_key(self, key):
        if key in self.key_map:
            self.toggle_component(self.key_map[key])
            return True
        control = key.lower()
        if key == " ":
            self.toggle_pause()
        elif key == "[":
            self.cycle_speed(-1)
        elif key == "]":
            self.cycle_speed(1)
        elif control == "z":
            self.restart()
        elif control == "a":
            self.toggle_all()
        elif control == "l":
            self.loop = not self.loop
        elif control == "x" or key == "\x1b":
            return False
        return True


def render(player, source, force=False):
    now = time.monotonic()
    if not force and now < getattr(render, "next_at", 0):
        return
    render.next_at = now + 0.5
    state = "PAUSED" if player.paused or not player.speed else "FINISHED" if player.finished else "PLAYING"
    direction = "reverse" if player.speed < 0 else "forward" if player.speed > 0 else "stopped"
    lines = [
        "Interactive MIDI component player",
        str(source),
        "%s  %6.1f / %6.1f sec  Speed: %g (%s)  Loop: %s" % (
            state, min(player.position, player.duration), player.duration,
            player.speed, direction,
            "on" if player.loop else "off",
        ),
        "",
        "Key  State Part  Source                    Notes",
    ]
    for component in player.components:
        marker = "ON " if player.enabled[component.index] else "off"
        source_name = "T%02d/C%02d %s" % (
            component.track + 1, component.channel + 1, component.name
        )
        lines.append("%-3s  %-3s  %02d    %-25.25s %6d" % (
            component.key, marker, component.index + 1,
            source_name, component.notes
        ))
    lines.extend([
        "",
        "Each key toggles one note-bearing track/channel component.",
        "[ slower | ] faster | Space pause/resume | z restart | a all off/on",
        "l loop | x/Esc quit",
    ])
    sys.stdout.write("\x1b[2J\x1b[H" + "\n".join(lines) + "\n")
    sys.stdout.flush()


def list_ports(pygame_midi):
    for port in range(pygame_midi.get_count()):
        interface, name, is_input, is_output, opened = pygame_midi.get_device_info(port)
        if is_output:
            print("%d: %s (%s)%s" % (
                port, name.decode(errors="replace"),
                interface.decode(errors="replace"),
                " [open]" if opened else "",
            ))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path, nargs="?")
    parser.add_argument("--port", type=int, help="pygame MIDI output port index")
    parser.add_argument("--no-loop", action="store_true")
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        import pygame.midi
    except ImportError as error:
        parser.error("pygame is required for MIDI output: %s" % error)
    pygame.midi.init()
    try:
        if args.list_ports:
            list_ports(pygame.midi)
            return 0
        if args.midi is None:
            parser.error("a MIDI file is required unless --list-ports is used")
        midi = mido.MidiFile(args.midi)
        components = discover_components(midi)
        if not components:
            parser.error("MIDI contains no note-bearing track/channel components")
        events, duration = timed_messages(midi, components)
        port = args.port if args.port is not None else pygame.midi.get_default_output_id()
        if port < 0:
            parser.error("no MIDI output found; use --list-ports")
        output = pygame.midi.Output(port, latency=0)
        player = MidiPlayer(
            output, events, duration, components, not args.no_loop
        )
        try:
            with NonBlockingKeys() as keys:
                running = True
                render(player, args.midi, force=True)
                while running:
                    player.update()
                    key = keys.read()
                    if key is not None:
                        running = player.handle_key(key)
                        render(player, args.midi, force=True)
                    else:
                        render(player, args.midi)
                    time.sleep(0.002)
        except KeyboardInterrupt:
            pass
        finally:
            player.panic()
            output.close()
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
        return 0
    finally:
        pygame.midi.quit()


if __name__ == "__main__":
    raise SystemExit(main())

"""Convert Standard MIDI files into Music Box .song files.

The output is a compact, versioned event stream for the MicroPython player.
It preserves note-on velocity, effective channel volume, tempo, time
signature, beats, and calculated measure boundaries.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
import struct

import mido


MAGIC = b"MSNG"
VERSION = 3
VOICE_COUNT = 4

FLAG_BEAT = 0x01
FLAG_MEASURE = 0x02
FLAG_TEMPO = 0x04
FLAG_TIME_SIGNATURE = 0x08
FLAG_END = 0x10
FLAG_NOTE_ONSET = 0x20
FLAG_MELODY_ONSET = 0x40

HEADER = struct.Struct(">4sBBHHII")
RECORD = struct.Struct(">IBIBB15B")

DEFAULT_TEMPO = 500_000
DEFAULT_NUMERATOR = 4
DEFAULT_DENOMINATOR = 4
DEFAULT_CHANNEL_VOLUME = 100
DEFAULT_EXPRESSION = 127


def _absolute_events(midi):
    events = defaultdict(list)
    max_tick = 0
    signatures = {}

    for track_index, track in enumerate(midi.tracks):
        tick = 0
        for order, message in enumerate(track):
            tick += message.time
            max_tick = max(max_tick, tick)
            events[tick].append((track_index, order, message))
            if message.type == "time_signature":
                signatures[tick] = (message.numerator, message.denominator)

    if 0 not in signatures:
        signatures[0] = (DEFAULT_NUMERATOR, DEFAULT_DENOMINATOR)
    return events, max_tick, sorted(signatures.items())


def _note_spans(midi, max_tick):
    """Pair source note events while retaining track/channel identity."""
    pending = defaultdict(list)
    notes = []
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        for message in track:
            tick += message.time
            if not hasattr(message, "channel") or message.channel == 9:
                continue
            key = (track_index, message.channel, getattr(message, "note", -1))
            if message.type == "note_on" and message.velocity:
                pending[key].append((tick, message.velocity))
            elif message.type == "note_off" or (
                message.type == "note_on" and not message.velocity
            ):
                starts = pending.get(key)
                if starts:
                    start_tick, velocity = starts.pop(0)
                    if tick > start_tick:
                        notes.append({
                            "track": track_index,
                            "channel": message.channel,
                            "note": message.note,
                            "velocity": velocity,
                            "start_tick": start_tick,
                            "end_tick": tick,
                        })
    for (track, channel, note), starts in pending.items():
        for start_tick, velocity in starts:
            if max_tick > start_tick:
                notes.append({
                    "track": track,
                    "channel": channel,
                    "note": note,
                    "velocity": velocity,
                    "start_tick": start_tick,
                    "end_tick": max_tick,
                })
    return notes


def _annotation_event_id(item):
    return (
        item["track"],
        item["channel"],
        item["tick"],
        item["note"],
    )


def _load_melody_annotation(path):
    if path is None:
        data = {"version": 1, "segments": []}
    else:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version", 1) != 1:
        raise ValueError("Unsupported melody annotation version")

    prepared_segments = []
    for segment in data.get("segments", ()):
        start = segment.get("start_tick", 0)
        end = segment.get("end_tick")
        if not isinstance(start, int) or start < 0:
            raise ValueError("melody segment start_tick must be a nonnegative int")
        if end is not None and (not isinstance(end, int) or end <= start):
            raise ValueError("melody segment end_tick must follow start_tick")
        selection = segment.get("selection", "highest")
        if selection not in ("highest", "lowest"):
            raise ValueError("melody selection must be highest or lowest")
        sources = {}
        for source in segment.get("sources", ()):
            key = (source["track"], source["channel"])
            sources[key] = int(source.get("priority", 0))
        prepared_segments.append({
            "start_tick": start,
            "end_tick": end,
            "selection": selection,
            "sources": sources,
        })

    data["_segments"] = prepared_segments
    data["_include"] = {
        _annotation_event_id(item) for item in data.get("include", ())
    }
    data["_exclude"] = {
        _annotation_event_id(item) for item in data.get("exclude", ())
    }
    return data


def _melody_state(notes, tick, annotation, channel_volume, expression):
    segment = None
    for candidate in annotation["_segments"]:
        end = candidate["end_tick"]
        if candidate["start_tick"] <= tick and (end is None or tick < end):
            segment = candidate
            break

    candidates = []
    for note in notes:
        if not note["start_tick"] <= tick < note["end_tick"]:
            continue
        event_id = (
            note["track"],
            note["channel"],
            note["start_tick"],
            note["note"],
        )
        if event_id in annotation["_exclude"]:
            continue
        if event_id in annotation["_include"]:
            priority = 1_000_000
        elif segment is not None:
            source = (note["track"], note["channel"])
            if source not in segment["sources"]:
                continue
            priority = segment["sources"][source]
        else:
            continue
        candidates.append((priority, note))

    if not candidates:
        return (0, 0, 0), False
    best_priority = max(priority for priority, _note in candidates)
    candidates = [note for priority, note in candidates if priority == best_priority]
    onset_candidates = [
        note for note in candidates if note["start_tick"] == tick
    ]
    melody_onset = bool(onset_candidates)
    if melody_onset:
        # Prefer notes that actually begin now. This preserves every onset
        # timestamp even when a higher note from the same-priority source is
        # still sounding, and collapses simultaneous chords to one event.
        candidates = onset_candidates
    selection = segment["selection"] if segment is not None else "highest"
    chooser = max if selection == "highest" else min
    chosen_pitch = chooser(note["note"] for note in candidates)
    same_pitch = [note for note in candidates if note["note"] == chosen_pitch]

    def effective_level(note):
        return round(
            note["velocity"]
            * channel_volume[note["channel"]]
            * expression[note["channel"]]
            / (127 * 127)
        )

    chosen = max(same_pitch, key=effective_level)
    level = max(0, min(127, effective_level(chosen)))
    state = (chosen["note"], chosen["velocity"], level)
    return state, melody_onset


def _metrical_flags(signatures, max_tick, ticks_per_beat):
    flags = defaultdict(int)
    for index, (start, (numerator, denominator)) in enumerate(signatures):
        end = signatures[index + 1][0] if index + 1 < len(signatures) else max_tick
        beat_ticks = Fraction(ticks_per_beat * 4, denominator)
        beat = Fraction(start)
        beat_index = 0
        while beat <= end:
            if beat == end and index + 1 < len(signatures):
                break
            flags[beat] |= FLAG_BEAT
            if beat_index % numerator == 0:
                flags[beat] |= FLAG_MEASURE
            beat += beat_ticks
            beat_index += 1
    return flags


def _remove_note(active, key):
    velocities = active.get(key)
    if not velocities:
        return
    velocities.pop(0)
    if not velocities:
        del active[key]


def _select_voices(active, channel_volume, expression):
    """Return bass plus the three highest unique pitches."""
    pitches = {}
    for (_track, channel, note), velocities in active.items():
        for velocity in velocities:
            level = round(
                velocity
                * channel_volume[channel]
                * expression[channel]
                / (127 * 127)
            )
            candidate = (velocity, max(0, min(127, level)))
            if note not in pitches or candidate[1] > pitches[note][1]:
                pitches[note] = candidate

    notes = sorted(pitches)
    if len(notes) > VOICE_COUNT:
        notes = [notes[0]] + notes[-(VOICE_COUNT - 1) :]

    voices = []
    for note in notes:
        velocity, level = pitches[note]
        voices.extend((note, velocity, level))
    voices.extend((0, 0, 0) * (VOICE_COUNT - len(notes)))
    return tuple(voices)


def convert(source, destination, melody=None):
    source = Path(source)
    destination = Path(destination)
    midi = mido.MidiFile(source)
    if not 0 < midi.ticks_per_beat <= 0xFFFF:
        raise ValueError("SMPTE or invalid MIDI time division is not supported")

    events, max_tick, signatures = _absolute_events(midi)
    notes = _note_spans(midi, max_tick)
    melody_annotation = _load_melody_annotation(melody)
    point_flags = _metrical_flags(signatures, max_tick, midi.ticks_per_beat)
    point_flags[Fraction(0)] |= FLAG_TEMPO | FLAG_TIME_SIGNATURE

    for tick, messages in events.items():
        for _track, _order, message in messages:
            if message.type == "set_tempo":
                point_flags[Fraction(tick)] |= FLAG_TEMPO
            elif message.type == "time_signature":
                point_flags[Fraction(tick)] |= FLAG_TIME_SIGNATURE

    timeline = sorted(set(Fraction(tick) for tick in events) | set(point_flags))
    active = {}
    channel_volume = defaultdict(lambda: DEFAULT_CHANNEL_VOLUME)
    expression = defaultdict(lambda: DEFAULT_EXPRESSION)
    tempo = DEFAULT_TEMPO
    numerator = DEFAULT_NUMERATOR
    denominator = DEFAULT_DENOMINATOR
    previous_tick = Fraction(0)
    elapsed_us = Fraction(0)
    previous_voices = None
    previous_melody = None
    records = []

    for tick in timeline:
        elapsed_us += (tick - previous_tick) * tempo / midi.ticks_per_beat
        previous_tick = tick
        state_changed = False
        note_onset = False

        for track_index, _order, message in events.get(tick, ()):
            if message.type == "set_tempo":
                tempo = message.tempo
            elif message.type == "time_signature":
                numerator = message.numerator
                denominator = message.denominator
            elif message.type == "control_change":
                if message.control == 7:
                    channel_volume[message.channel] = message.value
                    state_changed = True
                elif message.control == 11:
                    expression[message.channel] = message.value
                    state_changed = True
            elif message.type == "note_on" and message.channel != 9:
                key = (track_index, message.channel, message.note)
                if message.velocity:
                    active.setdefault(key, []).append(message.velocity)
                    note_onset = True
                else:
                    _remove_note(active, key)
                state_changed = True
            elif message.type == "note_off" and message.channel != 9:
                _remove_note(active, (track_index, message.channel, message.note))
                state_changed = True

        flags = point_flags.get(tick, 0)
        if note_onset:
            flags |= FLAG_NOTE_ONSET
        voices = _select_voices(active, channel_volume, expression)
        melody_state, melody_onset = _melody_state(
            notes,
            tick,
            melody_annotation,
            channel_volume,
            expression,
        )
        if melody_onset:
            flags |= FLAG_MELODY_ONSET
        if (
            not flags
            and (not state_changed or voices == previous_voices)
            and melody_state == previous_melody
        ):
            continue

        at_ms = int((elapsed_us + 500) / 1000)
        records.append(
            (
                at_ms,
                flags,
                tempo,
                numerator,
                denominator,
                *voices,
                *melody_state,
            )
        )
        previous_voices = voices
        previous_melody = melody_state

    duration_ms = int((elapsed_us + 500) / 1000)
    silent = (0, 0, 0) * VOICE_COUNT
    records.append(
        (
            duration_ms,
            FLAG_END,
            tempo,
            numerator,
            denominator,
            *silent,
            0,
            0,
            0,
        )
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        output.write(
            HEADER.pack(
                MAGIC,
                VERSION,
                VOICE_COUNT,
                RECORD.size,
                midi.ticks_per_beat,
                len(records),
                duration_ms,
            )
        )
        for record in records:
            output.write(RECORD.pack(*record))

    expected_size = HEADER.size + len(records) * RECORD.size
    if destination.stat().st_size != expected_size:
        raise RuntimeError("Song file size validation failed")

    measure_count = sum(bool(record[1] & FLAG_MEASURE) for record in records)
    beat_count = sum(bool(record[1] & FLAG_BEAT) for record in records)
    melody_count = sum(
        bool(record[1] & FLAG_MELODY_ONSET) for record in records
    )
    print(
        "%s: %d records, %d beats, %d measures, %d melody onsets, "
        "%.2f s, %d bytes"
        % (
            destination,
            len(records),
            beat_count,
            measure_count,
            melody_count,
            duration_ms / 1000,
            expected_size,
        )
    )


def convert_manifest(path):
    path = Path(path)
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        melody = entry.get("melody")
        convert(
            path.parent / entry["source"],
            path.parent / entry["output"],
            path.parent / melody if melody else None,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", help="input .mid file")
    parser.add_argument("destination", nargs="?", help="output .song file")
    parser.add_argument("--melody", help="melody annotation JSON")
    parser.add_argument("--manifest", help="JSON batch-conversion manifest")
    args = parser.parse_args()

    if args.manifest:
        if args.source or args.destination:
            parser.error("source/destination cannot be combined with --manifest")
        convert_manifest(args.manifest)
    elif args.source and args.destination:
        convert(args.source, args.destination, args.melody)
    else:
        parser.error("provide source and destination, or --manifest")


if __name__ == "__main__":
    main()

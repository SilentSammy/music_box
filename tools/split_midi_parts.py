"""Split MIDI files into auditionable track/channel parts.

Examples:
    python tools/split_midi_parts.py mid --output midi_parts
    python tools/split_midi_parts.py mid/song.mid

Every output MIDI contains one source (track, channel) pair plus a conductor
track carrying the original tempo, time-signature, and key-signature events.
This preserves useful separation in both format-1 files (many tracks) and
format-0 files (one track containing many channels).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import mido


TIMING_META_TYPES = {
    "set_tempo",
    "time_signature",
    "key_signature",
    "smpte_offset",
    "marker",
    "cue_marker",
}

GM_INSTRUMENTS = (
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord",
    "Clavinet", "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer", "Drawbar Organ",
    "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ", "Accordion",
    "Harmonica", "Tango Accordion", "Acoustic Guitar (nylon)",
    "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
    "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar",
    "Distortion Guitar", "Guitar Harmonics", "Acoustic Bass",
    "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2", "Violin",
    "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings",
    "Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2",
    "Synth Strings 1", "Synth Strings 2", "Choir Aahs", "Voice Oohs",
    "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba",
    "Muted Trumpet", "French Horn", "Brass Section", "Synth Brass 1",
    "Synth Brass 2", "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
    "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle",
    "Ocarina", "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)",
    "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)",
    "Lead 8 (bass + lead)", "Pad 1 (new age)", "Pad 2 (warm)",
    "Pad 3 (polysynth)", "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)",
    "Pad 7 (halo)", "Pad 8 (sweep)", "FX 1 (rain)", "FX 2 (soundtrack)",
    "FX 3 (crystal)", "FX 4 (atmosphere)", "FX 5 (brightness)",
    "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)", "Sitar", "Banjo",
    "Shamisen", "Koto", "Kalimba", "Bag pipe", "Fiddle", "Shanai",
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock", "Taiko Drum",
    "Melodic Tom", "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise",
    "Breath Noise", "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter",
    "Applause", "Gunshot",
)


def _slug(value, fallback):
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value[:48] or fallback


def _track_name(track, track_index):
    for message in track:
        if message.type == "track_name" and message.name.strip():
            return message.name.strip()
    return "Track %d" % (track_index + 1)


def _absolute_track(track):
    tick = 0
    for order, message in enumerate(track):
        tick += message.time
        yield tick, order, message


def _make_delta_track(events, end_tick, name):
    output = mido.MidiTrack()
    output.append(mido.MetaMessage("track_name", name=name, time=0))
    previous_tick = 0
    for tick, order, message in sorted(events, key=lambda item: (item[0], item[1])):
        if message.type in ("track_name", "end_of_track"):
            continue
        output.append(message.copy(time=tick - previous_tick))
        previous_tick = tick
    output.append(
        mido.MetaMessage(
            "end_of_track",
            time=max(0, end_tick - previous_tick),
        )
    )
    return output


def _part_statistics(events):
    notes = []
    programs = set()
    active = defaultdict(int)
    active_count = 0
    max_polyphony = 0

    for tick, order, message in sorted(events, key=lambda item: (item[0], item[1])):
        if message.type == "program_change":
            programs.add(message.program)
        elif message.type == "note_on" and message.velocity:
            notes.append(message.note)
            active[message.note] += 1
            active_count += 1
            max_polyphony = max(max_polyphony, active_count)
        elif message.type in ("note_off", "note_on"):
            if active[message.note]:
                active[message.note] -= 1
                active_count -= 1

    program_names = []
    for program in sorted(programs):
        program_names.append(GM_INSTRUMENTS[program])

    return {
        "notes": len(notes),
        "lowest_note": min(notes) if notes else None,
        "highest_note": max(notes) if notes else None,
        "max_polyphony": max_polyphony,
        "programs": sorted(programs),
        "program_names": program_names,
    }


def _remove_previous_parts(destination):
    """Remove only MIDI files named by our previous manifest."""
    manifest_path = destination / "parts.json"
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return
    for part in previous.get("parts", ()):
        filename = part.get("file") if isinstance(part, dict) else None
        if not filename or Path(filename).name != filename:
            continue
        path = destination / filename
        if path.suffix.lower() in (".mid", ".midi"):
            try:
                path.unlink()
            except OSError:
                pass


def split_midi(source, destination):
    source = Path(source)
    destination = Path(destination)
    midi = mido.MidiFile(source)

    conductor_events = []
    part_events = defaultdict(list)
    part_names = {}
    end_tick = 0

    for track_index, track in enumerate(midi.tracks):
        name = _track_name(track, track_index)
        for tick, order, message in _absolute_track(track):
            end_tick = max(end_tick, tick)
            global_order = track_index * 1_000_000 + order
            if message.is_meta:
                if message.type in TIMING_META_TYPES:
                    conductor_events.append((tick, global_order, message))
                continue
            if hasattr(message, "channel") and message.channel != 9:
                key = (track_index, message.channel)
                part_events[key].append((tick, order, message))
                part_names[key] = name

    # Ignore tracks/channels that contain setup messages but no musical notes.
    musical_parts = []
    for key, events in sorted(part_events.items()):
        statistics = _part_statistics(events)
        if statistics["notes"]:
            musical_parts.append((key, events, statistics))

    destination.mkdir(parents=True, exist_ok=True)
    _remove_previous_parts(destination)
    manifest_parts = []
    index_lines = [
        "MIDI parts for: %s" % source.name,
        "Each file contains one original track/channel pair.",
        "",
    ]

    for part_number, (key, events, statistics) in enumerate(musical_parts, 1):
        track_index, channel = key
        original_name = part_names[key]
        descriptive_name = original_name
        if statistics["program_names"] and (
            midi.type == 0
            or original_name == "Track %d" % (track_index + 1)
        ):
            descriptive_name = statistics["program_names"][0]

        filename = "%02d_t%02d_ch%02d_%s.mid" % (
            part_number,
            track_index + 1,
            channel + 1,
            _slug(descriptive_name, "part"),
        )
        output_path = destination / filename
        isolated = mido.MidiFile(type=1, ticks_per_beat=midi.ticks_per_beat)
        isolated.tracks.append(
            _make_delta_track(conductor_events, end_tick, "Conductor")
        )
        isolated.tracks.append(
            _make_delta_track(events, end_tick, descriptive_name)
        )
        isolated.save(output_path)

        entry = {
            "file": filename,
            "track": track_index + 1,
            "channel": channel + 1,
            "track_name": original_name,
            **statistics,
        }
        manifest_parts.append(entry)
        pitch_range = "%s-%s" % (
            statistics["lowest_note"],
            statistics["highest_note"],
        )
        programs = ", ".join(statistics["program_names"]) or "unspecified"
        index_lines.append(
            "%02d  %-32s track=%d channel=%d notes=%d range=%s "
            "max_polyphony=%d program=%s"
            % (
                part_number,
                filename,
                track_index + 1,
                channel + 1,
                statistics["notes"],
                pitch_range,
                statistics["max_polyphony"],
                programs,
            )
        )

    manifest = {
        "source": str(source),
        "midi_type": midi.type,
        "ticks_per_beat": midi.ticks_per_beat,
        "duration_seconds": midi.length,
        "parts": manifest_parts,
    }
    (destination / "parts.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (destination / "README.txt").write_text(
        "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )
    print("%s -> %s (%d parts)" % (source, destination, len(musical_parts)))
    return manifest


def split_path(source, output=None):
    source = Path(source)
    if source.is_file():
        destination = (
            Path(output)
            if output is not None
            else source.parent / (source.stem + "_parts")
        )
        return [split_midi(source, destination)]

    if not source.is_dir():
        raise FileNotFoundError(source)
    output_root = (
        Path(output)
        if output is not None
        else source.parent / (source.name + "_parts")
    )
    results = []
    midi_paths = sorted(
        path
        for path in source.iterdir()
        if path.is_file() and path.suffix.lower() in (".mid", ".midi")
    )
    for midi_path in midi_paths:
        results.append(
            split_midi(
                midi_path,
                output_root / _slug(midi_path.stem, "song"),
            )
        )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Split MIDI files into original track/channel parts."
    )
    parser.add_argument("source", help="a MIDI file or directory of MIDI files")
    parser.add_argument(
        "--output",
        help="output directory (defaults to <source>_parts)",
    )
    args = parser.parse_args()
    split_path(args.source, args.output)


if __name__ == "__main__":
    main()

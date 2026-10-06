"""Convenient MIDI-to-Music-Box converter with melody annotations.

Listen first:
    python tools/play_midi_channels.py "mid/Maroon_5_Animals.mid"

Then convert using the channel number(s) that carry the melody:
    python tools/convert_midi.py "mid/Maroon_5_Animals.mid" --melody 1
    python tools/convert_midi.py song.mid --melody 1,3 --selection highest
For files whose tracks reuse a channel, select player component numbers instead:
    python tools/convert_midi.py song.mid --melody-parts 4,9,11
For a song that cannot be annotated automatically:
    python tools/convert_midi.py song.mid --no-melody

`--melody` uses the same 1-based MIDI channel numbers displayed by the player.
`--melody-parts` uses the numbered track/channel components displayed by the
player, allowing individual tracks on a shared channel to be selected.
By default, output goes to music_box/songs/<midi-name>.song and its editable
annotation goes to tools/melodies/<midi-name>.melody.json.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import mido

from midi_to_song import convert
from split_midi_parts import GM_INSTRUMENTS


ROOT = Path(__file__).resolve().parents[1]


def slug(value):
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value or "song"


def parse_channels(value):
    channels = []
    for item in value.split(","):
        try:
            channel = int(item.strip())
        except ValueError as error:
            raise argparse.ArgumentTypeError("melody channels must be numbers") from error
        if not 1 <= channel <= 16:
            raise argparse.ArgumentTypeError("melody channels must be from 1 to 16")
        if channel not in channels:
            channels.append(channel)
    if not channels:
        raise argparse.ArgumentTypeError("provide at least one melody channel")
    return channels


def parse_parts(value):
    parts = []
    for item in value.split(","):
        try:
            part = int(item.strip())
        except ValueError as error:
            raise argparse.ArgumentTypeError("melody parts must be numbers") from error
        if part < 1:
            raise argparse.ArgumentTypeError("melody parts must be positive")
        if part not in parts:
            parts.append(part)
    if not parts:
        raise argparse.ArgumentTypeError("provide at least one melody part")
    return parts


def channel_sources(midi):
    """Return note-bearing source tracks grouped by 1-based MIDI channel."""
    result = defaultdict(list)
    for track_index, track in enumerate(midi.tracks):
        name = next(
            (message.name for message in track if message.type == "track_name"),
            "Track %d" % (track_index + 1),
        )
        grouped = defaultdict(lambda: {"notes": 0, "programs": set()})
        for message in track:
            channel = getattr(message, "channel", None)
            if channel is None:
                continue
            # The .song voice converter intentionally excludes General MIDI
            # percussion channel 10 because its note numbers are drum selectors.
            if channel == 9:
                continue
            if message.type == "program_change":
                grouped[channel]["programs"].add(message.program)
            elif message.type == "note_on" and message.velocity:
                grouped[channel]["notes"] += 1
        for channel, details in grouped.items():
            if details["notes"]:
                result[channel + 1].append({
                    "track": track_index,
                    "track_number": track_index + 1,
                    "channel": channel,
                    "name": name,
                    "notes": details["notes"],
                    "programs": sorted(details["programs"]),
                })
    return dict(result)


def part_sources(midi):
    """Return player-style note-bearing track/channel components in order."""
    result = []
    for track_index, track in enumerate(midi.tracks):
        name = next(
            (message.name for message in track if message.type == "track_name"),
            "Track %d" % (track_index + 1),
        )
        grouped = defaultdict(lambda: {"notes": 0, "programs": set()})
        for message in track:
            channel = getattr(message, "channel", None)
            if channel is None or channel == 9:
                continue
            if message.type == "program_change":
                grouped[channel]["programs"].add(message.program)
            elif message.type == "note_on" and message.velocity:
                grouped[channel]["notes"] += 1
        for channel, details in sorted(grouped.items()):
            if details["notes"]:
                result.append({
                    "part": len(result) + 1,
                    "track": track_index,
                    "track_number": track_index + 1,
                    "channel": channel,
                    "channel_number": channel + 1,
                    "name": name,
                    "notes": details["notes"],
                    "programs": sorted(details["programs"]),
                })
    return result


def describe_channels(sources):
    print("Available note channels:")
    for channel in sorted(sources):
        note_count = sum(item["notes"] for item in sources[channel])
        programs = sorted({program for item in sources[channel] for program in item["programs"]})
        instruments = ", ".join(GM_INSTRUMENTS[p] for p in programs) or "unspecified"
        tracks = ", ".join(
            "track %d: %s" % (item["track_number"], item["name"])
            for item in sources[channel]
        )
        print("  %2d  notes=%-5d %-28s %s" % (
            channel, note_count, instruments[:28], tracks,
        ))


def describe_parts(parts):
    print("Available note-bearing parts:")
    for item in parts:
        instruments = ", ".join(
            GM_INSTRUMENTS[program] for program in item["programs"]
        ) or "unspecified"
        print("  %02d  track=%-2d channel=%-2d notes=%-5d %-20.20s %s" % (
            item["part"], item["track_number"], item["channel_number"],
            item["notes"], instruments, item["name"],
        ))


def make_annotation(sources, channels, selection, source_name):
    selected = []
    for channel in channels:
        if channel not in sources:
            raise ValueError("MIDI channel %d contains no notes" % channel)
        for item in sources[channel]:
            selected.append({
                "track": item["track"],
                "channel": item["channel"],
                "priority": 100,
            })
    return {
        "version": 1,
        "description": (
            "Melody annotations for %s from MIDI channel%s %s. "
            "Simultaneous notes are reduced to the %s note."
            % (
                source_name,
                "s" if len(channels) != 1 else "",
                ", ".join(str(channel) for channel in channels),
                selection,
            )
        ),
        "segments": [{
            "start_tick": 0,
            "end_tick": None,
            "selection": selection,
            "sources": selected,
        }],
        "include": [],
        "exclude": [],
    }


def make_part_annotation(parts, selected_parts, selection, source_name):
    indexed = {item["part"]: item for item in parts}
    selected = []
    for part in selected_parts:
        if part not in indexed:
            raise ValueError("MIDI part %d does not exist" % part)
        item = indexed[part]
        selected.append({
            "track": item["track"],
            "channel": item["channel"],
            "priority": 100,
        })
    return {
        "version": 1,
        "description": (
            "Melody annotations for %s from player parts %s. "
            "Simultaneous notes are reduced to the %s note."
            % (source_name, ", ".join("%02d" % part for part in selected_parts), selection)
        ),
        "segments": [{
            "start_tick": 0,
            "end_tick": None,
            "selection": selection,
            "sources": selected,
        }],
        "include": [],
        "exclude": [],
    }


def write_annotation(path, annotation, force=False):
    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != annotation:
            raise FileExistsError(
                "%s already exists and differs; pass --force to replace it" % path
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(annotation, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    melody = parser.add_mutually_exclusive_group()
    melody.add_argument("--melody", type=parse_channels,
                        help="comma-separated 1-based MIDI melody channel(s)")
    melody.add_argument("--melody-parts", type=parse_parts,
                        help="comma-separated player component numbers")
    melody.add_argument("--no-melody", action="store_true",
                        help="convert without melody-onset annotations")
    parser.add_argument("--selection", choices=("highest", "lowest"),
                        default="highest", help="reduce simultaneous melody notes")
    parser.add_argument("--output", type=Path, help="destination .song path")
    parser.add_argument("--annotation", type=Path, help="destination annotation JSON")
    parser.add_argument("--list", action="store_true", help="list channels without converting")
    parser.add_argument("--force", action="store_true",
                        help="replace a differing existing annotation")
    args = parser.parse_args(argv)

    source = args.midi.resolve()
    if not source.is_file():
        parser.error("MIDI file does not exist: %s" % args.midi)
    midi = mido.MidiFile(source)
    sources = channel_sources(midi)
    parts = part_sources(midi)
    describe_channels(sources)
    describe_parts(parts)
    if args.list:
        return 0
    if not args.melody and not args.melody_parts and not args.no_melody:
        parser.error(
            "choose melody sources with --melody or --melody-parts; use --list if unsure"
        )

    name = slug(source.stem)
    output = (args.output or ROOT / "music_box" / "songs" / (name + ".song")).resolve()
    annotation_path = None if args.no_melody else (
        args.annotation or ROOT / "tools" / "melodies" / (name + ".melody.json")
    ).resolve()
    if args.no_melody:
        annotation = None
    elif args.melody_parts:
        annotation = make_part_annotation(
            parts, args.melody_parts, args.selection, source.name
        )
    else:
        annotation = make_annotation(
            sources, args.melody, args.selection, source.name
        )
    if annotation_path is not None:
        write_annotation(annotation_path, annotation, args.force)
    convert(source, output, annotation_path)
    print("Melody annotation:", annotation_path or "none")
    print("Song output:       ", output)
    print("Nothing was uploaded; these are local files only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

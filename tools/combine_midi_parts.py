"""Combine selected MIDI part files back into one type-1 MIDI file.

The part files produced by split_midi_parts.py each contain the same
conductor track followed by one musical track. Files removed from the parts
directory are therefore omitted from the rebuilt arrangement.
"""
import argparse
from pathlib import Path

import mido


def _clone_track(track):
    cloned = mido.MidiTrack()
    cloned.extend(message.copy() for message in track)
    return cloned


def combine_parts(source_directory, destination):
    source_directory = Path(source_directory)
    destination = Path(destination)
    part_paths = sorted(source_directory.glob("*.mid"))
    if not part_paths:
        raise ValueError("No MIDI part files found in %s" % source_directory)

    first = mido.MidiFile(part_paths[0])
    if len(first.tracks) != 2:
        raise ValueError("Expected conductor + part in %s" % part_paths[0])

    combined = mido.MidiFile(type=1, ticks_per_beat=first.ticks_per_beat)
    combined.tracks.append(_clone_track(first.tracks[0]))

    names = []
    for part_path in part_paths:
        part = mido.MidiFile(part_path)
        if part.ticks_per_beat != combined.ticks_per_beat:
            raise ValueError("Mismatched ticks-per-beat in %s" % part_path)
        if len(part.tracks) != 2:
            raise ValueError("Expected conductor + part in %s" % part_path)
        combined.tracks.append(_clone_track(part.tracks[1]))
        names.append(part.tracks[1].name or part_path.stem)

    destination.parent.mkdir(parents=True, exist_ok=True)
    combined.save(destination)
    print(
        "%s: combined %d parts (%s)"
        % (destination, len(names), ", ".join(names))
    )
    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Combine selected split-MIDI parts into one MIDI file."
    )
    parser.add_argument("source_directory", help="folder containing part MIDIs")
    parser.add_argument("destination", help="combined output MIDI")
    args = parser.parse_args()
    combine_parts(args.source_directory, args.destination)


if __name__ == "__main__":
    main()

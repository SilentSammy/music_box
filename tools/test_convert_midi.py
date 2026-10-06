"""Tests for the convenient annotated MIDI conversion wrapper."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import mido

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import convert_midi
from midi_to_song import FLAG_MELODY_ONSET, HEADER, RECORD


class ConvertMidiTests(unittest.TestCase):
    def sample(self, path):
        midi = mido.MidiFile(ticks_per_beat=480)
        meta = mido.MidiTrack([mido.MetaMessage("track_name", name="Metadata")])
        lead = mido.MidiTrack([
            mido.MetaMessage("track_name", name="Lead"),
            mido.Message("program_change", channel=0, program=73, time=0),
            mido.Message("note_on", channel=0, note=60, velocity=100, time=0),
            mido.Message("note_on", channel=0, note=64, velocity=90, time=0),
            mido.Message("note_off", channel=0, note=60, time=480),
            mido.Message("note_off", channel=0, note=64, time=0),
        ])
        backing = mido.MidiTrack([
            mido.MetaMessage("track_name", name="Backing"),
            mido.Message("note_on", channel=1, note=48, velocity=80, time=0),
            mido.Message("note_off", channel=1, note=48, time=480),
        ])
        drums = mido.MidiTrack([
            mido.MetaMessage("track_name", name="Drums"),
            mido.Message("note_on", channel=9, note=36, velocity=100, time=0),
            mido.Message("note_off", channel=9, note=36, time=480),
        ])
        midi.tracks.extend((meta, lead, backing, drums))
        midi.save(path)

    def test_channel_numbers_match_interactive_player(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Example.mid"
            self.sample(source)
            sources = convert_midi.channel_sources(mido.MidiFile(source))
            self.assertEqual(sorted(sources), [1, 2])
            self.assertEqual(sources[1][0]["track"], 1)
            self.assertEqual(sources[1][0]["channel"], 0)
            parts = convert_midi.part_sources(mido.MidiFile(source))
            self.assertEqual(
                [(part["part"], part["track"], part["channel"])
                 for part in parts],
                [(1, 1, 0), (2, 2, 1)],
            )

    def test_conversion_writes_annotation_and_collapses_chord_onset(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Example.mid"
            output = Path(directory) / "example.song"
            annotation = Path(directory) / "example.json"
            self.sample(source)
            result = convert_midi.main([
                str(source), "--melody", "1", "--output", str(output),
                "--annotation", str(annotation),
            ])
            self.assertEqual(result, 0)
            data = json.loads(annotation.read_text(encoding="utf-8"))
            self.assertEqual(data["segments"][0]["sources"], [
                {"track": 1, "channel": 0, "priority": 100}
            ])
            raw = output.read_bytes()
            header = HEADER.unpack_from(raw)
            records = [
                RECORD.unpack_from(raw, HEADER.size + index * RECORD.size)
                for index in range(header[5])
            ]
            melody = [record for record in records if record[1] & FLAG_MELODY_ONSET]
            self.assertEqual(len(melody), 1)
            self.assertEqual(melody[0][-3], 64)

    def test_reject_missing_channel_and_protect_annotation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Example.mid"
            annotation = Path(directory) / "annotation.json"
            self.sample(source)
            sources = convert_midi.channel_sources(mido.MidiFile(source))
            with self.assertRaisesRegex(ValueError, "contains no notes"):
                convert_midi.make_annotation(sources, [16], "highest", source.name)
            annotation.write_text("{}", encoding="utf-8")
            expected = convert_midi.make_annotation(sources, [1], "highest", source.name)
            with self.assertRaises(FileExistsError):
                convert_midi.write_annotation(annotation, expected)

    def test_part_selection_distinguishes_tracks_on_same_channel(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        for name, note in (("First", 60), ("Second", 64)):
            midi.tracks.append(mido.MidiTrack([
                mido.MetaMessage("track_name", name=name),
                mido.Message("note_on", channel=0, note=note, velocity=90),
                mido.Message("note_off", channel=0, note=note, time=480),
            ]))
        parts = convert_midi.part_sources(midi)
        annotation = convert_midi.make_part_annotation(
            parts, [2], "highest", "shared.mid"
        )
        self.assertEqual(annotation["segments"][0]["sources"], [
            {"track": 1, "channel": 0, "priority": 100}
        ])
        self.assertIn("parts 02", annotation["description"])

    def test_explicit_no_melody_conversion_has_no_melody_onsets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "single.mid"
            output = Path(directory) / "single.song"
            self.sample(source)
            result = convert_midi.main([
                str(source), "--no-melody", "--output", str(output),
            ])
            self.assertEqual(result, 0)
            raw = output.read_bytes()
            header = HEADER.unpack_from(raw)
            records = [
                RECORD.unpack_from(raw, HEADER.size + index * RECORD.size)
                for index in range(header[5])
            ]
            self.assertFalse(any(record[1] & FLAG_MELODY_ONSET for record in records))


if __name__ == "__main__":
    unittest.main()

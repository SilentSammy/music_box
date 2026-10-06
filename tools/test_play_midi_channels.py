"""Tests for source-aware interactive MIDI component playback."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import mido

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import play_midi_channels as module


def sample_midi():
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500_000, time=0),
    ]))
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("track_name", name="Lead A"),
        mido.Message("note_on", channel=0, note=60, velocity=100, time=480),
        mido.Message("note_off", channel=0, note=60, time=480),
    ]))
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("track_name", name="Lead B"),
        mido.Message("note_on", channel=0, note=64, velocity=100, time=480),
        mido.Message("note_off", channel=0, note=64, time=480),
        mido.Message("note_on", channel=2, note=48, velocity=80, time=0),
        mido.Message("note_off", channel=2, note=48, time=480),
    ]))
    return midi


class MidiPlayerTests(unittest.TestCase):
    def setUp(self):
        self.midi = sample_midi()
        self.components = module.discover_components(self.midi)
        self.events, self.duration = module.timed_messages(
            self.midi, self.components
        )

    def test_discovers_track_channel_pairs_not_just_channels(self):
        self.assertEqual(
            [(part.track, part.channel, part.name, part.notes)
             for part in self.components],
            [(1, 0, "Lead A", 1),
             (2, 0, "Lead B", 1),
             (2, 2, "Lead B", 1)],
        )
        self.assertEqual([part.key for part in self.components], list("123"))

    def test_timing_retains_source_component(self):
        notes = [event for event in self.events
                 if event.message.type == "note_on"]
        self.assertEqual(
            [round(event.seconds, 3) for event in notes], [0.5, 0.5, 1.0]
        )
        self.assertEqual([event.component for event in notes], [0, 1, 2])
        self.assertEqual(self.duration, 1.5)

    def test_toggle_one_shared_channel_component_only(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components
        )
        player.active[0][60] = 1
        player.active[1][64] = 1
        player.toggle_component(0)
        self.assertFalse(player.enabled[0])
        self.assertTrue(player.enabled[1])
        output.write_short.assert_called_once_with(0x80, 60, 0)

    def test_muted_component_suppresses_its_future_notes(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components
        )
        player.enabled[0] = False
        first_a = next(event for event in self.events
                       if event.component == 0
                       and event.message.type == "note_on")
        first_b = next(event for event in self.events
                       if event.component == 1
                       and event.message.type == "note_on")
        player._process_event(first_a)
        output.write_short.assert_not_called()
        player._process_event(first_b)
        output.write_short.assert_called()

    def test_component_keys_and_controls(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components
        )
        player.handle_key("2")
        self.assertFalse(player.enabled[1])
        player.handle_key("a")
        self.assertFalse(any(player.enabled))
        player.handle_key("a")
        self.assertTrue(all(player.enabled))
        self.assertFalse(player.handle_key("x"))

    def test_speed_controls_cycle_through_requested_values(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components
        )
        self.assertEqual(player.speed, 1.0)
        player.handle_key("]")
        self.assertEqual(player.speed, 1.25)
        player.handle_key("[")
        self.assertEqual(player.speed, 1.0)
        for _ in range(3):
            player.handle_key("[")
        self.assertEqual(player.speed, 0.0)

    def test_reverse_crossing_inverts_note_boundaries(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components, loop=False
        )
        player.speed_index = module.PLAYBACK_SPEEDS.index(-1.0)
        player.position = self.duration
        player.index = len(self.events)
        player.last_clock = 0.0
        with patch.object(module.time, "monotonic", return_value=0.75):
            player.update()
        sent = [call.args for call in output.write_short.call_args_list]
        self.assertIn((0x90 | 2, 48, 80), sent)
        self.assertIn((0x90, 64, 100), sent)

    def test_pause_and_restart_clear_active_notes(self):
        output = MagicMock()
        player = module.MidiPlayer(
            output, self.events, self.duration, self.components
        )
        player.active[0][60] = 1
        with patch.object(module.time, "monotonic", side_effect=[1.0, 2.0]):
            player.toggle_pause()
            self.assertFalse(player.active[0])
            player.toggle_pause()
            player.restart()
        self.assertGreaterEqual(output.write_short.call_count, 16 * 3 * 2)


if __name__ == "__main__":
    unittest.main()

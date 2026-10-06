"""Host regression tests for melody-synchronized Song Snake."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock


APP = Path(__file__).resolve().parents[1] / "music_box"
sys.path.insert(0, str(APP))

from events import ENCODER, MEASURE, MELODY_ONSET, Event
from song_snake import SongSnake


def context(width=128, height=64, dt_ms=0):
    return types.SimpleNamespace(
        canvas=types.SimpleNamespace(width=width, height=height),
        dt_ms=dt_ms,
    )


class SongSnakeTests(unittest.TestCase):
    def game(self):
        game = SongSnake()
        game.on_enter(context())
        return game

    def test_grid_starts_without_pellets(self):
        game = self.game()
        self.assertEqual((game.columns, game.rows), (21, 8))
        self.assertEqual((game.grid_x, game.grid_y), (1, 8))
        self.assertEqual(game.pellets, [])

    def test_each_melody_onset_spawns_one_pellet(self):
        game = self.game()
        game.on_event(Event(MELODY_ONSET, (60, 100, 100)), None)
        game.on_event(Event(MELODY_ONSET, (62, 100, 100)), None)
        self.assertEqual(len(game.pellets), 2)

    def test_sequence_is_repeatable_despite_different_player_state(self):
        first = self.game()
        second = self.game()
        expected = []
        actual = []
        for index in range(12):
            first.on_event(Event(MELODY_ONSET), None)
            expected.append(first.pellets[-1])
            second.snake[0] = (index % second.columns, index % second.rows)
            if second.pellets and index % 3 == 0:
                second.pellets.pop(0)
            second.on_event(Event(MELODY_ONSET), None)
            actual.append(second.pellets[-1])
        self.assertEqual(actual, expected)

    def test_pellets_clear_after_four_completed_measures(self):
        game = self.game()
        for measure in range(5):
            game.on_event(Event(MEASURE), None)
            if measure < 4:
                game.on_event(Event(MELODY_ONSET), None)
        self.assertEqual(game.measure_index, 4)
        self.assertEqual(game.pellets, [])

    def test_encoder_turn_and_grid_wrapping(self):
        game = self.game()
        game.on_event(Event(ENCODER, 1), None)
        game._advance()
        self.assertEqual(game.direction, (0, 1))
        game.snake = [(4, game.rows - 1), (4, game.rows - 2)]
        game._advance()
        self.assertEqual(game.snake[0], (4, 0))

    def test_render_draws_head_direction_pixels(self):
        game = SongSnake("Animals")
        game.on_enter(context())
        canvas = MagicMock()
        canvas.width = 128
        game.render(canvas, context())
        head_x, head_y = game.snake[0]
        pixel_x = game.grid_x + head_x * game.TILE_SIZE
        pixel_y = game.grid_y + head_y * game.TILE_SIZE
        canvas.pixel.assert_any_call(pixel_x + 5, pixel_y + 2, 1)
        canvas.pixel.assert_any_call(pixel_x + 5, pixel_y + 3, 1)
        canvas.text.assert_any_call("Animals", 36, 56, 1)


if __name__ == "__main__":
    unittest.main()

"""Deterministic, melody-synchronized Snake game for song playback."""
from animation import Animation, EVENT_CONSUMED, EVENT_DIRTY
from events import ENCODER, MEASURE, MELODY_ONSET


class SongSnake(Animation):
    """Snake whose pellet sequence is driven by annotated melody notes."""

    opaque = True

    TILE_SIZE = 6
    TOP_HEIGHT = 8
    BOTTOM_HEIGHT = 8
    FOOTER_TEXT = "MII CHANNEL"
    MOVE_INTERVAL_MS = 180
    MAX_PELLETS = 10
    INITIAL_LENGTH = 4
    MEASURES_PER_CLEAR = 4
    RANDOM_SEED = 0x00C0FFEE

    def __init__(self):
        self.columns = 0
        self.rows = 0
        self.grid_x = 0
        self.grid_y = self.TOP_HEIGHT
        self.snake = []
        self.pellets = []
        self.direction = (1, 0)
        self.pending_turn = 0
        self.move_elapsed_ms = 0
        self.score = 0
        self.game_over = False
        self.measure_index = -1
        self.spawn_index = 0
        self.spawn_start = 0
        self.spawn_step = 1

    def on_enter(self, context):
        self.columns = context.canvas.width // self.TILE_SIZE
        self.rows = (
            context.canvas.height - self.TOP_HEIGHT - self.BOTTOM_HEIGHT
        ) // self.TILE_SIZE
        grid_width = self.columns * self.TILE_SIZE
        grid_height = self.rows * self.TILE_SIZE
        self.grid_x = (context.canvas.width - grid_width) // 2
        self.grid_y = self.TOP_HEIGHT + (
            context.canvas.height
            - self.TOP_HEIGHT
            - self.BOTTOM_HEIGHT
            - grid_height
        ) // 2
        self.restart()

    def restart(self):
        center_x = self.columns // 2
        center_y = self.rows // 2
        self.snake = [
            (center_x - offset, center_y)
            for offset in range(self.INITIAL_LENGTH)
        ]
        self.pellets = []
        self.direction = (1, 0)
        self.pending_turn = 0
        self.move_elapsed_ms = 0
        self.score = 0
        self.game_over = False
        self.measure_index = -1
        self.spawn_index = 0
        self._configure_spawn_sequence()

    def _configure_spawn_sequence(self):
        cell_count = self.columns * self.rows
        state = (
            1664525 * self.RANDOM_SEED + 1013904223
        ) & 0xFFFFFFFF
        self.spawn_start = state % cell_count
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        step = (state % cell_count) | 1
        while self._greatest_common_divisor(step, cell_count) != 1:
            step = (step + 2) % cell_count
            if step == 0:
                step = 1
        self.spawn_step = step

    @staticmethod
    def _greatest_common_divisor(left, right):
        while right:
            left, right = right, left % right
        return left

    def _spawn_pellet(self):
        """Add the next song-defined location, independent of player actions."""
        cell_count = self.columns * self.rows
        index = (
            self.spawn_start + self.spawn_index * self.spawn_step
        ) % cell_count
        self.spawn_index += 1
        cell = (index % self.columns, index // self.columns)
        if len(self.pellets) >= self.MAX_PELLETS:
            self.pellets.pop(0)
        self.pellets.append(cell)

    def on_event(self, event, context):
        if event.type == ENCODER and not self.game_over:
            if self.pending_turn == 0 and event.value:
                self.pending_turn = 1 if event.value > 0 else -1
            return EVENT_DIRTY | EVENT_CONSUMED
        if event.type == MEASURE:
            self.measure_index += 1
            if (
                self.measure_index > 0
                and self.measure_index % self.MEASURES_PER_CLEAR == 0
            ):
                self.pellets = []
                return EVENT_DIRTY
            return 0
        if event.type == MELODY_ONSET:
            self._spawn_pellet()
            return EVENT_DIRTY
        return 0

    def _apply_turn(self):
        if not self.pending_turn:
            return
        direction_x, direction_y = self.direction
        if self.pending_turn > 0:
            self.direction = (-direction_y, direction_x)
        else:
            self.direction = (direction_y, -direction_x)
        self.pending_turn = 0

    def _advance(self):
        self._apply_turn()
        head_x, head_y = self.snake[0]
        direction_x, direction_y = self.direction
        new_head = (
            (head_x + direction_x) % self.columns,
            (head_y + direction_y) % self.rows,
        )
        growing = new_head in self.pellets
        collision_body = self.snake if growing else self.snake[:-1]
        if new_head in collision_body:
            self.game_over = True
            return
        self.snake.insert(0, new_head)
        if growing:
            self.pellets.remove(new_head)
            self.score += 1
        else:
            self.snake.pop()

    def update(self, context):
        if self.game_over:
            return False
        self.move_elapsed_ms += min(context.dt_ms, 250)
        changed = False
        while self.move_elapsed_ms >= self.MOVE_INTERVAL_MS and not self.game_over:
            self.move_elapsed_ms -= self.MOVE_INTERVAL_MS
            self._advance()
            changed = True
        return changed

    def render(self, canvas, context):
        canvas.text("L:%02d P:%02d" % (
            len(self.snake), len(self.pellets)
        ), 0, 0, 1)
        canvas.text("S:%02d" % self.score, 88, 0, 1)
        if self.FOOTER_TEXT:
            canvas.text(
                self.FOOTER_TEXT,
                0,
                self.grid_y + self.rows * self.TILE_SIZE,
                1,
            )

        for pellet_x, pellet_y in self.pellets:
            pixel_x = self.grid_x + pellet_x * self.TILE_SIZE
            pixel_y = self.grid_y + pellet_y * self.TILE_SIZE
            canvas.fill_rect(pixel_x + 2, pixel_y + 2, 2, 2, 1)

        for index, (snake_x, snake_y) in enumerate(self.snake):
            pixel_x = self.grid_x + snake_x * self.TILE_SIZE
            pixel_y = self.grid_y + snake_y * self.TILE_SIZE
            canvas.fill_rect(pixel_x + 1, pixel_y + 1, 4, 4, 1)
            if index == 0:
                direction_x, direction_y = self.direction
                if direction_x > 0:
                    indicator = ((pixel_x + 5, pixel_y + 2),
                                 (pixel_x + 5, pixel_y + 3))
                elif direction_x < 0:
                    indicator = ((pixel_x, pixel_y + 2),
                                 (pixel_x, pixel_y + 3))
                elif direction_y > 0:
                    indicator = ((pixel_x + 2, pixel_y + 5),
                                 (pixel_x + 3, pixel_y + 5))
                else:
                    indicator = ((pixel_x + 2, pixel_y),
                                 (pixel_x + 3, pixel_y))
                for indicator_x, indicator_y in indicator:
                    canvas.pixel(indicator_x, indicator_y, 1)

        if self.game_over:
            canvas.fill_rect(16, 22, 96, 28, 1)
            canvas.text("GAME OVER", 28, 26, 0)
            canvas.text("Click: stop", 24, 38, 0)

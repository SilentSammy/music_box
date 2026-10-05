"""Input-agnostic menu renderer.

Menus are ordered sequences of ``("Label", callback)`` pairs. Callbacks may
run any code, including ``menu.set_menu(other_menu)`` to navigate between menus.
The application maps any input device to ``scroll_up()``, ``scroll_down()``,
and ``select()``.
"""


class Menu:
    ROW_HEIGHT = 10
    VISIBLE_ROWS = 6

    def __init__(self, display, options):
        self.display = display
        self.options = ()
        self.labels = []
        self.index = 0
        self.set_menu(options)

    def set_menu(self, options):
        """Replace the current menu with an ordered sequence of option pairs."""
        if not isinstance(options, (list, tuple)):
            raise TypeError("menu options must be a list or tuple")
        for option in options:
            if not isinstance(option, (list, tuple)) or len(option) != 2:
                raise TypeError("each menu option must be a (label, callback) pair")
            label, callback = option
            if not isinstance(label, str):
                raise TypeError("menu labels must be strings")
            if not callable(callback):
                raise TypeError("menu values must be callable")

        self.options = options
        self.labels = [label for label, callback in options]
        self.index = 0
        self.draw()

    def scroll_up(self):
        if self.labels:
            self.index = (self.index - 1) % len(self.labels)
            self.draw()

    def scroll_down(self):
        if self.labels:
            self.index = (self.index + 1) % len(self.labels)
            self.draw()

    def select(self):
        if self.labels:
            self.options[self.index][1]()

    def draw(self):
        d = self.display
        d.clear()
        if not self.labels:
            d.show()
            return

        top = max(0, self.index - self.VISIBLE_ROWS + 1)
        bottom = min(len(self.labels), top + self.VISIBLE_ROWS)
        for row, i in enumerate(range(top, bottom)):
            label = self.labels[i]
            y = row * self.ROW_HEIGHT
            if i == self.index:
                d.fill_rect(0, y, d.width, self.ROW_HEIGHT, 1)
                d.text(label, 2, y + 1, 0)
            else:
                d.text(label, 2, y + 1, 1)
        d.show()

"""Input-agnostic ordered menu renderer."""


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
        display = self.display
        display.clear()
        if not self.labels:
            display.show()
            return

        top = max(0, self.index - self.VISIBLE_ROWS + 1)
        bottom = min(len(self.labels), top + self.VISIBLE_ROWS)
        for row, option_index in enumerate(range(top, bottom)):
            label = self.labels[option_index]
            y = row * self.ROW_HEIGHT
            if option_index == self.index:
                display.fill_rect(0, y, display.width, self.ROW_HEIGHT, 1)
                display.text(label, 2, y + 1, 0)
            else:
                display.text(label, 2, y + 1, 1)
        display.show()

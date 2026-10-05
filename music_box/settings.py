"""Persistent and extensible Music Box settings."""
import json


SETTINGS_FILE = "settings.json"
DEFAULTS = {
    "version": 1,
    "volume": 50,
}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.data = DEFAULTS.copy()
        self.load()

    def load(self):
        try:
            with open(self.path, "r") as settings_file:
                saved = json.loads(settings_file.read())
            if isinstance(saved, dict):
                self.data.update(saved)
        except (OSError, ValueError):
            pass

        # Reject damaged or manually edited volume values.
        volume = self.data.get("volume", DEFAULTS["volume"])
        if not isinstance(volume, int) or not 0 <= volume <= 100:
            self.data["volume"] = DEFAULTS["volume"]

    def save(self):
        with open(self.path, "w") as settings_file:
            settings_file.write(json.dumps(self.data))

    def get(self, name):
        return self.data[name]

    def set(self, name, value):
        self.data[name] = value

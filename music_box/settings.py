"""Persistent and extensible Music Box settings."""
import json
import os


SETTINGS_FILE = "settings.json"
DEFAULTS = {
    "version": 2,
    "volume": 75,
    "imu_accel_offset": None,
    "about_text": "Para mi Carly. Con amor, Samu <3",
}


def migrate_v1_to_v2(data):
    # Add future rename/unit-conversion migrations here, one schema at a time.
    data["version"] = 2
    return data


MIGRATIONS = {1: migrate_v1_to_v2}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.data = DEFAULTS.copy()
        self.load()

    def load(self):
        saved = self._read(self.path)
        if saved is None:
            try:
                import platform_services
                previous = platform_services.installation_context().get("previous_path")
                if previous:
                    saved = self._read(previous + "/" + self.path)
                    if saved is not None:
                        print("Settings imported from previous installation:", previous)
            except (ImportError, AttributeError, OSError, ValueError):
                pass
        if saved is not None:
            self.data.update(saved)
        self._validate()
        # Create missing settings and persist schema upgrades in this install only.
        self.save()

    @staticmethod
    def _read(path):
        try:
            with open(path, "r") as settings_file:
                saved = json.load(settings_file)
            if not isinstance(saved, dict):
                return None
            version = saved.get("version", 1)
            if type(version) is not int or not 1 <= version <= DEFAULTS["version"]:
                return None
            while version < DEFAULTS["version"]:
                saved = MIGRATIONS[version](saved)
                version = saved["version"]
            # Removed/unknown keys do not enter the current schema.
            return {key: saved[key] for key in DEFAULTS if key in saved}
        except (OSError, ValueError):
            return None

    def _validate(self):
        # Reject damaged or manually edited volume values.
        volume = self.data.get("volume", DEFAULTS["volume"])
        if type(volume) is not int or not 0 <= volume <= 100:
            self.data["volume"] = DEFAULTS["volume"]
        if not isinstance(self.data.get("about_text"), str):
            self.data["about_text"] = DEFAULTS["about_text"]
        self.data["imu_accel_offset"] = self.imu_calibration()
        self.data["version"] = DEFAULTS["version"]

    def save(self):
        temporary = self.path + ".tmp"
        with open(temporary, "w") as settings_file:
            json.dump(self.data, settings_file)
            settings_file.flush()
        if hasattr(os, "sync"):
            os.sync()
        # LittleFS rename replaces atomically; CPython/Windows uses replace.
        getattr(os, "replace", os.rename)(temporary, self.path)
        if hasattr(os, "sync"):
            os.sync()

    def imu_calibration(self):
        offset = self.data.get("imu_accel_offset")
        if not isinstance(offset, (list, tuple)) or len(offset) != 3:
            return None
        # Reject malformed, infinite, or NaN values instead of using bad physics.
        if not all(isinstance(value, (int, float)) and -4 <= value <= 4
                   for value in offset):
            return None
        return tuple(offset)

    def get(self, name):
        return self.data[name]

    def set(self, name, value):
        self.data[name] = value

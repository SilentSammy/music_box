"""Build the static update feed published through GitHub Pages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "update_source.json"
DEFAULT_OUTPUT = ROOT / "build" / "update-source"
OUTPUT_MARKER = ".music-box-update-source"
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
EXCLUDED_NAMES = {"pymakr.conf", "settings.json", "settings.json.tmp", "wifi_secrets.py"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_PARTS = {"__pycache__"}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict) -> bytes:
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_config(config: dict) -> None:
    required = {
        "schema_version",
        "application_id",
        "version",
        "base_url",
        "source_directory",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError("Missing configuration keys: " + ", ".join(missing))
    if config["schema_version"] != 1:
        raise ValueError("Only update-source schema version 1 is supported")
    if not VERSION_RE.fullmatch(config["version"]):
        raise ValueError("version may contain only letters, numbers, '.', '_' and '-'")
    if not config["application_id"]:
        raise ValueError("application_id must not be empty")
    if not str(config["base_url"]).startswith("https://"):
        raise ValueError("base_url must use HTTPS")


def prepare_output(output: Path) -> None:
    if output.exists():
        marker = output / OUTPUT_MARKER
        if not marker.is_file():
            raise ValueError(
                f"Refusing to replace unrecognized output directory: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / OUTPUT_MARKER).write_text("generated\n", encoding="utf-8")


def deployable_files(source: Path):
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        if any(part in EXCLUDED_PARTS or part.startswith(".") for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        yield path, PurePosixPath(*relative.parts)


def build(config_path: Path, output: Path) -> dict:
    config = read_json(config_path)
    validate_config(config)

    source = (ROOT / config["source_directory"]).resolve()
    if not source.is_dir() or not (source / "main.py").is_file():
        raise ValueError(f"Application source is missing main.py: {source}")

    prepare_output(output)

    base_url = config["base_url"].rstrip("/")
    version = config["version"]
    release_root = output / "releases" / version
    files_root = release_root / "files"
    manifest_files = []

    for source_path, relative in deployable_files(source):
        relative_text = relative.as_posix()
        compile_module = (config.get("compile_modules", False)
                          and source_path.suffix == ".py" and relative_text != "main.py")
        if compile_module:
            relative = relative.with_suffix(".mpy")
            relative_text = relative.as_posix()
        destination = files_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if compile_module:
            subprocess.run([
                sys.executable, "-m", "mpy_cross", "-s",
                source_path.relative_to(source).as_posix(), "-o", str(destination),
                str(source_path),
            ], check=True)
            data = destination.read_bytes()
        else:
            data = source_path.read_bytes()
            destination.write_bytes(data)
        encoded_path = quote(relative_text, safe="/")
        manifest_files.append(
            {
                "path": relative_text,
                "size": len(data),
                "sha256": sha256(data),
                "url": f"{base_url}/releases/{version}/files/{encoded_path}",
            }
        )

    if not manifest_files:
        raise ValueError("The application source contains no deployable files")

    manifest = {
        "schema_version": 1,
        "application_id": config["application_id"],
        "version": version,
        "files": manifest_files,
    }
    if config.get("compile_modules", False):
        # Portable bytecode; no CPU-specific native/viper compilation.
        manifest["mpy_format"] = 6
        manifest["minimum_micropython"] = [1, 29, 0]
    manifest_bytes = write_json(release_root / "manifest.json", manifest)
    manifest_url = f"{base_url}/releases/{version}/manifest.json"

    descriptor = {
        "schema_version": 1,
        "application_id": config["application_id"],
        "version": version,
        "manifest": {
            "url": manifest_url,
            "size": len(manifest_bytes),
            "sha256": sha256(manifest_bytes),
        },
    }
    write_json(output / "update.json", descriptor)
    (output / ".nojekyll").write_text("", encoding="utf-8")

    title = html.escape(config["application_id"])
    safe_version = html.escape(version)
    index = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} update source</title>
<h1>{title} update source</h1>
<p>Published version: <strong>{safe_version}</strong></p>
<ul>
  <li><a href="update.json">Version descriptor</a></li>
  <li><a href="releases/{quote(version)}/manifest.json">Release manifest</a></li>
</ul>
"""
    (output / "index.html").write_text(index, encoding="utf-8", newline="\n")

    return {
        "version": version,
        "files": len(manifest_files),
        "bytes": sum(item["size"] for item in manifest_files),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.config.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Legacy converter for Cajita-Musical uint16_t song headers."""
import argparse
import re
import struct
from pathlib import Path


ROW_PATTERN = re.compile(
    r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}"
)


def convert(source, destination):
    source = Path(source)
    destination = Path(destination)
    rows = [tuple(map(int, match)) for match in ROW_PATTERN.findall(source.read_text())]
    if not rows:
        raise ValueError("No song rows found in %s" % source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        for row in rows:
            output.write(struct.pack(">5H", *row))
    print("%s: %d legacy events" % (destination, len(rows)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    convert(args.source, args.destination)

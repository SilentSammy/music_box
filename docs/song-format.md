# Music Box song format

`.song` files are generated on the development computer by
`tools/midi_to_song.py`. Version 2 uses big-endian binary fields.

The 18-byte header is `>4sBBHHII`:

- magic: `MSNG`
- format version
- voice count
- record size
- source MIDI ticks per quarter note
- record count
- duration in milliseconds

Each 23-byte record is `>IBIBB12B`:

- absolute playback position in milliseconds
- event flags
- tempo in microseconds per quarter note
- time-signature numerator and denominator
- four triplets of MIDI note, original velocity, and effective level

Event flags are beat (`0x01`), measure (`0x02`), tempo change (`0x04`),
time-signature change (`0x08`), end (`0x10`), and note onset (`0x20`). Measure
boundaries are calculated from MIDI PPQN and time-signature events. Effective
level includes MIDI note velocity, CC7 channel volume, and CC11 expression.
Channel 10 percussion is omitted because the four passive buzzers are pitched
voices.

Convert the project song manifest with:

```powershell
python tools/midi_to_song.py --manifest tools/songs.json
```

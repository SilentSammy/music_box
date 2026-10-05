# OLED Display Notes

## Current hardware
- SSD1306 128x64 monochrome OLED, I2C
- Wired: SCL = GPIO7, SDA = GPIO6, addr = 0x3C
- ESP32-C3, MicroPython 1.23.0

## Findings

**Pixel control:** Full per-pixel control via `framebuf` (pixel/line/rect/ellipse/poly/text/etc).
Monochrome only — no grayscale/color, no per-pixel brightness.

**Software PWM experiment (to fake brightness/blink):**
- Single pixel toggle via column/page addressing (`0x21`/`0x22`) instead of full buffer rewrite.
- Results (measured on this hardware):
  - 1 pixel, 400kHz, naive: ~754 Hz max
  - 1 pixel, 400kHz, merged commands: ~974 Hz max
  - 1 pixel, 1MHz clock, merged commands: ~1316 Hz max
  - 8 px: ~92 Hz, 16 px: ~46 Hz, 32 px: ~23 Hz, 64 px: ~11.5 Hz (scales linearly, ~675us/pixel/phase)
  - Full-frame rewrite: ~12ms/frame (~83 FPS ceiling) regardless of 400kHz vs 1MHz config
- Verdict: PWM dimming is viable for **1 pixel** (~9/10), marginal for a small cluster (~8-16px, ~4/10),
  not viable for a full grayscale framebuffer (~1/10). Whole-screen blink is borderline (~5/10) and
  eats the whole CPU budget since it's blocking.
- Note: raising I2C clock 400kHz→1MHz didn't help bulk transfers at all, only small transactions.
  Bottleneck for full-frame updates isn't clock speed, it's per-transaction/driver overhead.

## Future color upgrade path

- No true "drop-in" I2C color replacement for SSD1306 in general — most color OLED/LCD controllers
  (SSD1351, ST7789, ST7735, etc.) are SPI-only and need more pins (SCLK, MOSI, CS, DC, RES vs just SCL/SDA).
- Color also needs ~16x the bandwidth (RGB565 vs 1bpp), so I2C wouldn't keep up anyway.
- **Decision:** if we can find an identically-sized *I2C* color display later, upgrade is software-only
  (new driver class, same 4 wires). If not, we're stuck needing SPI.
- **Mitigation for PCB:** route the display connector as **7 pins**, not 4:
  - GND, VCC, SCL/SCLK (GPIO7), SDA/MOSI (GPIO6) — populated/used now
  - CS, DC, RES — unpopulated spare pads wired to free GPIOs, reserved for a future SPI display
  - Avoid ESP32-C3 strapping pins (GPIO2, GPIO8, GPIO9) for these spares.
  - Cost is ~3 extra pads/traces, no extra components until actually used.
- App-level display code should stay behind a small abstraction (`.pixel()`, `.text()`, `.show()`,
  `.clear()`) so swapping the driver later doesn't touch higher-level logic.

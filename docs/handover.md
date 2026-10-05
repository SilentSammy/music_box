# Music Box — Session Handover

## Hardware (validated, wired on breadboard)
- **Board**: ESP32-C3 (XIAO-style), MicroPython 1.23.0. Avoid strapping pins GPIO2/8/9.
- **Display**: SSD1306 128x64 I2C OLED. SCL=GPIO7, SDA=GPIO6, addr=0x3C.
- **Rotary encoder + button** (KY-040 style): CLK=GPIO3, DT=GPIO4, SW=GPIO5, all `Pin.IN, Pin.PULL_UP`.
- **Buzzer breadboard (separate, clean)**: passive piezo buzzer, `+` on GPIO10, `-` on GND.
  - A potentiometer was originally planned for hardware volume control but is **no longer needed** — volume is fully software-controlled via PWM duty cycle (see below). The pot footprint on the breadboard can be left unpopulated.

## Workspace layout
- `gui-test/` — PyMakr project, current source of truth for the menu/display/encoder system. Upload this whole folder to the device via PyMakr.
  - `main.py` — owns menu contents, navigation links, and encoder→menu wiring.
  - `menu.py` — generic, input-agnostic menu helper. Menus are `{"Label": callback}` dicts. `set_menu()`, `scroll_up()`, `scroll_down()`, `select()`. Callbacks can call `menu.set_menu(other_dict)` to link to another menu (nesting/back-navigation is just a callback that re-assigns the menu).
  - `quadrature_encoder.py` — IRQ-driven encoder decoder (Gray-code state-transition table) + debounced button. `take_delta()` / `take_presses()`.
  - `ssd1306_driver.py` — minimal hand-written SSD1306 I2C driver (framebuf-based).
  - `pymakr.conf` — project name only.
- `buzzer_test/` — separate PyMakr project for the standalone buzzer breadboard.
  - `main.py` — plays C5/E5/G5, each at volumes 0.1/0.25/0.5/1.0 via `volume_to_duty()`.
- `docs/display-notes.md` — earlier hardware findings (pixel control, PWM benchmarks, color-OLED upgrade path notes). Still valid, not touched this session.

## Key decision this session: dropped micro-gui
We initially tried `micropython-micro-gui` (peterhinch) for menus. Abandoned it after repeated import-order/driver-compatibility failures (`ImportError: can't import name SSD`, then `AttributeError: 'SSD1306_I2C' object has no attribute 'rgb'` — official ssd1306 driver isn't color-system compatible, needed nano-gui's patched driver). User's call: "if we don't understand how something works we shouldn't use it." We looked at Pololu's `pico_snapshot` Zumo robot code for inspiration (`extras/menu.py`) and wrote our own ~60-90 line understandable modules instead. All micro-gui vendor files and remnants have been removed from the device and the workspace (the old `firmware/` folder is gone).

## Buzzer volume findings
- Piezo buzzer loudness perception is **non-linear** (log/exponential-ish) vs. raw PWM duty. Equal jumps in `duty_u16` do not sound like equal jumps in loudness.
- Useful audible range starts very low: duty **32** (out of 65535) was already clearly audible; duty near 32768 (50% electrical duty) is the practical maximum (square wave is fullest here — going toward 65535 approaches a constant-high signal = silence).
- Solved with `volume_to_duty(volume)` in `buzzer_test/main.py`: cubic taper, `duty = round(MAX_TONE_DUTY * volume**3)`, `MAX_TONE_DUTY = 32768`. Maps a 0.0-1.0 slider linearly-perceived scale onto duty. Reference points: 0.0→0, 0.1→33, 0.25→512, 0.5→4096, 0.75→13824, 1.0→32768.
- This function is only in `buzzer_test/main.py` right now — **not yet ported into `gui-test`**. If/when the buzzer is wired into the main menu project (not just its own test breadboard), copy `volume_to_duty()` (and `MAX_TONE_DUTY`) over, or factor it into a shared module.

## Known open items / not yet done
- Encoder physical rotation direction (which way = positive count) and detent accuracy (no skips/double-counts) was asked about early on but never confirmed by the user — low priority, verify empirically if it matters for menu feel.
- The buzzer test was run/iterated based on user's live listening feedback (COM12 serial), not captured/logged — no objective measurement, just "sounds right now" per user.
- Buzzer code lives in its own isolated PyMakr project (`buzzer_test/`); it has NOT been integrated with the display/encoder/menu system in `gui-test/`. That integration (e.g. a "Volume" menu item that actually drives a buzzer, or playing a note per menu action) is a natural next step but wasn't requested yet.
- Multiple buzzers were mentioned as an original plan ("control several buzzers") — only one buzzer pin (GPIO10) has been tested so far.

## Gotchas for next agent
- **COM12 serial port locking**: only one process can hold the ESP32-C3 serial port at a time. PyMakr's own terminal client (`node.exe ... pymakr .../client.js ... serial COM12`) will block `mpremote` commands with "failed to access com12 (it may be in use by another program)". Find and stop that specific node process (check `Get-CimInstance Win32_Process` for `CommandLine -match 'com12'`) rather than guessing — don't kill VS Code itself. Sometimes a stale handle persists even after the process is gone; unplugging/replugging the USB cable is the fallback fix.
- When testing scripts without permanently installing them as the device's boot file, use `mpremote connect com12 run <path>` rather than overwriting `main.py` on the device.

# Application settings and diagnostics

Music Box creates `settings.json` at runtime. Neither this file, its temporary
save file, nor Wi-Fi credentials are included in remote releases.

On startup, valid local settings take priority. If the local file is missing or
unreadable, the app uses `platform_services.installation_context().previous_path`
to read the previous installation's settings, when available. It never changes
that previous file. Without usable previous settings, it creates defaults.

The settings `version` is a schema version, not an application release version.
Schema 2 retains volume and accelerometer calibration and adds `about_text`.
Migration functions in `settings.py` explicitly upgrade older schemas; future
key renames or unit changes should be implemented in additional migration steps.
New keys receive defaults, retired/unknown keys are dropped, and invalid values
fall back to defaults. Unknown newer schemas are not blindly imported. Saves
use a temporary file followed by an atomic replacement.

Defaults: volume 75%, no IMU calibration, and the message
`Para mi Carly. Con amor, Samu <3`. Edit `about_text` in the device's settings
to customize it. About shows the framework's installed version (or the standalone
version), live Wi-Fi network/status, and the message; rotate to scroll long messages.
The radio normally turns off between update checks, so About may show Offline.

Hardware test plays a half-second tone on each of the four buzzers at the saved
volume, blinks the active-low GPIO8 LED, and alternates accelerometer (g) and
gyroscope (degrees/second) readings. Wi-Fi tests connection/IP acquisition, not
internet reachability or throughput. It requests the framework's connection
service without taking over its radio; a standalone upload can use a locally
provisioned `wifi_secrets.py`. Results time out after 45 seconds. Click to leave;
buzzers stop and the LED switches off. Buzzer audibility and LED operation are
confirmed by the person using the test, not inferred by software.

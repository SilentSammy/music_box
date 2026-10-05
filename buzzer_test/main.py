"""Passive piezo buzzer test for ESP32-C3.

Wiring:
    buzzer 1 + -> GPIO5
    buzzer 2 + -> GPIO9
    buzzer 3 + -> GPIO10
    buzzer 4 + -> GPIO20
    all buzzer - terminals -> GND

The sequence plays once at startup. Use a transistor driver for a magnetic
buzzer or speaker that draws more current than a GPIO can safely supply.
"""
from machine import Pin, PWM
import time

BUZZERS = (
    (5, "C5", 523),
    (9, "E5", 659),
    (10, "G5", 784),
    (20, "C6", 1047),
)
MAX_TONE_DUTY = 32_768  # 50% electrical duty produces the strongest square wave.


def volume_to_duty(volume):
    """Convert a normalized volume (0.0 to 1.0) to audio-tapered PWM duty."""
    if not 0.0 <= volume <= 1.0:
        raise ValueError("volume must be between 0.0 and 1.0")
    return round(MAX_TONE_DUTY * volume ** 3)


VOLUMES = (0.1, 0.25, 0.5, 1.0)


def play_tone(buzzer, frequency, volume, duration_ms=600):
    buzzer.freq(frequency)
    buzzer.duty_u16(volume)
    time.sleep_ms(duration_ms)
    buzzer.duty_u16(0)
    time.sleep_ms(250)


buzzers = [
    (pin_number, note_name, frequency, PWM(Pin(pin_number), duty_u16=0))
    for pin_number, note_name, frequency in BUZZERS
]

try:
    time.sleep_ms(500)
    for pin_number, note_name, frequency, buzzer in buzzers:
        print("GPIO", pin_number, "-", note_name, "-", frequency, "Hz")
        for volume in VOLUMES:
            duty = volume_to_duty(volume)
            print("  Volume:", volume, "- duty:", duty)
            play_tone(buzzer, frequency, duty)
        time.sleep_ms(750)
finally:
    for pin_number, note_name, frequency, buzzer in buzzers:
        buzzer.duty_u16(0)
        buzzer.deinit()

print("Buzzer test complete")

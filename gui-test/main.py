"""Music box menu demo.

This file owns the menu contents, navigation links, and encoder mapping.
The Menu helper knows nothing about encoders or how screens are connected.
"""
from machine import I2C, Pin
import time

from menu import Menu
from quadrature_encoder import Encoder
from ssd1306_driver import SSD1306

i2c = I2C(0, scl=Pin(7), sda=Pin(6), freq=400_000)
display = SSD1306(i2c)
encoder = Encoder(clk_pin=3, dt_pin=1, sw_pin=0)


def show_main_menu():
    menu.set_menu(main_menu)


def show_play_menu():
    menu.set_menu(play_menu)


def show_settings_menu():
    menu.set_menu(settings_menu)


def play_song_a():
    print("Playing: Song A")


def play_song_b():
    print("Playing: Song B")


def volume_up():
    print("Volume up")


def volume_down():
    print("Volume down")


def show_about():
    print("Music Box v0.1")


play_menu = (
    ("< Back", show_main_menu),
    ("Song A", play_song_a),
    ("Song B", play_song_b),
)

settings_menu = (
    ("< Back", show_main_menu),
    ("Volume Up", volume_up),
    ("Volume Down", volume_down),
)

main_menu = (
    ("Play", show_play_menu),
    ("Settings", show_settings_menu),
    ("About", show_about),
    ("Settings", show_settings_menu),
    ("About", show_about),
    ("Settings", show_settings_menu),
    ("About", show_about),
    ("Settings", show_settings_menu),
    ("About", show_about),
)

menu = Menu(display, main_menu)


def encoder_turned(delta):
    scroll = menu.scroll_down if delta > 0 else menu.scroll_up
    for _ in range(abs(delta)):
        scroll()


def encoder_pressed():
    menu.select()


while True:
    delta = encoder.take_delta()
    if delta:
        encoder_turned(delta)

    for _ in range(encoder.take_presses()):
        encoder_pressed()

    time.sleep_ms(20)

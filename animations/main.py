"""Standalone animation sandbox for the Music Box hardware."""
from animation_engine import AnimationEngine
from button_balls import ButtonBalls
from caption_overlay import CaptionOverlay
from hardware import Hardware


# Change this one assignment to choose which animation starts at boot.
ACTIVE_ANIMATION = ButtonBalls
# Set to an empty string to hide the caption.
ANIMATION_TEXT = ""


def main(max_frames=None):
    hardware = Hardware()
    engine = AnimationEngine(hardware, frames_per_second=20)

    try:
        engine.push(ACTIVE_ANIMATION())
        if ANIMATION_TEXT:
            engine.push(CaptionOverlay(ANIMATION_TEXT))
        return engine.run(max_frames=max_frames)
    finally:
        engine.close()


if __name__ == "__main__":
    main()

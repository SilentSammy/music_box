"""Cooperative, allocation-light animation timer scheduler."""
import time

from events import Event, TIMER


class TimerHandle:
    __slots__ = (
        "deadline",
        "interval_ms",
        "callback",
        "owner",
        "repeat",
        "catch_up",
        "cancelled",
    )

    def __init__(
        self,
        deadline,
        interval_ms,
        callback,
        owner,
        repeat,
        catch_up,
    ):
        self.deadline = deadline
        self.interval_ms = interval_ms
        self.callback = callback
        self.owner = owner
        self.repeat = repeat
        self.catch_up = catch_up
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class Scheduler:
    def __init__(self):
        self._timers = []

    def after(self, delay_ms, callback, owner=None):
        return self._add(delay_ms, 0, callback, owner, False, False)

    def every(self, interval_ms, callback, owner=None, catch_up=True):
        return self._add(
            interval_ms,
            interval_ms,
            callback,
            owner,
            True,
            catch_up,
        )

    def _add(
        self,
        delay_ms,
        interval_ms,
        callback,
        owner,
        repeat,
        catch_up,
    ):
        if delay_ms < 0 or interval_ms < 0:
            raise ValueError("timer delays cannot be negative")
        handle = TimerHandle(
            time.ticks_add(time.ticks_ms(), delay_ms),
            interval_ms,
            callback,
            owner,
            repeat,
            catch_up,
        )
        self._timers.append(handle)
        return handle

    def cancel_owner(self, owner):
        for timer in self._timers:
            if timer.owner is owner:
                timer.cancelled = True

    def update(self, now_ms, context):
        dirty = False
        for timer in tuple(self._timers):
            if timer.cancelled:
                continue
            while time.ticks_diff(now_ms, timer.deadline) >= 0:
                event = Event(TIMER, timer, now_ms, timer.owner)
                dirty = bool(timer.callback(event, context)) or dirty
                if not timer.repeat or timer.cancelled:
                    timer.cancelled = True
                    break
                if timer.catch_up:
                    timer.deadline = time.ticks_add(
                        timer.deadline,
                        timer.interval_ms,
                    )
                else:
                    timer.deadline = time.ticks_add(
                        now_ms,
                        timer.interval_ms,
                    )
                    break
        self._timers = [timer for timer in self._timers if not timer.cancelled]
        return dirty

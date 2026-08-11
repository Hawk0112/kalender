"""Loest den Summer aus, wenn eine Erinnerung faellig wird.

Wird als Ausgabe der Lautsprecher gewaehlt, macht dieser Teil nichts - dann
kommt der Ton wie bisher aus dem Browser. Beim Summer laeuft alles hier im
Dienst, unabhaengig davon, ob ueberhaupt eine Anzeige laeuft.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as clock, timedelta

from .events import collect_alarms, expand

log = logging.getLogger(__name__)

REFRESH_SECONDS = 60.0


class AlarmRunner(threading.Thread):
    def __init__(self, context, buzzer):
        super().__init__(daemon=True, name="alarm-runner")
        self.context = context
        self.buzzer = buzzer
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._alarms: list[dict] = []
        self._fired: set[str] = set()
        self._next_refresh = 0.0
        self._ringing: dict | None = None
        self._ends_at = 0.0

    # -- Steuerung -------------------------------------------------------
    def shutdown(self) -> None:
        self._stop.set()
        self.silence()

    def silence(self) -> None:
        """Laufenden Alarm beenden - vom Taster, aus der Anzeige oder per Zeit."""
        with self._lock:
            active = self._ringing is not None
            self._ringing = None
            self._ends_at = 0.0
        if active:
            log.info("Summer beendet.")
        self.buzzer.stop()

    def on_button(self, action: str) -> None:
        if action == "today":
            self.silence()

    def test(self, sound: str, seconds: float = 3.0) -> bool:
        """Tonprobe aus der Einstellungsseite."""
        config = self.context.config
        if not self.buzzer.play(sound, float(config.alarm["volume"])):
            return False
        with self._lock:
            self._ringing = {"title": "Tonprobe"}
            self._ends_at = time.monotonic() + max(0.5, seconds)
        return True

    def ringing(self) -> bool:
        with self._lock:
            return self._ringing is not None

    # -- Ablauf ----------------------------------------------------------
    def run(self) -> None:
        # Beim Start nichts nachholen, was waehrend eines Neustarts faellig war.
        self._refresh(mark_past=True)
        while not self._stop.wait(1.0):
            try:
                self._tick()
            except Exception:
                log.exception("Fehler beim Pruefen der Erinnerungen")

    def _tick(self) -> None:
        config = self.context.config
        alarm = config.alarm
        uses_buzzer = alarm["enabled"] and alarm["output"] == "buzzer"

        if not uses_buzzer:
            if self.ringing():
                self.silence()      # Ausgabe wurde umgestellt
            return
        if not self.buzzer.available:
            return

        now = time.monotonic()
        if now >= self._ends_at and self.ringing():
            self.silence()
        if now >= self._next_refresh:
            self._refresh()
            self._next_refresh = now + REFRESH_SECONDS
        if self.ringing():
            return

        due = self._due_alarm(config)
        if due is not None:
            self._fire(due, alarm)

    def _due_alarm(self, config) -> dict | None:
        now = datetime.now(config.tz)
        with self._lock:
            alarms = list(self._alarms)
        for entry in alarms:
            if entry["id"] in self._fired:
                continue
            moment = datetime.fromisoformat(entry["at"])
            if moment > now:
                continue
            self._fired.add(entry["id"])
            # Nur ausloesen, was gerade erst faellig wurde.
            if (now - moment).total_seconds() < 120:
                return entry
        return None

    def _fire(self, entry: dict, alarm: dict) -> None:
        if alarm["stop_mode"] == "key":
            seconds = float(alarm.get("hard_limit_seconds", 300))
        else:
            seconds = float(alarm["duration_seconds"])

        if not self.buzzer.play(alarm["sound"], float(alarm["volume"])):
            return
        with self._lock:
            self._ringing = entry
            self._ends_at = time.monotonic() + seconds
        log.info("Erinnerung: %s (Summer, %.0f s)", entry["title"], seconds)

    # -- Erinnerungen einsammeln ----------------------------------------
    def _refresh(self, mark_past: bool = False) -> None:
        config = self.context.config
        store = self.context.store
        sources = {source["id"]: source for source in config.calendars}

        now = datetime.now(config.tz)
        start = datetime.combine(now.date(), clock.min, tzinfo=config.tz)
        horizon = start + timedelta(days=config.days + 2)

        events = []
        for state in store.snapshot().sources:
            source = sources.get(state.id)
            if state.calendar is None or source is None:
                continue
            events.extend(
                expand(state.calendar, source, start, horizon, config.tz, config.highlights)
            )

        alarms = collect_alarms(
            events, now, horizon, bool(config.alarm["at_event_start"])
        )
        with self._lock:
            self._alarms = alarms

        known = {entry["id"] for entry in alarms}
        self._fired &= known          # Erledigtes vergessen, was nicht mehr ansteht
        if mark_past:
            for entry in alarms:
                if datetime.fromisoformat(entry["at"]) <= now:
                    self._fired.add(entry["id"])

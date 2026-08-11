"""Hintergrund-Aktualisierung und Zwischenspeicher der geparsten Kalender."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from icalendar import Calendar

from .config import Config
from .events import parse_calendar
from .sources import SourceFetcher

log = logging.getLogger(__name__)


@dataclass
class SourceState:
    id: str
    name: str
    color: str
    url: str = ""
    calendar: Calendar | None = None
    ok: bool = False
    from_cache: bool = False
    error: str | None = None
    last_success: datetime | None = None


@dataclass
class StoreSnapshot:
    sources: list[SourceState] = field(default_factory=list)
    last_attempt: datetime | None = None
    last_success: datetime | None = None


class CalendarStore:
    """Haelt die geparsten Kalender und aktualisiert sie im Hintergrund."""

    def __init__(self, config: Config, cache_dir: Path):
        self.config = config
        self.fetcher = SourceFetcher(cache_dir, timeout=int(config.refresh["timeout_seconds"]))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = {
            source["id"]: SourceState(
                source["id"], source["name"], source["color"], source["url"]
            )
            for source in config.calendars
        }
        self._last_attempt: datetime | None = None
        self._last_success: datetime | None = None

    def apply_config(self, config: Config) -> None:
        """Neue Konfiguration uebernehmen, ohne den Dienst neu zu starten."""
        with self._lock:
            self.config = config
            self.fetcher.timeout = int(config.refresh["timeout_seconds"])
            previous = {state.url: state for state in self._state.values()}
            fresh: dict[str, SourceState] = {}
            for source in config.calendars:
                state = SourceState(
                    source["id"], source["name"], source["color"], source["url"]
                )
                # Gleiche Adresse wie vorher: Daten weiterverwenden, damit die
                # Anzeige waehrend des naechsten Abrufs nicht leer wird.
                old = previous.get(source["url"])
                if old is not None:
                    state.calendar = old.calendar
                    state.ok = old.ok
                    state.from_cache = old.from_cache
                    state.last_success = old.last_success
                fresh[source["id"]] = state
            self._state = fresh
        self.refresh_now()

    # -- Lebenszyklus ----------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="calendar-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            all_ok = self.refresh()
            # Intervalle bei jedem Durchlauf neu lesen - sie koennen sich ueber
            # die Einstellungsseite geaendert haben.
            interval = timedelta(minutes=float(self.config.refresh["interval_minutes"]))
            retry = timedelta(minutes=float(self.config.refresh["retry_minutes"]))
            wait = interval if all_ok else retry
            self._wake.wait(wait.total_seconds())
            self._wake.clear()

    # -- Abruf -----------------------------------------------------------
    def refresh(self) -> bool:
        all_ok = True
        now = datetime.now(timezone.utc)
        for source in self.config.calendars:
            result = self.fetcher.fetch(source)
            state = SourceState(
                source["id"], source["name"], source["color"], source["url"]
            )

            if result.text is not None:
                try:
                    state.calendar = parse_calendar(result.text)
                    state.ok = result.error is None
                    state.from_cache = result.from_cache
                    state.error = result.error
                    state.last_success = result.fetched_at
                except Exception as exc:
                    log.error("ICS von %s nicht lesbar: %s", source["name"], exc)
                    state.error = f"ICS nicht lesbar: {exc}"
            else:
                state.error = result.error or "Kein Ergebnis"

            if not state.ok:
                all_ok = False

            with self._lock:
                previous = self._state.get(source["id"])
                # Bei Fehlschlag ohne Cache die zuletzt gute Fassung behalten.
                if state.calendar is None and previous is not None and previous.calendar is not None:
                    state.calendar = previous.calendar
                    state.from_cache = True
                    state.last_success = previous.last_success
                self._state[source["id"]] = state

        with self._lock:
            self._last_attempt = now
            if all_ok:
                self._last_success = now
            log.info(
                "Aktualisierung %s (%d Quellen)",
                "ok" if all_ok else "mit Fehlern",
                len(self.config.calendars),
            )
        return all_ok

    # -- Lesen -----------------------------------------------------------
    def snapshot(self) -> StoreSnapshot:
        with self._lock:
            return StoreSnapshot(
                sources=list(self._state.values()),
                last_attempt=self._last_attempt,
                last_success=self._last_success,
            )

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        stale_after = timedelta(minutes=float(self.config.refresh["stale_after_minutes"]))
        now = datetime.now(timezone.utc)

        problems = [
            {"calendar": state.name, "message": state.error}
            for state in snap.sources
            if state.error
        ]
        newest = max(
            (state.last_success for state in snap.sources if state.last_success),
            default=None,
        )
        return {
            "online": not problems,
            "stale": newest is None or (now - newest) > stale_after,
            "last_success": newest.isoformat() if newest else None,
            "last_attempt": snap.last_attempt.isoformat() if snap.last_attempt else None,
            "problems": problems,
            "calendars": [
                {
                    "name": state.name,
                    "color": state.color,
                    "ok": state.ok,
                    "from_cache": state.from_cache,
                }
                for state in snap.sources
            ],
        }

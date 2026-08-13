"""Physische Taster am GPIO.

Drei Taster mit je einer Aufgabe:

* ``today``   - kurz: Alarmton beenden, sonst zurueck auf die aktuelle Woche.
                lang: System neu starten.
* ``forward`` - eine Woche vorwaerts
* ``back``    - eine Woche zurueck

Die Anzeige laeuft im Browser, deshalb zaehlt dieser Dienst nur die
Tastendruecke; die Anzeige holt sich die Zaehlerstaende ab und reagiert darauf.
Der Neustart bei langem Druck laeuft dagegen bewusst vollstaendig hier ab -
gerade wenn Browser oder Bildschirm haengen, soll der Taster noch wirken.

Fehlt die Hardware (Entwicklung am PC) oder ist ein Pin belegt, laeuft alles
Uebrige unveraendert weiter; der betroffene Taster wird als nicht verfuegbar
gemeldet.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

ACTIONS = ("today", "forward", "back")

# Erster Befehl, der sich ausfuehren laesst, gewinnt. Das dafuer noetige
# sudo-Recht legt install.sh an - eng begrenzt auf genau diesen Befehl.
REBOOT_COMMANDS = [
    ["sudo", "-n", "/usr/sbin/reboot"],
    ["sudo", "-n", "/sbin/reboot"],
]


def reboot_system() -> None:
    """System neu starten. Wirft eine Ausnahme, wenn kein Befehl greift."""
    last_error = "kein Befehl ausfuehrbar"
    for command in REBOOT_COMMANDS:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        except FileNotFoundError:
            last_error = f"{command[-1]} nicht vorhanden"
            continue
        except subprocess.TimeoutExpired:
            return  # Der Neustart laeuft bereits.
        if result.returncode == 0:
            return
        last_error = (result.stderr or result.stdout or "").strip() or (
            f"Rueckgabewert {result.returncode}"
        )
    raise RuntimeError(
        f"{last_error}. Fehlt die sudo-Regel? Siehe install.sh bzw. "
        "/etc/sudoers.d/kalender-reboot"
    )


class ButtonWatcher:
    def __init__(
        self,
        settings: dict[str, Any],
        on_reboot: Callable[[], None] | None = None,
    ):
        self.enabled = bool(settings.get("enabled", True))
        self.pull_up = bool(settings.get("pull_up", True))
        self.bounce_time = float(settings.get("bounce_time", 0.05))
        # 0 schaltet den Neustart per langem Druck ab.
        self.reboot_hold_seconds = float(settings.get("reboot_hold_seconds", 20))
        # 0 bedeutet: dieser Taster ist nicht angeschlossen.
        self.pins: dict[str, int] = {
            "today": int(settings.get("gpio", 17)),
            "forward": int(settings.get("gpio_forward", 0)),
            "back": int(settings.get("gpio_back", 0)),
        }

        self._lock = threading.Lock()
        self._counts = {action: 0 for action in ACTIONS}
        self._last: datetime | None = None
        self._changed = threading.Event()
        self._devices: dict[str, Any] = {}
        self._errors: dict[str, str] = {}
        self._rebooting = False
        self._on_reboot = on_reboot or self._reboot
        self._listeners: list[Callable[[str], None]] = []
        self.error: str | None = None

    def add_listener(self, callback: Callable[[str], None]) -> None:
        """Wird bei jedem Tastendruck mit der Aufgabe aufgerufen."""
        self._listeners.append(callback)

    # -- Lebenszyklus ----------------------------------------------------
    def start(self) -> None:
        if not self.enabled:
            self.error = "in der Konfiguration abgeschaltet"
            return
        try:
            from gpiozero import Button  # type: ignore[import-not-found]
        except Exception:
            self.error = "gpiozero nicht installiert"
            log.info("Taster nicht aktiv: %s", self.error)
            return

        for action in ACTIONS:
            pin = self.pins[action]
            if pin <= 0:
                continue
            try:
                options: dict[str, Any] = {
                    "pull_up": self.pull_up,
                    "bounce_time": self.bounce_time,
                }
                if action == "today" and self.reboot_hold_seconds > 0:
                    options["hold_time"] = self.reboot_hold_seconds
                    options["hold_repeat"] = False

                device = Button(pin, **options)
                device.when_pressed = self._make_handler(action)
                if action == "today" and self.reboot_hold_seconds > 0:
                    device.when_held = self._on_hold
                self._devices[action] = device
                log.info("Taster '%s' aktiv an GPIO%d", action, pin)
            except Exception as exc:
                self._errors[action] = str(exc)
                log.warning("Taster '%s' an GPIO%d nicht nutzbar: %s", action, pin, exc)

        if not self._devices:
            self.error = self._errors.get("today") or "kein Taster nutzbar"
        elif self.reboot_hold_seconds > 0 and "today" in self._devices:
            log.info("Neustart bei %.0f s Dauerdruck", self.reboot_hold_seconds)

    def stop(self) -> None:
        for device in self._devices.values():
            try:
                device.close()
            except Exception:
                pass
        self._devices.clear()
        self._changed.set()

    # -- Zaehler ---------------------------------------------------------
    def _make_handler(self, action: str) -> Callable[[], None]:
        def handler() -> None:
            count = self.press(action)
            log.info("Taster '%s' gedrueckt (%d)", action, count)

        return handler

    def press(self, action: str) -> int:
        """Einen Tastendruck vermerken - auch von aussen ausloesbar."""
        if action not in ACTIONS:
            raise ValueError(f"Unbekannte Taste: {action}")
        with self._lock:
            self._counts[action] += 1
            self._last = datetime.now(timezone.utc)
            count = self._counts[action]
        self._changed.set()
        for listener in self._listeners:
            try:
                listener(action)
            except Exception:
                log.exception("Fehler beim Melden des Tastendrucks")
        return count

    def counter(self) -> dict[str, Any]:
        with self._lock:
            counts = dict(self._counts)
            last = self._last
        counts["total"] = sum(counts[action] for action in ACTIONS)
        counts["at"] = last.isoformat() if last else None
        return counts

    def wait(self, since: int, timeout: float = 25.0) -> dict[str, Any]:
        """Warten, bis sich ein Zaehler aendert - hoechstens 'timeout' Sekunden.

        So reagiert die Anzeige ohne staendiges Nachfragen sofort auf einen
        Tastendruck.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            state = self.counter()
            if state["total"] != since:
                return state
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return state
            # Kurze Schritte: so geht auch ein Ereignis nicht verloren, das
            # zwischen zwei Durchlaeufen gemeldet wurde.
            self._changed.wait(min(remaining, 1.0))
            self._changed.clear()

    @property
    def available(self) -> bool:
        return bool(self._devices)

    def state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "reboot_hold_seconds": self.reboot_hold_seconds,
            "error": self.error,
            "buttons": {
                action: {
                    "gpio": self.pins[action],
                    "available": action in self._devices,
                    "error": self._errors.get(action),
                }
                for action in ACTIONS
            },
        }

    # -- langer Druck ----------------------------------------------------
    def _on_hold(self) -> None:
        # Bei einem klemmenden Taster sonst ein Neustart nach dem anderen.
        with self._lock:
            if self._rebooting:
                return
            self._rebooting = True
        log.warning(
            "Taster %.0f s gehalten - System wird neu gestartet.",
            self.reboot_hold_seconds,
        )
        try:
            self._on_reboot()
        except Exception as exc:
            log.error("Neustart fehlgeschlagen: %s", exc)
            with self._lock:
                self._rebooting = False

    def _reboot(self) -> None:
        reboot_system()

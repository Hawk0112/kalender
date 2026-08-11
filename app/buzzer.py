"""Piezo-Summer am GPIO als Alarmgeber.

Der Summer haengt zwischen einem GPIO-Pin und GND. Toene entstehen ueber ein
Rechtecksignal (PWM): die Frequenz bestimmt die Tonhoehe, das Tastverhaeltnis
grob die Lautstaerke. Ein Piezo kann keine Klangfarben, deshalb sind die
Melodien schlichte Ton-Pausen-Muster - fuer einen Wecker reicht das.

Gegenueber dem Ton aus dem Browser hat das einen Vorteil: Es klingelt auch,
wenn der Bildschirm aus ist oder der Browser haengt.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

# Je Eintrag (Frequenz in Hz, Dauer in Sekunden); Frequenz 0 bedeutet Pause.
# Die Kennungen entsprechen den Toenen im Browser, damit die Einstellung
# unabhaengig von der gewaehlten Ausgabe gilt.
PATTERNS: dict[str, list[tuple[float, float]]] = {
    "beep": [(1000, 0.13), (0, 0.09), (1000, 0.13), (0, 1.15)],
    "alarm": [
        (950, 0.12), (700, 0.12), (950, 0.12), (700, 0.12),
        (950, 0.12), (700, 0.12), (950, 0.12), (700, 0.12),
        (0, 0.55),
    ],
    "chime": [(880, 0.18), (1109, 0.18), (1319, 0.5), (0, 1.7)],
    "gong": [(220, 0.5), (180, 0.9), (0, 1.8)],
    "soft": [(523, 0.35), (0, 0.25), (523, 0.35), (0, 3.0)],
}
DEFAULT_PATTERN = "beep"


class Buzzer:
    def __init__(self, settings: dict[str, Any]):
        self.gpio = int(settings.get("buzzer_gpio", 18))
        self._device = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    # -- Lebenszyklus ----------------------------------------------------
    def start(self) -> None:
        if self.gpio <= 0:
            self.error = "kein Pin eingetragen"
            return
        try:
            from gpiozero import PWMOutputDevice  # type: ignore[import-not-found]
        except Exception:
            self.error = "gpiozero nicht installiert"
            log.info("Summer nicht aktiv: %s", self.error)
            return
        try:
            self._device = PWMOutputDevice(self.gpio, frequency=1000, initial_value=0)
            log.info("Summer aktiv an GPIO%d", self.gpio)
        except Exception as exc:
            # Manche Ausnahmen tragen keinen Text - dann wenigstens die Art nennen.
            self.error = str(exc) or type(exc).__name__
            log.warning("Summer an GPIO%d nicht nutzbar: %s", self.gpio, self.error)

    def close(self) -> None:
        self.stop()
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @property
    def available(self) -> bool:
        return self._device is not None

    def state(self) -> dict[str, Any]:
        return {"gpio": self.gpio, "available": self.available, "error": self.error}

    # -- Toene -----------------------------------------------------------
    def _tone(self, frequency: float, duty: float) -> None:
        device = self._device
        if device is None:
            return
        try:
            if frequency <= 0:
                device.value = 0
            else:
                device.frequency = frequency
                device.value = duty
        except Exception as exc:
            log.warning("Summer nicht ansteuerbar: %s", exc)

    def play(self, sound: str, volume: float = 0.8) -> bool:
        """Muster wiederholt abspielen, bis stop() kommt."""
        if not self.available:
            return False
        pattern = PATTERNS.get(sound) or PATTERNS[DEFAULT_PATTERN]
        # Beim Rechtecksignal ist 50 % am lautesten; darunter wird es leiser.
        duty = max(0.02, min(0.5, 0.5 * float(volume)))

        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(pattern, duty), name="buzzer", daemon=True
        )
        self._thread.start()
        return True

    def _loop(self, pattern: list[tuple[float, float]], duty: float) -> None:
        try:
            while not self._stop.is_set():
                for frequency, seconds in pattern:
                    if self._stop.is_set():
                        break
                    self._tone(frequency, duty)
                    if self._stop.wait(seconds):
                        break
        finally:
            self._tone(0, 0)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._tone(0, 0)

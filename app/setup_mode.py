"""Einrichtung per Handy: zeitlich begrenzter Zugang aus dem Heimnetz.

Der Kalender zeigt auf Wunsch einen QR-Code. Wer ihn mit dem Handy scannt,
landet unmittelbar auf der Einstellungsseite und kann die Kalenderadresse dort
mit einer richtigen Tastatur eintippen oder einfuegen - ohne SSH, ohne Konto,
ohne dass die Adresse das Heimnetz verlaesst.

Damit nicht dauerhaft jeder im Netz an den Einstellungen drehen kann:

* Der Zugang gilt nur, solange der Einrichtungsmodus laeuft (Standard 15 min).
* Er verlangt eine Kennung, die ausschliesslich auf dem Bildschirm steht -
  entweder im QR-Code oder als sechsstellige Zahl zum Abtippen.
* Vom Geraet selbst (127.0.0.1) ist alles wie bisher erreichbar.
"""

from __future__ import annotations

import io
import logging
import secrets
import socket
import threading
import time
from typing import Any

log = logging.getLogger(__name__)


def local_ip() -> str:
    """Adresse, unter der das Geraet im Heimnetz erreichbar ist."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Verbindet nicht wirklich, waehlt nur die passende Schnittstelle aus.
        probe.connect(("8.8.8.8", 53))
        return probe.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""
    finally:
        probe.close()


LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class SetupMode:
    def __init__(self, minutes: float = 15.0, port: int = 8080, host: str = "0.0.0.0"):
        self.minutes = float(minutes)
        self.port = int(port)
        # Lauscht der Dienst nur auf dem Geraet selbst, kann kein Handy
        # herankommen - dann ist der QR-Code sinnlos.
        self.host = str(host)
        self._lock = threading.Lock()
        self._until = 0.0
        self._token = ""
        self._code = ""

    # -- Zustand ---------------------------------------------------------
    @property
    def active(self) -> bool:
        with self._lock:
            return time.monotonic() < self._until

    def remaining(self) -> int:
        with self._lock:
            return max(0, int(self._until - time.monotonic()))

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._token = secrets.token_urlsafe(16)
            self._code = f"{secrets.randbelow(900000) + 100000}"
            self._until = time.monotonic() + self.minutes * 60
        log.info("Einrichtungsmodus fuer %.0f Minuten geoeffnet", self.minutes)
        return self.info()

    def stop(self) -> None:
        with self._lock:
            self._until = 0.0
            self._token = ""
            self._code = ""
        log.info("Einrichtungsmodus beendet")

    # -- Pruefung --------------------------------------------------------
    def token_ok(self, value: str) -> bool:
        with self._lock:
            if not self._token or time.monotonic() >= self._until:
                return False
            return secrets.compare_digest(value or "", self._token)

    def code_ok(self, value: str) -> bool:
        with self._lock:
            if not self._code or time.monotonic() >= self._until:
                return False
            return secrets.compare_digest((value or "").strip(), self._code)

    def token(self) -> str:
        with self._lock:
            return self._token

    # -- Anzeige ---------------------------------------------------------
    def url(self) -> str:
        ip = local_ip()
        return f"http://{ip}:{self.port}" if ip else ""

    def reachable(self) -> tuple[bool, str]:
        """Kann ein Handy das Geraet ueberhaupt erreichen?"""
        if self.host in LOOPBACK:
            return False, (
                "Der Dienst ist auf das Gerät beschränkt. Für die Einrichtung "
                "per Handy in config.yaml server.host auf 0.0.0.0 setzen und "
                "den Dienst neu starten."
            )
        if not local_ip():
            return False, "Keine Netzwerkadresse gefunden – hängt das Gerät im Netz?"
        return True, ""

    def info(self, with_qr: bool = True) -> dict[str, Any]:
        aktiv = self.active
        erreichbar, grund = self.reachable()
        basis = self.url() if erreichbar else ""
        with self._lock:
            token, code = self._token, self._code
        ziel = f"{basis}/setup?t={token}" if (aktiv and basis) else ""

        daten: dict[str, Any] = {
            "active": aktiv,
            "remaining": self.remaining(),
            "minutes": self.minutes,
            "address": basis,
            "code": code if aktiv else "",
            "url": ziel,
            "reachable": erreichbar,
            "reason": grund,
        }
        if with_qr and ziel:
            daten["qr"] = self.qr_svg(ziel)
        return daten

    @staticmethod
    def qr_svg(text: str) -> str:
        try:
            import segno  # type: ignore[import-not-found]
        except Exception:
            log.warning("segno nicht installiert - kein QR-Code moeglich")
            return ""
        try:
            code = segno.make(text, error="m")
            # omitsize laesst width/height weg und setzt stattdessen eine
            # viewBox. Nur damit skaliert der Browser die Zeichnung mit - sonst
            # bliebe sie winzig in der linken oberen Ecke stehen.
            return code.svg_inline(
                scale=1, border=2, omitsize=True, dark="#000000", light="#ffffff"
            )
        except Exception as exc:
            log.warning("QR-Code nicht erzeugbar: %s", exc)
            return ""

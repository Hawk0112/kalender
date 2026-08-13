"""Programmstand aus dem Git-Repository nachziehen.

Ablauf beim Knopfdruck in den Einstellungen:

1. Beim Repository nachfragen, ob es etwas Neueres gibt.
2. Wenn ja, den neuen Stand holen und die Bibliotheken abgleichen.
3. **Probelauf**: Laesst sich das Programm laden und die Konfiguration lesen?
   Schlaegt das fehl, wird der alte Stand wiederhergestellt und *nicht* neu
   gestartet - sonst stuende das Geraet nach dem Neustart mit einem defekten
   Programm da, und man kaeme nur noch per SSH heran.
4. Erst danach neu starten.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .button import reboot_system

log = logging.getLogger(__name__)

GIT_TIMEOUT = 90
PIP_TIMEOUT = 600
CHECK_TIMEOUT = 90
# Kurz warten, damit die Meldung in der Anzeige noch ankommt.
REBOOT_DELAY = 4.0


class UpdateError(Exception):
    pass


class Updater:
    def __init__(self, app_dir: Path, on_reboot: Callable[[], None] | None = None):
        self.app_dir = Path(app_dir)
        self._on_reboot = on_reboot or reboot_system
        self._lock = threading.Lock()
        self._busy = False

    # -- Hilfen ----------------------------------------------------------
    def _git(self, *args: str, timeout: int = GIT_TIMEOUT) -> str:
        env = dict(os.environ)
        # Nicht nach Zugangsdaten fragen - hier kann niemand antworten.
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.setdefault("GCM_INTERACTIVE", "never")
        try:
            result = subprocess.run(
                ["git", "-C", str(self.app_dir), *args],
                capture_output=True, text=True, timeout=timeout, env=env,
            )
        except FileNotFoundError:
            raise UpdateError("git ist nicht installiert.") from None
        except subprocess.TimeoutExpired:
            raise UpdateError(f"git {args[0]} hat zu lange gebraucht.") from None
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip().splitlines()
            raise UpdateError(message[-1] if message else f"git {args[0]} fehlgeschlagen")
        return result.stdout.strip()

    @property
    def _python(self) -> Path:
        venv = self.app_dir / ".venv"
        candidate = venv / "bin" / "python"
        return candidate if candidate.exists() else venv / "Scripts" / "python.exe"

    def available(self) -> bool:
        return (self.app_dir / ".git").exists()

    # -- Pruefen ---------------------------------------------------------
    def check(self) -> dict[str, Any]:
        if not self.available():
            raise UpdateError(
                "Kein Git-Repository - diese Installation wurde von Hand kopiert."
            )
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD") or "main"
        if branch == "HEAD":
            raise UpdateError("Kein Zweig ausgecheckt.")
        self._git("fetch", "origin", branch, "--quiet")

        local = self._git("rev-parse", "HEAD")
        remote = self._git("rev-parse", f"origin/{branch}")
        behind = 0
        if local != remote:
            counts = self._git("rev-list", "--left-right", "--count",
                               f"HEAD...origin/{branch}")
            parts = counts.split()
            behind = int(parts[1]) if len(parts) == 2 else 1

        return {
            "branch": branch,
            "local": local[:7],
            "remote": remote[:7],
            "update_available": local != remote,
            "commits": behind,
            "subject": (
                self._git("log", "-1", "--pretty=%s", f"origin/{branch}")
                if local != remote else ""
            ),
        }

    # -- Einspielen ------------------------------------------------------
    def run(self) -> dict[str, Any]:
        with self._lock:
            if self._busy:
                raise UpdateError("Es läuft bereits eine Aktualisierung.")
            self._busy = True
        try:
            return self._run()
        finally:
            with self._lock:
                self._busy = False

    def _run(self) -> dict[str, Any]:
        info = self.check()
        if not info["update_available"]:
            return {**info, "updated": False, "message": "Bereits auf dem neuesten Stand."}

        previous = self._git("rev-parse", "HEAD")
        branch = info["branch"]
        log.info("Aktualisierung: %s -> %s", previous[:7], info["remote"])

        self._git("reset", "--hard", f"origin/{branch}")
        try:
            changed = self._git("diff", "--name-only", previous, "HEAD").splitlines()
            if "requirements.txt" in changed:
                self._install_requirements()
            self._smoke_test()
        except UpdateError as exc:
            # Zurueck auf den Stand, der nachweislich lief.
            log.error("Aktualisierung verworfen: %s", exc)
            self._git("reset", "--hard", previous)
            raise UpdateError(f"{exc} Der vorherige Stand wurde wiederhergestellt.")

        kiosk_changed = any(name.startswith("kiosk/") for name in changed)
        self._schedule_reboot()
        return {
            **info,
            "updated": True,
            "from": previous[:7],
            "files": len(changed),
            "kiosk_changed": kiosk_changed,
            "message": f"Aktualisiert auf {info['remote']} – Neustart läuft.",
        }

    def _install_requirements(self) -> None:
        python = self._python
        if not python.exists():
            raise UpdateError("Python-Umgebung nicht gefunden.")
        try:
            result = subprocess.run(
                [str(python), "-m", "pip", "install", "--quiet", "-r",
                 str(self.app_dir / "requirements.txt")],
                capture_output=True, text=True, timeout=PIP_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise UpdateError("Nachladen der Bibliotheken hat zu lange gebraucht.") from None
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            raise UpdateError(f"Bibliotheken: {detail[-1] if detail else 'Fehler'}")

    def _smoke_test(self) -> None:
        """Prueft, ob der neue Stand ueberhaupt startfaehig ist."""
        python = self._python
        if not python.exists():
            raise UpdateError("Python-Umgebung nicht gefunden.")
        code = (
            "import app.server; "
            "from app.config import load_config; "
            "load_config('config.yaml'); "
            "print('ok')"
        )
        try:
            result = subprocess.run(
                [str(python), "-c", code], cwd=str(self.app_dir),
                capture_output=True, text=True, timeout=CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise UpdateError("Probelauf hat zu lange gebraucht.") from None
        if result.returncode != 0 or "ok" not in result.stdout:
            detail = (result.stderr or "").strip().splitlines()
            raise UpdateError(f"Probelauf fehlgeschlagen: {detail[-1] if detail else '?'}")

    def _schedule_reboot(self) -> None:
        def spaeter() -> None:
            time.sleep(REBOOT_DELAY)
            try:
                self._on_reboot()
            except Exception as exc:
                log.error("Neustart nach Aktualisierung fehlgeschlagen: %s", exc)

        threading.Thread(target=spaeter, name="update-reboot", daemon=True).start()

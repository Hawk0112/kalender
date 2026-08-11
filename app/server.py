"""HTTP-Server: liefert die Anzeige und die Termindaten als JSON."""

from __future__ import annotations

import argparse
import hashlib
import logging
import signal
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

from . import __version__

from flask import Flask, jsonify, request, send_from_directory

from .config import (
    Config,
    ConfigError,
    editable_settings,
    load_config,
    save_config,
    settings_to_raw,
)
from .alarm_runner import AlarmRunner
from .button import ButtonWatcher
from .buzzer import Buzzer
from .events import build_days, collect_alarms, expand, parse_calendar
from .sources import SourceFetcher
from .store import CalendarStore

log = logging.getLogger("kalender")

STATIC_DIR = Path(__file__).parent / "static"


def build_id() -> str:
    """Kennung des aktuellen Programmstands.

    Enthaelt einen Fingerabdruck der Dateien der Anzeige. Aendert er sich,
    laedt die Seite sich selbst neu - nach einem Update erscheint die neue
    Oberflaeche also ohne Zutun, ohne den Kiosk anzufassen.
    """
    parts = []
    try:
        for path in sorted(STATIC_DIR.iterdir()):
            if path.is_file():
                info = path.stat()
                parts.append(f"{path.name}:{info.st_mtime_ns}:{info.st_size}")
    except OSError:
        return __version__
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:10]
    return f"{__version__}+{digest}"


class AppContext:
    """Haelt die aktuell gueltige Konfiguration - sie kann sich zur Laufzeit aendern."""

    def __init__(
        self,
        config: Config,
        store: CalendarStore,
        button: ButtonWatcher,
        buzzer: Buzzer | None = None,
    ):
        self.config = config
        self.store = store
        self.button = button
        self.buzzer = buzzer
        self.alarms: AlarmRunner | None = None

    def reload(self, config: Config) -> None:
        self.config = config
        self.store.apply_config(config)


def create_app(ctx: AppContext) -> Flask:
    app = Flask(__name__, static_folder=None)
    store = ctx.store

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/api/refresh")
    def api_refresh():
        """Kalender sofort neu holen.

        Wartet auf das Ergebnis, damit der Knopf in den Einstellungen melden
        kann, ob es geklappt hat. Mit ?wait=0 kehrt der Aufruf sofort zurueck.
        """
        if request.args.get("wait") == "0":
            store.refresh_now()
            return jsonify({"ok": True, "waited": False})

        all_ok = store.refresh()
        status = store.status()
        return jsonify(
            {
                "ok": all_ok,
                "waited": True,
                "status": status,
                "problems": status["problems"],
            }
        )

    @app.get("/api/week")
    def api_week():
        config = ctx.config
        sources_by_id = {source["id"]: source for source in config.calendars}
        now = datetime.now(config.tz)

        # Verschiebung der Anzeige in Tagen; die Taster blaettern wochenweise.
        try:
            offset = int(request.args.get("offset", 0))
        except ValueError:
            offset = 0
        offset = max(-730, min(730, offset))

        today = now.date()
        first_day = today + timedelta(days=offset)
        window_start = datetime.combine(first_day, time.min, tzinfo=config.tz)
        window_end = window_start + timedelta(days=config.days)

        # Erinnerungen richten sich immer nach dem echten Heute, egal welche
        # Woche gerade angezeigt wird. Etwas ueber die Anzeige hinaus, weil
        # eine Erinnerung Tage vor dem Termin liegen kann.
        alarm_start = datetime.combine(today, time.min, tzinfo=config.tz)
        alarm_horizon = alarm_start + timedelta(days=config.days + 2)

        def collect(start: datetime, end: datetime) -> list:
            found = []
            for state in store.snapshot().sources:
                source = sources_by_id.get(state.id)
                if state.calendar is None or source is None:
                    continue
                found.extend(
                    expand(
                        state.calendar, source, start, end, config.tz, config.highlights
                    )
                )
            return found

        if offset == 0:
            # Anzeigefenster liegt im Erinnerungsfenster - eine Auswertung genuegt.
            events = collect(window_start, alarm_horizon)
            alarm_events = events
        else:
            events = collect(window_start, window_end)
            alarm_events = collect(alarm_start, alarm_horizon)

        view = dict(config.view)
        days = build_days(
            events,
            first_day,
            config.days,
            config.tz,
            now,
            int(view["day_start_hour"]),
            int(view["day_end_hour"]),
        )
        view["range"] = {
            "start_hour": int(view["day_start_hour"]),
            "end_hour": int(view["day_end_hour"]),
        }

        alarms = (
            collect_alarms(
                alarm_events, now, alarm_horizon, bool(config.alarm["at_event_start"])
            )
            if config.alarm["enabled"]
            else []
        )

        return jsonify(
            {
                "generated_at": now.isoformat(),
                "version": build_id(),
                "timezone": str(config.tz),
                "locale": config.locale,
                "offset_days": offset,
                "today": today.isoformat(),
                "view": view,
                "alarm": config.alarm,
                "alarms": alarms,
                "buzzer": ctx.buzzer.state() if ctx.buzzer else None,
                "button": ctx.button.state(),
                "status": store.status(),
                "days": days,
            }
        )

    # -- Taster ----------------------------------------------------------
    @app.get("/api/button")
    def api_button():
        """Aktuelle Zaehlerstaende der Taster."""
        return jsonify(ctx.button.counter())

    @app.get("/api/button/wait")
    def api_button_wait():
        """Wartet auf den naechsten Tastendruck und antwortet dann sofort.

        Die Anzeige haengt dauerhaft in dieser Abfrage. So reagiert sie ohne
        Verzoegerung, ohne im Leerlauf staendig nachzufragen.
        """
        try:
            since = int(request.args.get("since", -1))
        except ValueError:
            since = -1
        return jsonify(ctx.button.wait(since, timeout=25.0))

    @app.post("/api/button/press")
    def api_button_press():
        """Tastendruck ausloesen - zum Pruefen ohne Hardware."""
        action = str(request.args.get("action") or "today")
        try:
            count = ctx.button.press(action)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "action": action, "presses": count})

    # -- Alarm -----------------------------------------------------------
    @app.post("/api/alarm/stop")
    def api_alarm_stop():
        """Laufenden Alarm beenden - auch den Summer, wenn er gerade laeutet."""
        if ctx.alarms is not None:
            ctx.alarms.silence()
        return jsonify({"ok": True})

    @app.post("/api/alarm/test")
    def api_alarm_test():
        """Tonprobe auf dem Summer, fuer den Knopf in den Einstellungen."""
        sound = str(request.args.get("sound") or ctx.config.alarm["sound"])
        if ctx.config.alarm["output"] != "buzzer":
            return jsonify(
                {"ok": False, "error": "Ausgabe steht auf Lautsprecher - "
                                       "erst umstellen und speichern."}
            )
        if ctx.alarms is None or ctx.buzzer is None or not ctx.buzzer.available:
            reason = ctx.buzzer.error if ctx.buzzer else "kein Summer eingerichtet"
            return jsonify({"ok": False, "error": reason or "Summer nicht verfügbar"})
        if not ctx.alarms.test(sound, seconds=3.0):
            return jsonify({"ok": False, "error": "Summer antwortet nicht"})
        return jsonify({"ok": True})

    # -- Einstellungsseite ----------------------------------------------
    @app.get("/api/settings")
    def api_settings_get():
        return jsonify(editable_settings(ctx.config))

    @app.put("/api/settings")
    def api_settings_put():
        try:
            raw = settings_to_raw(request.get_json(silent=True), ctx.config)
            save_config(ctx.config.path, raw)
        except ConfigError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except OSError as exc:
            log.error("Konfiguration nicht schreibbar: %s", exc)
            return jsonify({"ok": False, "error": f"Datei nicht schreibbar: {exc}"}), 500

        try:
            config = load_config(ctx.config.path)
        except ConfigError as exc:
            # Sollte nach der Pruefung nicht vorkommen; dann lieber ehrlich melden.
            log.error("Gespeicherte Konfiguration nicht ladbar: %s", exc)
            return jsonify({"ok": False, "error": str(exc)}), 500

        ctx.reload(config)
        log.info("Einstellungen geaendert: %d Kalender", len(config.calendars))
        return jsonify({"ok": True, "settings": editable_settings(config)})

    @app.post("/api/settings/test")
    def api_settings_test():
        """Eine Kalenderadresse ausprobieren, bevor sie gespeichert wird."""
        payload = request.get_json(silent=True) or {}
        url = str(payload.get("url") or "").strip()
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://") :]
        if not url.startswith(("http://", "https://")):
            return jsonify({"ok": False, "error": "Adresse muss mit https:// beginnen."}), 400

        probe = {
            "id": "probe",
            "name": "Test",
            "url": url,
            "source_url": url,
            "remote": True,
            "color": "#888888",
            "exclude": [],
        }
        fetcher = SourceFetcher(
            Path(store.fetcher.cache_dir) / "probe",
            timeout=int(ctx.config.refresh["timeout_seconds"]),
        )
        result = fetcher.fetch(probe)
        if result.text is None:
            return jsonify({"ok": False, "error": result.error or "Kein Ergebnis"})

        try:
            calendar = parse_calendar(result.text)
            now = datetime.now(ctx.config.tz)
            start = datetime.combine(now.date(), time.min, tzinfo=ctx.config.tz)
            found = expand(calendar, probe, start, start + timedelta(days=30), ctx.config.tz)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Inhalt nicht lesbar: {exc}"})

        name = str(calendar.get("X-WR-CALNAME") or "").strip()
        return jsonify({"ok": True, "count": len(found), "name": name})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kalenderanzeige fuer Raspberry Pi")
    default_config = Path(__file__).resolve().parent.parent / "config.yaml"
    parser.add_argument("--config", default=str(default_config), help="Pfad zur config.yaml")
    parser.add_argument("--cache-dir", default=None, help="Verzeichnis fuer den Offline-Cache")
    parser.add_argument("--host", default=None, help="Ueberschreibt server.host")
    parser.add_argument("--port", type=int, default=None, help="Ueberschreibt server.port")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    if not config.calendars:
        log.warning("Keine Kalender konfiguriert - die Anzeige bleibt leer.")

    cache_dir = Path(args.cache_dir) if args.cache_dir else config.path.parent / "cache"
    store = CalendarStore(config, cache_dir)
    store.start()

    button = ButtonWatcher(config.button)
    button.start()
    if button.enabled and not button.available:
        log.info("Taster nicht verfuegbar (%s) - der Alarm laesst sich weiterhin "
                 "mit jeder Taste beenden.", button.error)

    buzzer = Buzzer(config.alarm)
    buzzer.start()
    if config.alarm["output"] == "buzzer" and not buzzer.available:
        log.warning(
            "Summer nicht verfuegbar (%s) - es klingelt nichts. In den "
            "Einstellungen laesst sich auf Lautsprecher umstellen.",
            buzzer.error,
        )

    ctx = AppContext(config, store, button, buzzer)
    ctx.alarms = AlarmRunner(ctx, buzzer)
    button.add_listener(ctx.alarms.on_button)
    ctx.alarms.start()

    def shutdown(signum, frame):  # noqa: ARG001
        store.stop()
        if ctx.alarms is not None:
            ctx.alarms.shutdown()
        buzzer.close()
        button.stop()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown)
        except (ValueError, AttributeError):
            pass

    app = create_app(ctx)
    host = args.host or config.server["host"]
    port = args.port or int(config.server["port"])
    log.info("Kalender laeuft auf http://%s:%s (Zeitzone %s)", host, port, config.tz)
    app.run(host=host, port=port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

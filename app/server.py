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

from flask import Flask, jsonify, make_response, redirect, request, send_from_directory

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
from .setup_mode import SetupMode
from .store import CalendarStore
from .updater import UpdateError, Updater

# Anfragen vom Geraet selbst gelten immer als berechtigt.
LOCAL_ADDRESSES = {"127.0.0.1", "::1", "localhost"}
SETUP_COOKIE = "kalender_setup"

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
        # Das Repository liegt eine Ebene ueber dem Paket.
        self.updater = Updater(Path(__file__).resolve().parent.parent)
        self.setup = SetupMode(
            minutes=float(config.server.get("setup_minutes", 15)),
            port=int(config.server["port"]),
            host=str(config.server.get("host", "0.0.0.0")),
        )

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

    def vom_geraet() -> bool:
        return (request.remote_addr or "") in LOCAL_ADDRESSES

    def berechtigt() -> bool:
        """Aus dem Netz nur waehrend der Einrichtung und mit gueltiger Kennung."""
        if not ctx.setup.active:
            return False
        mitgebracht = request.cookies.get(SETUP_COOKIE) or request.args.get("t", "")
        return ctx.setup.token_ok(mitgebracht)

    @app.before_request
    def zugang_pruefen():
        # Das Geraet selbst und der Einstiegspunkt bleiben immer erreichbar.
        if vom_geraet() or request.path == "/setup" or berechtigt():
            return None
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Kalender</title>"
            "<body style='font-family:system-ui;padding:2rem;line-height:1.5'>"
            "<h1>Kalender</h1>"
            "<p>Die Einstellungen sind nur waehrend der Einrichtung erreichbar.</p>"
            "<p>Halte am Geraet die beiden rechten Taster zehn Sekunden lang "
            "gedrueckt und oeffne dann den angezeigten QR-Code.</p></body>",
            403,
        )

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
                        state.calendar, source, start, end, config.tz,
                        config.highlights, config.reminder_marks,
                        int(config.view["day_start_hour"]),
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

    @app.get("/api/event")
    def api_event():
        """Alles, was ueber einen Termin bekannt ist - fuer die Fehlersuche.

        Wird erst beim Anklicken geholt, damit die Wochenansicht nicht bei
        jedem Abruf die Rohdaten aller Termine mitschleppt.
        """
        kennung = request.args.get("id", "")
        # Die Kennung endet auf "@JJJJ-MM-TT" fuer den Tagesabschnitt; die UID
        # davor darf selbst ein @ enthalten.
        gesucht = kennung.rsplit("@", 1)[0] if "@" in kennung else kennung
        if not gesucht:
            return jsonify({"ok": False, "error": "keine Kennung angegeben"}), 400

        config = ctx.config
        sources = {source["id"]: source for source in config.calendars}
        now = datetime.now(config.tz)
        start = datetime.combine(now.date(), time.min, tzinfo=config.tz) - timedelta(days=380)
        ende = start + timedelta(days=760)

        for state in store.snapshot().sources:
            quelle = sources.get(state.id)
            if state.calendar is None or quelle is None:
                continue
            if not gesucht.startswith(quelle["id"] + ":"):
                continue
            for termin in expand(
                state.calendar, quelle, start, ende, config.tz,
                config.highlights, config.reminder_marks,
                int(config.view["day_start_hour"]), with_raw=True,
            ):
                if termin["id"] != gesucht:
                    continue
                return jsonify({
                    "ok": True,
                    "id": termin["id"],
                    "title": termin["title"],
                    "location": termin["location"],
                    "calendar": termin["calendar"],
                    "color": termin["color"],
                    "source_color": termin["source_color"],
                    "highlight": termin["highlight"],
                    "icon": termin["icon"],
                    "reminder_mark": termin["reminder_mark"],
                    "all_day": termin["all_day"],
                    "start": termin["start"].isoformat(),
                    "end": termin["end"].isoformat(),
                    "alarms": [a.isoformat() for a in termin["alarms"]],
                    "raw": termin["raw"],
                })
        return jsonify({"ok": False, "error": "Termin nicht gefunden"}), 404

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

    # -- Einrichtung per Handy -------------------------------------------
    def setup_seite(meldung: str = "") -> str:
        """Kleine, in sich geschlossene Seite - sie braucht keine Zusatzdateien,
        weil die ohne gueltige Kennung gar nicht ausgeliefert wuerden."""
        hinweis = (
            f"<p style='color:#b3341c'>{meldung}</p>" if meldung else ""
        )
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Kalender einrichten</title>"
            "<body style='font-family:system-ui;max-width:24rem;margin:0 auto;"
            "padding:2rem 1.2rem;line-height:1.5'>"
            "<h1 style='font-size:1.4rem'>Kalender einrichten</h1>"
            f"{hinweis}"
            "<p>Gib die sechsstellige Zahl ein, die auf dem Kalender steht.</p>"
            "<form method='get' action='/setup'>"
            "<input name='code' inputmode='numeric' autocomplete='off' "
            "style='font-size:1.6rem;width:100%;padding:0.6rem;text-align:center;"
            "letter-spacing:0.3em;border:1px solid #999;border-radius:0.4rem'>"
            "<button style='margin-top:1rem;width:100%;padding:0.8rem;"
            "font-size:1.1rem;border:0;border-radius:0.4rem;background:#1f6fd0;"
            "color:#fff'>Weiter</button></form></body>"
        )

    @app.get("/setup")
    def setup_einstieg():
        """Ziel des QR-Codes. Bei gueltiger Kennung geht es zur Anzeige."""
        if not ctx.setup.active:
            return setup_seite("Die Einrichtung ist gerade nicht geöffnet."), 403

        token = request.args.get("t", "")
        code = request.args.get("code", "")
        if not (ctx.setup.token_ok(token) or ctx.setup.code_ok(code)):
            meldung = "Die Zahl stimmt nicht." if code else ""
            return setup_seite(meldung), 403 if code else 200

        antwort = make_response(redirect("/?setup=1"))
        antwort.set_cookie(
            SETUP_COOKIE, ctx.setup.token(),
            max_age=ctx.setup.remaining(), httponly=True, samesite="Lax",
        )
        return antwort

    @app.get("/api/setup")
    def api_setup_status():
        return jsonify(ctx.setup.info())

    @app.post("/api/setup")
    def api_setup_start():
        if not vom_geraet():
            return jsonify({"ok": False, "error": "nur am Gerät möglich"}), 403
        erreichbar, grund = ctx.setup.reachable()
        if not erreichbar:
            return jsonify({"ok": False, "error": grund}), 400
        return jsonify({"ok": True, **ctx.setup.start()})

    @app.delete("/api/setup")
    def api_setup_stop():
        ctx.setup.stop()
        return jsonify({"ok": True})

    # -- Programmstand ---------------------------------------------------
    @app.get("/api/update")
    def api_update_check():
        """Nur nachsehen, ob es etwas Neues gibt."""
        try:
            return jsonify({"ok": True, **ctx.updater.check()})
        except UpdateError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/update")
    def api_update_run():
        """Neuen Stand holen, pruefen und bei Erfolg neu starten."""
        try:
            return jsonify({"ok": True, **ctx.updater.run()})
        except UpdateError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            log.exception("Aktualisierung fehlgeschlagen")
            return jsonify({"ok": False, "error": str(exc)}), 500

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

    host = args.host or config.server["host"]
    port = args.port or int(config.server["port"])

    ctx = AppContext(config, store, button, buzzer)
    # Der Einrichtungsmodus muss wissen, worauf tatsaechlich gelauscht wird -
    # die Befehlszeile kann die Konfiguration ueberschreiben.
    ctx.setup.host = host
    ctx.setup.port = port
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
    log.info("Kalender laeuft auf http://%s:%s (Zeitzone %s)", host, port, config.tz)
    app.run(host=host, port=port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

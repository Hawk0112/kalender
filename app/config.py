"""Laden und Validieren der Konfiguration."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DEFAULTS: dict[str, Any] = {
    "timezone": "Europe/Vienna",
    "locale": "de-AT",
    "server": {"host": "127.0.0.1", "port": 8080},
    "refresh": {
        "interval_minutes": 15,
        "retry_minutes": 2,
        "timeout_seconds": 20,
        "stale_after_minutes": 90,
    },
    "view": {
        "days": 7,
        # dark = heller Text auf dunklem Grund, light = umgekehrt
        "theme": "dark",
        "day_start_hour": 6,
        "day_end_hour": 22,
        "layout": "timegrid",
        "show_clock": True,
        "show_weeknumber": True,
        "hour_step": 1,
        # Nach so vielen Minuten ohne Tastendruck zurueck auf die aktuelle
        # Woche. 0 laesst die Ansicht stehen.
        "return_to_today_minutes": 5,
        "dim": {
            "enabled": True,
            "start_hour": 22,
            "end_hour": 6,
            "brightness": 0.55,
        },
    },
    "alarm": {
        "enabled": True,
        # buzzer  = Piezo-Summer am GPIO, klingelt auch bei dunklem Bildschirm
        # speaker = Ton aus dem Browser ueber HDMI, USB o. ae.
        "output": "buzzer",
        "buzzer_gpio": 18,
        "sound": "beep",
        "volume": 0.8,
        # auto = nach 'duration_seconds' Schluss, key = bis zur Tasteneingabe
        "stop_mode": "auto",
        "duration_seconds": 10,
        # Termine ohne eigene Erinnerung bleiben still. Auf true gesetzt,
        # melden sie sich zum Terminbeginn.
        "at_event_start": False,
    },
    # Taster am GPIO. Die Nummern sind BCM-Nummern, nicht die der Stiftleiste:
    # 17 = Pin 11, 27 = Pin 13, 22 = Pin 15. 0 bedeutet "nicht angeschlossen".
    "button": {
        "enabled": True,
        # Kurz: Alarm aus bzw. zurueck auf heute. Lang: Neustart.
        "gpio": 17,
        "gpio_forward": 27,
        "gpio_back": 22,
        # Taster gegen GND, interner Pull-up - kein Widerstand noetig.
        "pull_up": True,
        "bounce_time": 0.05,
        # So lange gedrueckt halten, um das System neu zu starten. 0 schaltet
        # das ab.
        "reboot_hold_seconds": 20,
        # Taster 2 und 3 gemeinsam so lange halten, um die Einstellungen zu
        # oeffnen. 0 schaltet das ab.
        "combo_hold_seconds": 2.0,
    },
    "calendars": [],
    # Termine, die auffallen sollen - unabhaengig davon, aus welchem Kalender
    # sie stammen. Greift ueber Stichwoerter im Titel oder ueber den Kalendernamen.
    "highlights": [
        {
            "name": "Geburtstage",
            "match": ["geburtstag", "birthday", "bday", "\U0001f382"],
            "color": "#ff4fa3",
            "icon": "\U0001f382",
        }
    ],
}

# Auswaehlbare Alarmtoene. Erzeugt werden sie im Browser, es gibt also
# keine Audiodateien, die fehlen oder nicht abspielbar sein koennen.
SOUNDS = [
    {"id": "beep", "name": "Doppelpiep"},
    {"id": "alarm", "name": "Wecker"},
    {"id": "chime", "name": "Glockenspiel"},
    {"id": "gong", "name": "Gong"},
    {"id": "soft", "name": "Sanfter Ton"},
]
SOUND_IDS = {sound["id"] for sound in SOUNDS}

# Wo der Alarmton herauskommt.
OUTPUTS = [
    {"id": "buzzer", "name": "Summer am GPIO"},
    {"id": "speaker", "name": "Lautsprecher (HDMI/USB)"},
]
OUTPUT_IDS = {output["id"] for output in OUTPUTS}

# Farbschema der Anzeige.
THEMES = [
    {"id": "dark", "name": "Dunkel"},
    {"id": "light", "name": "Hell"},
]
THEME_IDS = {theme["id"] for theme in THEMES}

# Sicherheitsnetz fuer den Modus "bis zur Tasteneingabe": Wenn niemand da ist,
# soll der Ton nicht endlos laufen.
ALARM_HARD_LIMIT_SECONDS = 300

PALETTE = [
    "#4f9cf9",
    "#f2b53c",
    "#5ec269",
    "#e0688a",
    "#9b7bea",
    "#3fbfb0",
    "#e8804a",
]


class ConfigError(Exception):
    pass


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = copy.deepcopy(base)
        for key, value in override.items():
            merged[key] = _merge(merged.get(key), value) if key in merged else value
        return merged
    return override


class Config:
    def __init__(self, data: dict[str, Any], path: Path):
        self.path = path
        self.data = data
        try:
            self.tz = ZoneInfo(str(data["timezone"]))
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ConfigError(f"Unbekannte Zeitzone: {data.get('timezone')!r}") from exc

    # -- Abkuerzungen ----------------------------------------------------
    @property
    def locale(self) -> str:
        return str(self.data["locale"])

    @property
    def view(self) -> dict[str, Any]:
        return self.data["view"]

    @property
    def refresh(self) -> dict[str, Any]:
        return self.data["refresh"]

    @property
    def server(self) -> dict[str, Any]:
        return self.data["server"]

    @property
    def calendars(self) -> list[dict[str, Any]]:
        return self.data["calendars"]

    @property
    def highlights(self) -> list[dict[str, Any]]:
        return self.data["highlights"]

    @property
    def alarm(self) -> dict[str, Any]:
        return self.data["alarm"]

    @property
    def button(self) -> dict[str, Any]:
        return self.data["button"]

    @property
    def days(self) -> int:
        return int(self.view["days"])


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise ConfigError(
            f"Konfiguration nicht gefunden: {path}\n"
            "Kopiere config.example.yaml nach config.yaml."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} enthaelt kein YAML-Objekt.")

    data = _merge(DEFAULTS, raw)
    data["calendars"] = _normalise_calendars(data.get("calendars"), path.parent)
    data["highlights"] = _normalise_highlights(data.get("highlights"))

    view = data["view"]
    view["days"] = max(1, min(14, int(view["days"])))
    view["day_start_hour"] = max(0, min(23, int(view["day_start_hour"])))
    view["day_end_hour"] = max(view["day_start_hour"] + 1, min(24, int(view["day_end_hour"])))
    if view["layout"] not in ("timegrid", "agenda"):
        raise ConfigError("view.layout muss 'timegrid' oder 'agenda' sein.")
    if view["theme"] not in THEME_IDS:
        raise ConfigError(f"view.theme muss {' oder '.join(sorted(THEME_IDS))} sein.")
    try:
        back = float(view["return_to_today_minutes"])
    except (TypeError, ValueError):
        raise ConfigError("view.return_to_today_minutes muss eine Zahl sein.") from None
    view["return_to_today_minutes"] = max(0.0, min(240.0, back))

    alarm = data["alarm"]
    if alarm["sound"] not in SOUND_IDS:
        raise ConfigError(
            f"alarm.sound muss einer von {', '.join(sorted(SOUND_IDS))} sein."
        )
    if alarm["stop_mode"] not in ("auto", "key"):
        raise ConfigError("alarm.stop_mode muss 'auto' oder 'key' sein.")
    if alarm["output"] not in OUTPUT_IDS:
        raise ConfigError(
            f"alarm.output muss einer von {', '.join(sorted(OUTPUTS))} sein."
        )
    try:
        buzzer_pin = int(alarm["buzzer_gpio"])
    except (TypeError, ValueError):
        raise ConfigError("alarm.buzzer_gpio muss eine Zahl sein.") from None
    if buzzer_pin and not 2 <= buzzer_pin <= 27:
        raise ConfigError(
            "alarm.buzzer_gpio muss 0 (nicht angeschlossen) oder eine "
            "BCM-Nummer zwischen 2 und 27 sein."
        )
    alarm["buzzer_gpio"] = buzzer_pin
    alarm["duration_seconds"] = max(1, min(120, int(alarm["duration_seconds"])))
    alarm["volume"] = max(0.0, min(1.0, float(alarm["volume"])))
    alarm["hard_limit_seconds"] = ALARM_HARD_LIMIT_SECONDS

    button = data["button"]
    pin_keys = ("gpio", "gpio_forward", "gpio_back")
    try:
        pins = {key: int(button[key]) for key in pin_keys}
        bounce = float(button["bounce_time"])
        hold = float(button["reboot_hold_seconds"])
        combo = float(button["combo_hold_seconds"])
    except (TypeError, ValueError):
        raise ConfigError(
            "button: Pin-Nummern, bounce_time und reboot_hold_seconds muessen "
            "Zahlen sein."
        ) from None

    for key, pin in pins.items():
        if pin and not 2 <= pin <= 27:
            raise ConfigError(
                f"button.{key} muss 0 (nicht angeschlossen) oder eine "
                "BCM-Nummer zwischen 2 und 27 sein."
            )
    belegt = [pin for pin in pins.values() if pin]
    if len(belegt) != len(set(belegt)):
        raise ConfigError("Jeder Taster braucht einen eigenen Pin.")
    if alarm["buzzer_gpio"] and alarm["buzzer_gpio"] in belegt:
        raise ConfigError(
            f"GPIO{alarm['buzzer_gpio']} ist doppelt vergeben: Summer und Taster."
        )
    if hold and not 3 <= hold <= 120:
        raise ConfigError(
            "button.reboot_hold_seconds muss 0 (aus) oder zwischen 3 und 120 sein."
        )
    if combo and not 0.5 <= combo <= 10:
        raise ConfigError(
            "button.combo_hold_seconds muss 0 (aus) oder zwischen 0.5 und 10 sein."
        )

    button.update(pins)
    button["bounce_time"] = max(0.005, min(1.0, bounce))
    button["reboot_hold_seconds"] = hold
    button["combo_hold_seconds"] = combo

    return Config(data, path)


def _normalise_calendars(entries: Any, base_dir: Path) -> list[dict[str, Any]]:
    if not entries:
        return []
    if not isinstance(entries, list):
        raise ConfigError("'calendars' muss eine Liste sein.")

    result: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("url"):
            raise ConfigError(f"calendars[{index}]: 'url' fehlt.")
        url = str(entry["url"]).strip()
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://") :]
        is_remote = url.startswith(("http://", "https://"))
        if not is_remote:
            url = str((base_dir / url).resolve())

        exclude = entry.get("exclude") or []
        if isinstance(exclude, str):
            exclude = [exclude]

        result.append(
            {
                "id": f"cal{index}",
                "name": str(entry.get("name") or f"Kalender {index + 1}"),
                "url": url,
                # unveraenderte Schreibweise aus der Datei - fuer die Einstellungsseite
                "source_url": str(entry["url"]).strip(),
                "remote": is_remote,
                "color": str(entry.get("color") or PALETTE[index % len(PALETTE)]),
                "exclude": [str(x).lower() for x in exclude],
            }
        )
    return result


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _normalise_highlights(entries: Any) -> list[dict[str, Any]]:
    if not entries:
        return []
    if not isinstance(entries, list):
        raise ConfigError("'highlights' muss eine Liste sein.")

    result: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ConfigError(f"highlights[{index}]: erwartet ein Objekt.")
        terms = [t.lower() for t in _as_list(entry.get("match")) if t]
        calendars = [c.lower() for c in _as_list(entry.get("calendars")) if c]
        if not terms and not calendars:
            raise ConfigError(
                f"highlights[{index}]: 'match' oder 'calendars' muss gesetzt sein."
            )
        result.append(
            {
                "name": str(entry.get("name") or f"Hervorhebung {index + 1}"),
                "match": terms,
                "calendars": calendars,
                "color": str(entry["color"]) if entry.get("color") else None,
                "icon": str(entry.get("icon") or ""),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Einstellungsseite: lesen, pruefen, zurueckschreiben
# ---------------------------------------------------------------------------

HEADER = """# Kalender - Konfiguration
#
# Diese Datei wird auch von der Einstellungsseite (Zahnrad oben rechts)
# geschrieben. Beim Speichern ueber die Oberflaeche gehen eigene Kommentare
# verloren; die vorherige Fassung liegt als config.yaml.bak daneben.
"""

COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def editable_settings(config: Config) -> dict[str, Any]:
    """Die von der Oberflaeche bearbeitbaren Werte."""
    return {
        "timezone": str(config.data["timezone"]),
        "locale": config.locale,
        "refresh": {
            "interval_minutes": int(config.refresh["interval_minutes"]),
            "timeout_seconds": int(config.refresh["timeout_seconds"]),
        },
        "view": {
            "days": int(config.view["days"]),
            "theme": config.view["theme"],
            "layout": config.view["layout"],
            "day_start_hour": int(config.view["day_start_hour"]),
            "day_end_hour": int(config.view["day_end_hour"]),
            "hour_step": int(config.view["hour_step"]),
            "show_clock": bool(config.view["show_clock"]),
            "show_weeknumber": bool(config.view["show_weeknumber"]),
            "return_to_today_minutes": float(config.view["return_to_today_minutes"]),
            "dim": {
                "enabled": bool(config.view["dim"]["enabled"]),
                "start_hour": int(config.view["dim"]["start_hour"]),
                "end_hour": int(config.view["dim"]["end_hour"]),
                "brightness": float(config.view["dim"]["brightness"]),
            },
        },
        "alarm": {
            "enabled": bool(config.alarm["enabled"]),
            "output": config.alarm["output"],
            "sound": config.alarm["sound"],
            "volume": float(config.alarm["volume"]),
            "stop_mode": config.alarm["stop_mode"],
            "duration_seconds": int(config.alarm["duration_seconds"]),
            "at_event_start": bool(config.alarm["at_event_start"]),
        },
        "sounds": SOUNDS,
        "outputs": OUTPUTS,
        "themes": THEMES,
        "alarm_hard_limit_seconds": ALARM_HARD_LIMIT_SECONDS,
        "calendars": [
            {
                "name": cal["name"],
                "url": cal["source_url"],
                "color": cal["color"],
                "exclude": cal["exclude"],
                "editable": cal["remote"],
            }
            for cal in config.calendars
        ],
        "highlights": [
            {
                "name": rule["name"],
                "match": rule["match"],
                "calendars": rule["calendars"],
                "color": rule["color"] or PALETTE[0],
                "icon": rule["icon"],
            }
            for rule in config.highlights
        ],
        "palette": PALETTE,
    }


def _clamp_int(value: Any, low: int, high: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{label}: Zahl erwartet.") from None
    if not low <= number <= high:
        raise ConfigError(f"{label}: Wert muss zwischen {low} und {high} liegen.")
    return number


def _check_color(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not COLOR_PATTERN.match(text):
        raise ConfigError(f"{label}: Farbe muss im Format #rrggbb angegeben werden.")
    return text.lower()


def settings_to_raw(payload: Any, previous: Config) -> dict[str, Any]:
    """Eingaben der Oberflaeche pruefen und in eine speicherbare Struktur bringen."""
    if not isinstance(payload, dict):
        raise ConfigError("Ungueltige Daten empfangen.")

    timezone = str(payload.get("timezone") or "").strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"Unbekannte Zeitzone: {timezone or '(leer)'}") from None

    locale = str(payload.get("locale") or "").strip()
    if not re.match(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$", locale):
        raise ConfigError("Sprache muss z. B. 'de-AT' lauten.")

    view_in = payload.get("view") or {}
    dim_in = view_in.get("dim") or {}
    start_hour = _clamp_int(view_in.get("day_start_hour"), 0, 23, "Anzeige von")
    end_hour = _clamp_int(view_in.get("day_end_hour"), 1, 24, "Anzeige bis")
    if end_hour <= start_hour:
        raise ConfigError("Anzeige bis muss nach Anzeige von liegen.")
    layout = str(view_in.get("layout") or "timegrid")
    if layout not in ("timegrid", "agenda"):
        raise ConfigError("Unbekannte Darstellung.")
    theme = str(view_in.get("theme") or "dark")
    if theme not in THEME_IDS:
        raise ConfigError("Unbekanntes Farbschema.")

    try:
        brightness = float(dim_in.get("brightness", 0.55))
    except (TypeError, ValueError):
        raise ConfigError("Nachtabsenkung: Zahl erwartet.") from None
    if not 0.1 <= brightness <= 1.0:
        raise ConfigError("Nachtabsenkung muss zwischen 0.1 und 1.0 liegen.")

    alarm_in = payload.get("alarm") or {}
    sound = str(alarm_in.get("sound") or "beep")
    if sound not in SOUND_IDS:
        raise ConfigError("Unbekannter Alarmton.")
    stop_mode = str(alarm_in.get("stop_mode") or "auto")
    if stop_mode not in ("auto", "key"):
        raise ConfigError("Unbekannte Einstellung für das Ende des Alarms.")
    try:
        volume = float(alarm_in.get("volume", 0.8))
    except (TypeError, ValueError):
        raise ConfigError("Lautstärke: Zahl erwartet.") from None
    if not 0.0 <= volume <= 1.0:
        raise ConfigError("Lautstärke muss zwischen 0 und 1 liegen.")

    output = str(alarm_in.get("output") or "buzzer")
    if output not in OUTPUT_IDS:
        raise ConfigError("Unbekannte Tonausgabe.")

    alarm = {
        "enabled": bool(alarm_in.get("enabled", True)),
        "output": output,
        # Der Pin ist Verdrahtung - unveraendert aus der Datei uebernehmen.
        "buzzer_gpio": int(previous.alarm["buzzer_gpio"]),
        "sound": sound,
        "volume": round(volume, 2),
        "stop_mode": stop_mode,
        "duration_seconds": _clamp_int(
            alarm_in.get("duration_seconds", 10), 1, 120, "Dauer des Alarms"
        ),
        "at_event_start": bool(alarm_in.get("at_event_start", False)),
    }

    calendars = []
    seen_urls = set()
    for index, entry in enumerate(payload.get("calendars") or [], start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Kalender {index}: ungueltiger Eintrag.")
        name = str(entry.get("name") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not name:
            raise ConfigError(f"Kalender {index}: Name fehlt.")
        if not url:
            raise ConfigError(f"Kalender „{name}“: Adresse fehlt.")
        if not url.startswith(("http://", "https://", "webcal://")):
            raise ConfigError(
                f"Kalender „{name}“: Adresse muss mit https:// oder webcal:// beginnen."
            )
        if url in seen_urls:
            raise ConfigError(f"Kalender „{name}“: Adresse ist doppelt eingetragen.")
        seen_urls.add(url)

        exclude = [t.strip() for t in _as_list(entry.get("exclude")) if t.strip()]
        calendar = {
            "name": name,
            "url": url,
            "color": _check_color(entry.get("color"), f"Kalender „{name}“"),
        }
        if exclude:
            calendar["exclude"] = exclude
        calendars.append(calendar)

    highlights = []
    for index, entry in enumerate(payload.get("highlights") or [], start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Hervorhebung {index}: ungueltiger Eintrag.")
        name = str(entry.get("name") or "").strip() or f"Hervorhebung {index}"
        terms = [t.strip() for t in _as_list(entry.get("match")) if t.strip()]
        cals = [t.strip() for t in _as_list(entry.get("calendars")) if t.strip()]
        if not terms and not cals:
            raise ConfigError(
                f"Hervorhebung „{name}“: mindestens ein Stichwort oder ein Kalender noetig."
            )
        rule = {"name": name, "color": _check_color(entry.get("color"), f"Hervorhebung „{name}“")}
        if terms:
            rule["match"] = terms
        if cals:
            rule["calendars"] = cals
        if str(entry.get("icon") or "").strip():
            rule["icon"] = str(entry["icon"]).strip()[:4]
        highlights.append(rule)

    refresh_in = payload.get("refresh") or {}
    previous_refresh = previous.refresh

    # Lokale Dateien (z. B. der Demokalender) bleiben erhalten, sind aber ueber
    # die Oberflaeche nicht editierbar - sonst koennte man beliebige Dateien lesen.
    for cal in previous.calendars:
        if not cal["remote"]:
            entry = {"name": cal["name"], "url": cal["source_url"], "color": cal["color"]}
            if cal["exclude"]:
                entry["exclude"] = cal["exclude"]
            calendars.append(entry)

    return {
        "timezone": timezone,
        "locale": locale,
        "server": dict(previous.server),
        "refresh": {
            "interval_minutes": _clamp_int(
                refresh_in.get("interval_minutes"), 1, 1440, "Aktualisierung"
            ),
            "retry_minutes": int(previous_refresh["retry_minutes"]),
            "timeout_seconds": _clamp_int(
                refresh_in.get("timeout_seconds"), 5, 120, "Zeitlimit"
            ),
            "stale_after_minutes": int(previous_refresh["stale_after_minutes"]),
        },
        "view": {
            "days": _clamp_int(view_in.get("days"), 1, 14, "Anzahl Tage"),
            "theme": theme,
            "day_start_hour": start_hour,
            "day_end_hour": end_hour,
            "layout": layout,
            "show_clock": bool(view_in.get("show_clock", True)),
            "show_weeknumber": bool(view_in.get("show_weeknumber", True)),
            "hour_step": _clamp_int(view_in.get("hour_step", 1), 1, 6, "Stundenlinien"),
            "return_to_today_minutes": _clamp_int(
                view_in.get("return_to_today_minutes", 5), 0, 240, "Zurück auf heute"
            ),
            "dim": {
                "enabled": bool(dim_in.get("enabled", True)),
                "start_hour": _clamp_int(dim_in.get("start_hour"), 0, 23, "Absenkung ab"),
                "end_hour": _clamp_int(dim_in.get("end_hour"), 0, 23, "Absenkung bis"),
                "brightness": round(brightness, 2),
            },
        },
        "alarm": alarm,
        # Der Taster wird nur in der Datei eingestellt - unveraendert uebernehmen,
        # damit das Speichern ueber die Oberflaeche ihn nicht entfernt.
        "button": dict(previous.button),
        "highlights": highlights,
        "calendars": calendars,
    }


def save_config(path: Path, raw: dict[str, Any]) -> None:
    """Konfiguration atomar schreiben und die vorherige Fassung sichern."""
    path = Path(path)
    body = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(HEADER + "\n" + body, encoding="utf-8")
    if path.exists():
        try:
            path.replace(path.with_suffix(".yaml.bak"))
        except OSError:
            pass
    tmp.replace(path)

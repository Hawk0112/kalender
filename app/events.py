"""Parsen der ICS-Daten und Aufbereitung fuer die Wochenansicht."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Iterable

import recurring_ical_events
from icalendar import Calendar

log = logging.getLogger(__name__)


def parse_calendar(text: str) -> Calendar:
    return Calendar.from_ical(text)


def _as_datetime(value: Any, tz: tzinfo) -> tuple[datetime, bool]:
    """Liefert (aware datetime, ist_ganztaegig)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz), False
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tz), True
    raise TypeError(f"Unerwarteter Zeitwert: {value!r}")


def _component_bounds(component: Any, tz: tzinfo) -> tuple[datetime, datetime, bool] | None:
    dtstart = component.get("DTSTART")
    if dtstart is None:
        return None
    start, all_day = _as_datetime(dtstart.dt, tz)

    dtend = component.get("DTEND")
    if dtend is not None:
        end, _ = _as_datetime(dtend.dt, tz)
    else:
        duration = component.get("DURATION")
        if duration is not None:
            end = start + duration.dt
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))

    if end <= start:
        end = start + (timedelta(days=1) if all_day else timedelta(minutes=30))
    return start, end, all_day


def _text(component: Any, key: str) -> str:
    value = component.get(key)
    if value is None:
        return ""
    return str(value).strip()


def alarm_times(component: Any, start: datetime, end: datetime, tz: tzinfo) -> list[datetime]:
    """Zeitpunkte der Erinnerungen (VALARM) eines Termins bestimmen."""
    moments: list[datetime] = []
    for sub in getattr(component, "subcomponents", []):
        if getattr(sub, "name", "") != "VALARM":
            continue
        if str(sub.get("ACTION", "")).upper() == "EMAIL":
            continue
        trigger = sub.get("TRIGGER")
        if trigger is None:
            continue
        value = trigger.dt
        if isinstance(value, timedelta):
            # Relativ zum Beginn, mit RELATED=END relativ zum Ende.
            related = str(trigger.params.get("RELATED", "START")).upper()
            moments.append((end if related == "END" else start) + value)
        elif isinstance(value, (datetime, date)):
            moments.append(_as_datetime(value, tz)[0])
    return moments


# Farbe eines einzelnen Termins (COLOR, RFC 7986). Erlaubt sind ein Hex-Wert
# oder ein CSS-Farbname wie "tomato". Alles andere wird verworfen - die Daten
# stammen von fremden Servern und landen direkt im Stylesheet.
COLOR_VALUE = re.compile(r"^(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|[a-zA-Z]{3,24})$")


def event_color(component: Any) -> str:
    value = str(component.get("COLOR") or "").strip()
    return value.lower() if COLOR_VALUE.match(value) else ""


def match_highlight(title: str, source: dict, highlights: list[dict]) -> dict | None:
    """Erste passende Hervorhebungsregel finden (Titel-Stichwort oder Kalendername)."""
    haystack = title.lower()
    calendar_name = source["name"].lower()
    for rule in highlights:
        if calendar_name in rule["calendars"]:
            return rule
        if any(term in haystack for term in rule["match"]):
            return rule
    return None


def expand(
    calendar: Calendar,
    source: dict,
    window_start: datetime,
    window_end: datetime,
    tz: tzinfo,
    highlights: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Termine einer Quelle im Fenster expandieren (inkl. Serienterminen)."""
    try:
        components = recurring_ical_events.of(calendar).between(window_start, window_end)
    except Exception as exc:
        log.warning("Serientermine von %s nicht auswertbar: %s", source["name"], exc)
        components = []

    events: list[dict[str, Any]] = []
    for component in components:
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue

        bounds = _component_bounds(component, tz)
        if bounds is None:
            continue
        start, end, all_day = bounds

        title = _text(component, "SUMMARY") or "(ohne Titel)"
        haystack = title.lower()
        if any(term in haystack for term in source["exclude"]):
            continue

        rule = match_highlight(title, source, highlights or [])
        # Reihenfolge: eigene Hervorhebungsregel, dann die Farbe des Termins
        # aus dem Kalender, zuletzt die eingestellte Farbe der Quelle.
        if rule and rule["color"]:
            colour = rule["color"]
        else:
            colour = event_color(component) or source["color"]

        uid = _text(component, "UID") or title
        events.append(
            {
                "id": f"{source['id']}:{uid}:{start.isoformat()}",
                "title": title,
                "location": _text(component, "LOCATION"),
                "calendar": source["name"],
                "color": colour,
                "icon": rule["icon"] if rule else "",
                "highlight": rule["name"] if rule else None,
                "all_day": all_day,
                "start": start,
                "end": end,
                "alarms": alarm_times(component, start, end, tz),
            }
        )
    return events


def collect_alarms(
    events: Iterable[dict[str, Any]],
    now: datetime,
    horizon: datetime,
    at_event_start: bool,
    grace_seconds: int = 90,
) -> list[dict[str, Any]]:
    """Faellige Erinnerungen fuer die Anzeige zusammenstellen.

    Gemeldet wird nur, was im Termin selbst als Erinnerung (VALARM) steht.
    Termine ohne Erinnerung bleiben still; mit 'at_event_start' melden sie
    sich zum Beginn. Ganztaegige Termine sind davon ausgenommen - sie wuerden
    um Mitternacht losgehen.
    """
    earliest = now - timedelta(seconds=grace_seconds)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    for event in events:
        moments = list(event["alarms"])
        if at_event_start and not moments and not event["all_day"]:
            moments = [event["start"]]

        for moment in moments:
            if moment < earliest or moment > horizon:
                continue
            key = f"{event['id']}@{moment.isoformat()}"
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "id": key,
                    "at": moment.isoformat(),
                    "title": event["title"],
                    "location": event["location"],
                    "calendar": event["calendar"],
                    "color": event["color"],
                    "icon": event["icon"],
                    "all_day": event["all_day"],
                    "start": event["start"].isoformat(),
                    "end": event["end"].isoformat(),
                    "lead_minutes": round((event["start"] - moment).total_seconds() / 60),
                }
            )

    result.sort(key=lambda item: item["at"])
    return result


def build_days(
    events: Iterable[dict[str, Any]],
    first_day: date,
    day_count: int,
    tz: tzinfo,
    now: datetime,
    start_hour: int = 0,
    end_hour: int = 24,
) -> list[dict[str, Any]]:
    """Termine auf Tagesspalten verteilen, mehrtaegige Termine zerschneiden.

    Termine, die vollstaendig vor 'start_hour' oder nach 'end_hour' liegen,
    kommen in eigene Sammelbereiche ober- und unterhalb des Stundenrasters.
    """
    events = list(events)
    days: list[dict[str, Any]] = []
    window_start = start_hour * 60
    window_end = end_hour * 60

    for offset in range(day_count):
        current = first_day + timedelta(days=offset)
        day_start = datetime.combine(current, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)

        all_day: list[dict[str, Any]] = []
        early: list[dict[str, Any]] = []
        timed: list[dict[str, Any]] = []
        late: list[dict[str, Any]] = []

        for event in events:
            if event["end"] <= day_start or event["start"] >= day_end:
                continue

            segment = {
                "id": f"{event['id']}@{current.isoformat()}",
                "title": event["title"],
                "location": event["location"],
                "calendar": event["calendar"],
                "color": event["color"],
                "icon": event["icon"],
                "highlight": event["highlight"],
                "all_day": event["all_day"],
                "start": max(event["start"], day_start).isoformat(),
                "end": min(event["end"], day_end).isoformat(),
                "full_start": event["start"].isoformat(),
                "full_end": event["end"].isoformat(),
                "continues_before": event["start"] < day_start,
                "continues_after": event["end"] > day_end,
                "past": event["end"] <= now,
                "running": event["start"] <= now < event["end"],
            }

            if event["all_day"] or (event["end"] - event["start"]) >= timedelta(days=1):
                all_day.append(segment)
                continue

            # Lage des Tagesabschnitts in Minuten seit Mitternacht
            segment_start = (max(event["start"], day_start) - day_start).total_seconds() / 60
            segment_end = (min(event["end"], day_end) - day_start).total_seconds() / 60
            if segment_end <= window_start:
                early.append(segment)
            elif segment_start >= window_end:
                late.append(segment)
            else:
                timed.append(segment)

        # Hervorgehobenes zuerst, damit es nie unter "+N weitere" verschwindet.
        all_day.sort(key=lambda e: (e["highlight"] is None, e["full_start"], e["title"]))
        for bucket in (early, timed, late):
            bucket.sort(key=lambda e: (e["start"], e["end"]))

        iso = current.isocalendar()
        days.append(
            {
                "date": current.isoformat(),
                "weekday": current.weekday(),
                "week": iso.week,
                "is_today": current == now.date(),
                "is_weekend": current.weekday() >= 5,
                "all_day": all_day,
                "early": early,
                "timed": timed,
                "late": late,
            }
        )
    return days

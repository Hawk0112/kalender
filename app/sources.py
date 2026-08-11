"""Abruf der ICS-Quellen inklusive Offline-Cache.

Der Raspberry haengt dauerhaft an einer Anzeige: ein Netzwerkausfall darf die
Darstellung nicht leeren. Jede erfolgreich geladene Quelle wird deshalb auf
Platte gespeichert und beim naechsten Fehlschlag wieder verwendet.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = "Kalender-Pi/1.0 (+https://localhost)"


@dataclass
class FetchResult:
    calendar_id: str
    name: str
    text: str | None
    from_cache: bool
    fetched_at: datetime | None
    error: str | None = None


class SourceFetcher:
    def __init__(self, cache_dir: Path, timeout: int = 20):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        # ETag/Last-Modified je Quelle, um unnoetigen Traffic zu vermeiden.
        self._validators: dict[str, dict[str, str]] = {}

    def _cache_file(self, calendar: dict) -> Path:
        digest = hashlib.sha256(calendar["url"].encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{calendar['id']}-{digest}.ics"

    def fetch(self, calendar: dict) -> FetchResult:
        if not calendar["remote"]:
            return self._read_local(calendar)
        return self._read_remote(calendar)

    # -- lokale Datei ----------------------------------------------------
    def _read_local(self, calendar: dict) -> FetchResult:
        path = Path(calendar["url"])
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return FetchResult(calendar["id"], calendar["name"], None, False, None, str(exc))
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return FetchResult(calendar["id"], calendar["name"], text, False, stamp)

    # -- HTTP ------------------------------------------------------------
    def _read_remote(self, calendar: dict) -> FetchResult:
        cache_file = self._cache_file(calendar)
        headers: dict[str, str] = dict(self._validators.get(calendar["id"], {}))
        if not cache_file.exists():
            headers.clear()

        try:
            response = self.session.get(
                calendar["url"], headers=headers, timeout=self.timeout, allow_redirects=True
            )
            if response.status_code == 304 and cache_file.exists():
                return self._from_cache(calendar, cache_file, error=None, unchanged=True)
            response.raise_for_status()

            text = response.text
            if "BEGIN:VCALENDAR" not in text.upper():
                raise ValueError("Antwort enthaelt keine iCalendar-Daten")

            validators = {}
            if etag := response.headers.get("ETag"):
                validators["If-None-Match"] = etag
            if modified := response.headers.get("Last-Modified"):
                validators["If-Modified-Since"] = modified
            self._validators[calendar["id"]] = validators

            tmp = cache_file.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(cache_file)

            return FetchResult(
                calendar["id"],
                calendar["name"],
                text,
                False,
                datetime.now(timezone.utc),
            )
        except Exception as exc:  # Netzwerk, HTTP, Parsing - alles gleich behandelt
            log.warning("Abruf fehlgeschlagen (%s): %s", calendar["name"], exc)
            self._validators.pop(calendar["id"], None)
            if cache_file.exists():
                return self._from_cache(calendar, cache_file, error=str(exc))
            return FetchResult(calendar["id"], calendar["name"], None, False, None, str(exc))

    def _from_cache(
        self, calendar: dict, cache_file: Path, error: str | None, unchanged: bool = False
    ) -> FetchResult:
        text = cache_file.read_text(encoding="utf-8", errors="replace")
        stamp = datetime.fromtimestamp(cache_file.stat().st_mtime, tz=timezone.utc)
        return FetchResult(
            calendar["id"],
            calendar["name"],
            text,
            from_cache=not unchanged,
            fetched_at=datetime.now(timezone.utc) if unchanged else stamp,
            error=error,
        )

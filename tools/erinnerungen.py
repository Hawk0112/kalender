"""Zeigt, welche Termine eine Erinnerung mitbringen - und was sie unterscheidet.

Hintergrund: Google uebertraegt Erinnerungen im ICS-Abo nicht immer. Dieses
Werkzeug stellt die Termine mit Erinnerung denen ohne gegenueber, damit
erkennbar wird, was die Ausnahmen gemeinsam haben.

Aufruf auf dem Pi:

    cd ~/kalender && .venv/bin/python tools/erinnerungen.py

Mit --anonym werden Titel, Beschreibungen, Orte und Adressen ersetzt. Uebrig
bleibt nur die Struktur - so laesst sich die Ausgabe weitergeben, ohne dass
jemand die Termine mitlesen kann.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.sources import SourceFetcher  # noqa: E402

# Eigenschaften, die verraten, woher ein Termin stammt.
VERRAETERISCH = [
    "ORGANIZER", "ATTENDEE", "RRULE", "RECURRENCE-ID", "CLASS", "TRANSP",
    "STATUS", "SEQUENCE", "CREATED", "LAST-MODIFIED", "DESCRIPTION",
]


def entfalte(text: str) -> str:
    """ICS bricht lange Zeilen um - das rueckgaengig machen."""
    return re.sub(r"\r?\n[ \t]", "", text)


def wert(block: str, name: str) -> str:
    treffer = re.findall(rf"^{re.escape(name)}[;:]([^\r\n]*)", block, re.M)
    if not treffer:
        return ""
    if len(treffer) > 1:
        return f"{len(treffer)}x"
    return treffer[0].lstrip(":").strip()[:40]


# Diese Angaben verraten Persoenliches und werden mit --anonym ersetzt.
PERSOENLICH = {"SUMMARY", "DESCRIPTION", "LOCATION", "ORGANIZER", "ATTENDEE", "URL"}

ANONYM = False


def maskiere(name: str, v: str) -> str:
    """Inhalt durch eine Angabe ueber den Inhalt ersetzen."""
    if not ANONYM or name not in PERSOENLICH or not v:
        return v
    if re.fullmatch(r"\d+x", v):
        return v                       # blosse Anzahl, unbedenklich
    return f"(vorhanden, {len(v)} Zeichen)"


def beschreibe(block: str) -> dict[str, str]:
    daten = {}
    for name in VERRAETERISCH:
        v = wert(block, name)
        if v:
            daten[name] = maskiere(name, v)
    for x in sorted(set(re.findall(r"^(X-[A-Z0-9-]+)[;:]", block, re.M))):
        daten[x] = maskiere(x, wert(block, x))
    # Die Herkunft steckt im Namensteil der UID, nicht im Kennungsteil davor.
    uid = wert(block, "UID")
    if uid:
        daten["UID-Herkunft"] = "@" + uid.split("@")[-1] if "@" in uid else "(ohne @)"
    return daten


def zeige(titel: str, block: str, einzug: str = "    ") -> None:
    alarm = re.search(r"BEGIN:VALARM(.*?)END:VALARM", block, re.S)
    print(f"{einzug}{titel[:52]}")
    if alarm:
        trigger = wert(alarm.group(1), "TRIGGER") or "?"
        aktion = wert(alarm.group(1), "ACTION") or "?"
        print(f"{einzug}   Erinnerung: {trigger}   Art: {aktion}")
    for name, v in beschreibe(block).items():
        print(f"{einzug}   {name:15} {v}")


def main() -> int:
    global ANONYM
    argumente = [a for a in sys.argv[1:] if a != "--anonym"]
    ANONYM = "--anonym" in sys.argv
    pfad = argumente[0] if argumente else "config.yaml"
    cfg = load_config(pfad)
    if ANONYM:
        print("Anonymisierte Ausgabe - Titel, Orte und Adressen sind ersetzt.")
    holer = SourceFetcher(Path(tempfile.mkdtemp()), timeout=25)

    for quelle in cfg.calendars:
        ergebnis = holer.fetch(quelle)
        if ergebnis.text is None:
            print(f"\n{quelle['name']}: FEHLER - {ergebnis.error}")
            continue

        text = entfalte(ergebnis.text)
        bloecke = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", text, re.S)
        mit = [b for b in bloecke if "BEGIN:VALARM" in b]
        ohne = [b for b in bloecke if "BEGIN:VALARM" not in b]

        print(f"\n{'=' * 62}")
        print(f"{quelle['name']}: {len(bloecke)} Termine, {len(mit)} mit Erinnerung")
        print("=" * 62)

        def titel_von(block: str, nummer: int) -> str:
            if ANONYM:
                return f"Termin {nummer}"
            return wert(block, "SUMMARY") or "(ohne Titel)"

        if mit:
            print("\n  MIT Erinnerung:")
            for i, block in enumerate(mit[:12], start=1):
                zeige(titel_von(block, i), block)
                print()
        else:
            print("\n  Kein einziger Termin bringt eine Erinnerung mit.")

        if ohne:
            print(f"\n  OHNE Erinnerung (zum Vergleich, {min(4, len(ohne))} Beispiele):")
            for i, block in enumerate(ohne[:4], start=1):
                zeige(titel_von(block, i), block)
                print()

    print("\nWorauf zu achten ist: Tragen die Termine mit Erinnerung ein")
    print("ORGANIZER oder ATTENDEE? Dann stammen sie aus einer Einladung.")
    print("Andere X-Eigenschaften deuten auf einen Import aus einem anderen")
    print("Programm hin. Beides erklaert, warum Google dort eine Erinnerung")
    print("mitliefert, bei selbst angelegten Terminen aber nicht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

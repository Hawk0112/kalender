"""Zeigt, welche Termine eine Erinnerung mitbringen - und was sie unterscheidet.

Hintergrund: Google uebertraegt Erinnerungen im ICS-Abo nicht immer. Dieses
Werkzeug stellt die Termine mit Erinnerung denen ohne gegenueber, damit
erkennbar wird, was die Ausnahmen gemeinsam haben.

Aufruf auf dem Pi:

    cd ~/kalender && .venv/bin/python tools/erinnerungen.py
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


def beschreibe(block: str) -> dict[str, str]:
    daten = {}
    for name in VERRAETERISCH:
        v = wert(block, name)
        if v:
            daten[name] = v
    for x in sorted(set(re.findall(r"^(X-[A-Z0-9-]+)[;:]", block, re.M))):
        daten[x] = wert(block, x)
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
    pfad = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(pfad)
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

        if mit:
            print("\n  MIT Erinnerung:")
            for block in mit[:12]:
                zeige(wert(block, "SUMMARY") or "(ohne Titel)", block)
                print()
        else:
            print("\n  Kein einziger Termin bringt eine Erinnerung mit.")

        if ohne:
            print(f"\n  OHNE Erinnerung (zum Vergleich, {min(4, len(ohne))} Beispiele):")
            for block in ohne[:4]:
                zeige(wert(block, "SUMMARY") or "(ohne Titel)", block)
                print()

    print("\nWorauf zu achten ist: Tragen die Termine mit Erinnerung ein")
    print("ORGANIZER oder ATTENDEE? Dann stammen sie aus einer Einladung.")
    print("Andere X-Eigenschaften deuten auf einen Import aus einem anderen")
    print("Programm hin. Beides erklaert, warum Google dort eine Erinnerung")
    print("mitliefert, bei selbst angelegten Terminen aber nicht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

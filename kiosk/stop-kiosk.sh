#!/usr/bin/env bash
# Beendet die Vollbildanzeige, damit man am Desktop des Pi arbeiten kann.
#
# Der Datendienst (kalender.service) laeuft dabei weiter - nur die Anzeige
# verschwindet. Zurueck geht es mit kiosk/start-kiosk.sh oder einem Neustart.

set -u

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Zuerst die Huelle, sonst startet sie den Browser gleich wieder.
if pkill -f "$HIER/start-kiosk.sh" 2>/dev/null; then
  echo "Kiosk-Skript beendet."
else
  echo "Kein laufendes Kiosk-Skript gefunden."
fi
sleep 0.5

# Nur die eigene Chromium-Instanz treffen - erkennbar am eigenen Profil.
if pkill -f "kalender-chromium" 2>/dev/null; then
  echo "Anzeige geschlossen."
else
  echo "Keine Anzeige gefunden."
fi

cat <<EOF

Der Kalenderdienst laeuft weiter (systemctl status kalender).
Zurueck zur Vollbildanzeige:
    $HIER/start-kiosk.sh &
EOF

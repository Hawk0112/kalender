#!/usr/bin/env bash
# Neuen Programmstand uebernehmen, nachdem die Dateien ersetzt wurden.
#
# Schneller Weg fuer reine Programmaenderungen. Haben sich Systemdinge
# geaendert (neue Pakete, GPIO, sudo-Regel, Autostart), nimm stattdessen
# install.sh - das laesst sich jederzeit gefahrlos erneut ausfuehren.
#
# config.yaml und der Zwischenspeicher bleiben in beiden Faellen erhalten.
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

if [ ! -d "$APPDIR/.venv" ]; then
  warn "Keine Python-Umgebung gefunden - bitte einmal 'bash install.sh' ausfuehren."
  exit 1
fi

# Zeilenenden reparieren, falls die Dateien ueber Windows gekommen sind.
sed -i 's/\r$//' "$APPDIR"/*.sh "$APPDIR/kiosk/"*.sh 2>/dev/null || true
chmod +x "$APPDIR/kiosk/"*.sh 2>/dev/null || true

info "Python-Bibliotheken abgleichen"
"$APPDIR/.venv/bin/pip" install --quiet --upgrade pip
"$APPDIR/.venv/bin/pip" install --quiet -r "$APPDIR/requirements.txt"

info "Konfiguration pruefen"
if "$APPDIR/.venv/bin/python" -c "
import sys; sys.path.insert(0, '$APPDIR')
from app.config import load_config
load_config('$APPDIR/config.yaml')
print('config.yaml ist in Ordnung.')
"; then
  :
else
  warn "config.yaml wird nicht angenommen - der Dienst startet so nicht."
  warn "Bitte die Meldung oben beheben, dann update.sh erneut ausfuehren."
  exit 1
fi

info "Dienst neu starten"
sudo systemctl restart kalender.service
sleep 2

PORT="$(sed -n 's/^[[:space:]]*port:[[:space:]]*\([0-9]\+\).*/\1/p' "$APPDIR/config.yaml" | head -n1)"
PORT="${PORT:-8080}"

if curl -sf --max-time 5 "http://127.0.0.1:${PORT}/healthz" >/dev/null; then
  VERSION="$(curl -s --max-time 5 "http://127.0.0.1:${PORT}/api/week" \
    | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  info "Fertig"
  cat <<EOF

  Dienst laeuft, Programmstand: ${VERSION:-unbekannt}

  Die Anzeige laedt sich innerhalb einer Minute von selbst neu.
  Wurde start-kiosk.sh geaendert, ist zusaetzlich ein Neustart noetig:
      sudo reboot
EOF
else
  warn "Der Dienst antwortet nicht. Zur Ursache:"
  warn "    journalctl -u kalender -n 40"
  exit 1
fi

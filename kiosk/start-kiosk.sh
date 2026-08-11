#!/usr/bin/env bash
# Startet Chromium im Vollbild auf der Kalenderseite.
# Wird von der Desktop-Sitzung beim Hochfahren aufgerufen.

set -u

URL="${KALENDER_URL:-http://127.0.0.1:8080/}"
PROFILE="${HOME}/.local/share/kalender-chromium"

# Nur eine Instanz, egal wie viele Autostart-Mechanismen greifen.
exec 9>"/tmp/kalender-kiosk.lock"
if command -v flock >/dev/null 2>&1 && ! flock -n 9; then
  echo "Kiosk laeuft bereits."
  exit 0
fi

# Chromium heisst je nach Image anders.
BROWSER=""
for candidate in chromium-browser chromium google-chrome; do
  if command -v "$candidate" >/dev/null 2>&1; then
    BROWSER="$candidate"
    break
  fi
done
if [ -z "$BROWSER" ]; then
  echo "Kein Chromium gefunden. Installiere: sudo apt install -y chromium-browser" >&2
  exit 1
fi

# Bildschirmschoner aus (nur unter X11 relevant).
if [ "${XDG_SESSION_TYPE:-}" = "x11" ]; then
  xset s off -dpms s noblank 2>/dev/null || true
  command -v unclutter >/dev/null 2>&1 && unclutter -idle 1 -root &
fi

# Warten bis der Datendienst antwortet (max. 2 Minuten).
HEALTH="${URL%/}/healthz"
for _ in $(seq 1 60); do
  if curl -sf --max-time 2 "$HEALTH" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# "Chromium wurde nicht ordnungsgemaess beendet"-Dialog nach Stromausfall vermeiden.
PREFS="${PROFILE}/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS" 2>/dev/null || true
fi

FLAGS=(
  --kiosk
  --app="$URL"
  --user-data-dir="$PROFILE"
  --start-fullscreen
  --noerrdialogs
  --disable-infobars
  --disable-session-crashed-bubble
  --disable-features=Translate,TranslateUI,AutofillServerCommunication
  --disable-pinch
  --overscroll-history-navigation=0
  --no-first-run
  --fast
  --fast-start
  --check-for-update-interval=31536000
  --disable-component-update
  # Ohne diese Zeile bliebe der Alarmton stumm: Chromium spielt sonst erst
  # nach einer Benutzereingabe Ton ab, und die gibt es hier nicht.
  --autoplay-policy=no-user-gesture-required
)

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  FLAGS+=(--ozone-platform=wayland)
fi

# Nach einem Absturz neu starten - die Anzeige darf nicht schwarz bleiben.
# Wird der Browser dagegen bewusst geschlossen (Alt+F4, Rueckgabewert 0), bleibt
# er zu: nur so kommt man ohne SSH an den Desktop des Pi.
while true; do
  "$BROWSER" "${FLAGS[@]}"
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "Chromium wurde bewusst beendet - der Kiosk startet nicht neu."
    echo "Zurueck zur Anzeige: $0   (oder abmelden bzw. neu starten)"
    break
  fi
  echo "Chromium beendet (Code $code), Neustart in 5 s."
  sleep 5
done

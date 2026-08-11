#!/usr/bin/env bash
# Installation auf dem Raspberry Pi (Raspberry Pi OS Bookworm/Trixie, Pi 5).
# Aufruf:  bash install.sh
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNUSER="${SUDO_USER:-$(id -un)}"
USERHOME="$(getent passwd "$RUNUSER" | cut -d: -f6)"

info()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ]; then
  warn "Bitte nicht direkt als root starten, sondern als normaler Benutzer (z. B. 'pi')."
  exit 1
fi

# Zeilenenden korrigieren, falls die Dateien von Windows kopiert wurden.
sed -i 's/\r$//' "$APPDIR/kiosk/"*.sh 2>/dev/null || true

info "Systempakete"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip curl ca-certificates chromium-browser fonts-noto-core \
  python3-gpiozero python3-lgpio

info "Python-Umgebung"
# Die GPIO-Pakete kommen von der Distribution, die Umgebung braucht deshalb
# Zugriff auf die Systempakete. Aeltere Umgebungen ohne diesen Zugriff werden
# einmalig neu angelegt.
if [ -d "$APPDIR/.venv" ] && ! grep -q "include-system-site-packages = true" "$APPDIR/.venv/pyvenv.cfg" 2>/dev/null; then
  warn "Umgebung wird neu angelegt, damit der Taster GPIO nutzen kann."
  rm -rf "$APPDIR/.venv"
fi
if [ ! -d "$APPDIR/.venv" ]; then
  python3 -m venv --system-site-packages "$APPDIR/.venv"
fi
"$APPDIR/.venv/bin/pip" install --quiet --upgrade pip
"$APPDIR/.venv/bin/pip" install --quiet -r "$APPDIR/requirements.txt"

info "Konfiguration"
if [ ! -f "$APPDIR/config.yaml" ]; then
  cp "$APPDIR/config.example.yaml" "$APPDIR/config.yaml"
  warn "config.yaml angelegt - trage dort deine Kalender-URLs ein."
else
  echo "config.yaml ist vorhanden, bleibt unveraendert."
fi
mkdir -p "$APPDIR/cache"

PORT="$(sed -n 's/^[[:space:]]*port:[[:space:]]*\([0-9]\+\).*/\1/p' "$APPDIR/config.yaml" | head -n1)"
PORT="${PORT:-8080}"
URL="http://127.0.0.1:${PORT}/"

info "Dienst kalender.service"
sed -e "s|__APPDIR__|$APPDIR|g" -e "s|__USER__|$RUNUSER|g" \
  "$APPDIR/systemd/kalender.service.template" | sudo tee /etc/systemd/system/kalender.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable kalender.service
# Ausdruecklich neu starten: 'enable --now' wuerde einen bereits laufenden
# Dienst stehen lassen, beim Aktualisieren liefe dann der alte Programmstand.
sudo systemctl restart kalender.service

info "Neustart per langem Tastendruck"
# Der Dienst laeuft als normaler Benutzer und darf sonst nichts als root tun.
# Diese Regel erlaubt genau einen Befehl: den Neustart des Systems.
SUDOERS_TMP="$(mktemp)"
cat > "$SUDOERS_TMP" <<EOF
# Angelegt von $APPDIR/install.sh
# Erlaubt dem Kalender genau einen Befehl als root: den Systemneustart.
$RUNUSER ALL=(root) NOPASSWD: /usr/sbin/reboot, /sbin/reboot
EOF
if sudo visudo -cqf "$SUDOERS_TMP" 2>/dev/null; then
  sudo install -m 0440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/kalender-reboot
  echo "Regel /etc/sudoers.d/kalender-reboot eingerichtet."
else
  warn "sudo-Regel war fehlerhaft und wurde NICHT installiert."
  warn "Der Taster beendet weiterhin den Alarm, startet aber nicht neu."
fi
rm -f "$SUDOERS_TMP"

info "Kiosk-Autostart"
chmod +x "$APPDIR/kiosk/start-kiosk.sh" "$APPDIR/kiosk/stop-kiosk.sh"
KIOSK="$APPDIR/kiosk/start-kiosk.sh"

# Die Kalender-URL fuer das Kiosk-Skript hinterlegen.
mkdir -p "$USERHOME/.config/kalender"
printf 'KALENDER_URL=%s\n' "$URL" > "$USERHOME/.config/kalender/env"

# 1) labwc (Standard-Sitzung auf dem Pi 5)
mkdir -p "$USERHOME/.config/labwc"
LABWC="$USERHOME/.config/labwc/autostart"
touch "$LABWC"
if ! grep -q "start-kiosk.sh" "$LABWC"; then
  printf '\n# Kalender-Anzeige\nKALENDER_URL=%s %s &\n' "$URL" "$KIOSK" >> "$LABWC"
fi
chmod +x "$LABWC" 2>/dev/null || true

# 2) wayfire (aeltere Images)
WAYFIRE="$USERHOME/.config/wayfire.ini"
if [ -f "$WAYFIRE" ] && ! grep -q "start-kiosk.sh" "$WAYFIRE"; then
  if grep -q '^\[autostart\]' "$WAYFIRE"; then
    sed -i "/^\[autostart\]/a kalender = $KIOSK" "$WAYFIRE"
  else
    printf '\n[autostart]\nkalender = %s\n' "$KIOSK" >> "$WAYFIRE"
  fi
fi

# 3) XDG-Autostart (X11/LXDE und als Rueckfall)
mkdir -p "$USERHOME/.config/autostart"
cat > "$USERHOME/.config/autostart/kalender-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kalender
Exec=env KALENDER_URL=$URL $KIOSK
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

info "Bildschirm dauerhaft an"
if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_blanking 1 || warn "Bildschirmschoner konnte nicht abgeschaltet werden."
fi

info "Fertig"
cat <<EOF

  Datendienst : systemctl status kalender
  Protokoll   : journalctl -u kalender -f
  Anzeige     : $URL
  Einstellung : $APPDIR/config.yaml   (danach: sudo systemctl restart kalender)

  Vollbild verlassen : Alt+F4, oder $APPDIR/kiosk/stop-kiosk.sh
  Vollbild starten   : $APPDIR/kiosk/start-kiosk.sh &

  Naechster Schritt: Kalender-URLs in config.yaml eintragen und neu starten:
      sudo systemctl restart kalender && sudo reboot
EOF

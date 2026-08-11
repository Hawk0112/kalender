# Einrichtung auf dem Raspberry Pi 5 – Schritt für Schritt

Ausgangspunkt: Auf der SSD liegt eine frische Installation von **Raspberry Pi OS
mit Desktop** (64 Bit, Bookworm oder neuer), der Pi startet und du siehst den
Desktop.

Ziel: Nach jedem Einschalten erscheint automatisch die Wochenansicht im
Vollbild, ohne dass jemand etwas anklicken muss.

Rechne mit 30 bis 45 Minuten, das meiste davon Wartezeit beim Aktualisieren.

---

## Was du brauchst

| | |
|---|---|
| Raspberry Pi 5 mit Netzteil | 27 W USB-C empfohlen |
| SSD mit Pi OS Desktop | fertig installiert |
| Display + HDMI-Kabel | Querformat |
| Tastatur und Maus | nur für die Einrichtung, danach nicht mehr |
| Netzwerk | LAN oder WLAN, dauerhaft |
| Tonausgabe | **wichtig:** der Pi 5 hat *keinen* Klinkenausgang. Lautsprecher im Display über HDMI, USB-Lautsprecher oder USB-Audioadapter |
| Taster (optional) | einfacher Schließer mit zwei Drähten, für das Abschalten des Alarmtons |

Außerdem die ICS-Adressen deiner Kalender. Wie du die bekommst, steht in
[README.md](README.md) im Abschnitt „Kalender-URLs beschaffen". Du kannst sie
aber auch später bequem am Bildschirm eintragen.

---

## Schritt 1 – Grundeinstellungen

Beim ersten Start führt dich der Assistent durch Land, Sprache, Tastatur,
Benutzername und WLAN. Wichtig sind:

* **Land: Österreich**, damit Zeitzone und WLAN-Funkbereich stimmen.
* **Benutzername:** merk ihn dir, du brauchst ihn gleich. Im Weiteren steht
  `pi` dafür – ersetze das durch deinen Namen.
* **WLAN** verbinden (oder LAN-Kabel einstecken).

Falls du den Assistenten übersprungen hast, holst du die Zeitzone so nach:

```bash
sudo raspi-config
```

→ *Localisation Options* → *Timezone* → *Europe* → *Vienna*.

Prüfe danach, ob die Uhr stimmt – ein falsches Datum würde den falschen Tag als
ersten anzeigen:

```bash
timedatectl
```

In der Ausgabe müssen `Time zone: Europe/Vienna` und
`System clock synchronized: yes` stehen.

---

## Schritt 2 – System aktualisieren

```bash
sudo apt update && sudo apt full-upgrade -y
```

Das dauert bei einer frischen Installation einige Minuten. Danach einmal neu
starten:

```bash
sudo reboot
```

---

## Schritt 3 – Automatische Anmeldung sicherstellen

Damit die Anzeige nach einem Stromausfall von allein hochkommt, muss der Pi
ohne Passwortabfrage auf den Desktop starten. Bei der Standardinstallation ist
das meist schon so; sicherheitshalber:

```bash
sudo raspi-config
```

→ *System Options* → *Boot / Auto Login* → **Desktop Autologin** → *Finish*.

---

## Schritt 4 – Tonausgabe wählen

Nur nötig, wenn du den Alarmton nutzen willst.

Schließe die Tonquelle an (Display über HDMI, USB-Lautsprecher oder
USB-Adapter). Dann **Rechtsklick auf das Lautsprechersymbol** oben rechts in
der Taskleiste und das gewünschte Gerät auswählen. Lautstärke auf einen
kräftigen Wert stellen – im Kalender lässt sie sich später noch feiner regeln.

Zum Ausprobieren:

```bash
speaker-test -c2 -t wav -l1
```

Hörst du nichts, prüfe die Geräteauswahl und ob am Display der Ton nicht
stummgeschaltet ist.

---

## Schritt 5 – Die Dateien auf den Pi bringen

Das Projekt liegt auf deinem Windows-Rechner unter `C:\Projekte\Kalender`.
Wähle einen der drei Wege.

### Variante A – USB-Stick (am einfachsten)

1. Am Windows-Rechner den **gesamten Ordner** `Kalender` auf einen USB-Stick
   kopieren. Den Unterordner `.venv` brauchst du nicht, der wird am Pi neu
   angelegt.
2. Stick am Pi einstecken, der Dateimanager öffnet sich.
3. Im Terminal am Pi:

```bash
cp -r /media/$USER/*/Kalender ~/kalender
```

Findet der Befehl nichts, schau im Dateimanager nach dem genauen Pfad des
Sticks und passe ihn an.

### Variante B – Über das Netzwerk (ohne Stick)

Erst am Pi SSH einschalten:

```bash
sudo raspi-config
```

→ *Interface Options* → *SSH* → *Yes*. Dann die Adresse des Pi notieren:

```bash
hostname -I
```

Jetzt am **Windows-Rechner** in PowerShell (ersetze Benutzer und Adresse). Der
Umweg über `cd` verhindert, dass `scp` den Laufwerksbuchstaben für einen
Rechnernamen hält:

```powershell
cd C:\Projekte
scp -r .\Kalender pi@192.168.1.50:~/kalender
```

Der Ordner `~/kalender` darf am Pi noch nicht existieren, sonst landen die
Dateien eine Ebene tiefer. Der Unterordner `.venv` wird mitkopiert und ist
unbrauchbar – das Installationsskript legt ihn selbst neu an, du musst dich
nicht darum kümmern.

### Variante C – Aus einem Git-Repository

Wenn du das Projekt in ein Repository gelegt hast:

```bash
git clone <adresse-deines-repos> ~/kalender
```

### In jedem Fall danach prüfen

```bash
ls ~/kalender
```

Du musst `install.sh`, `app`, `kiosk` und `config.example.yaml` sehen.

Hast du die Dateien unter Windows in einem Editor geöffnet und gespeichert,
könnten die Zeilenenden falsch sein. Der folgende Befehl schadet nie und
repariert das vorsorglich:

```bash
sed -i 's/\r$//' ~/kalender/install.sh ~/kalender/kiosk/start-kiosk.sh
```

---

## Schritt 6 – Installation ausführen

```bash
cd ~/kalender && bash install.sh
```

Das Skript erledigt in einem Durchgang:

* Systempakete nachinstallieren (Chromium, GPIO-Unterstützung, Schriften)
* die Python-Umgebung anlegen und die Bibliotheken installieren
* `config.yaml` aus der Vorlage erzeugen
* den Dienst `kalender.service` einrichten und starten
* den Kiosk-Autostart eintragen
* den Bildschirmschoner abschalten

Zwischendurch fragt es nach deinem Passwort (für `sudo`). Am Ende zeigt es eine
Zusammenfassung mit der Adresse der Anzeige.

Kurz prüfen, ob der Dienst läuft:

```bash
systemctl status kalender
```

Es muss `active (running)` dastehen. Mit `q` verlässt du die Anzeige.

---

## Schritt 7 – Kalender eintragen

Am schnellsten geht es am Bildschirm. Öffne Chromium über das Startmenü und
rufe `http://localhost:8080` auf – der Vollbildmodus startet erst nach dem
nächsten Neustart, im normalen Fenster geht es jetzt bequemer. Klicke oben
rechts auf das **Zahnrad** und trage unter *Kalender* Name, ICS-Adresse und
Farbe ein. Der Knopf **Testen** sagt dir
sofort, ob die Adresse stimmt und wie viele Termine sie enthält. Danach
*Speichern* – die Anzeige übernimmt es ohne Neustart.

Der Demokalender ist zu Beginn eingetragen, damit du überhaupt etwas siehst. Er
lässt sich nicht über das Zahnrad entfernen, weil er eine lokale Datei ist.
Wenn du ihn loswerden willst, nimm ihn aus der Datei:

```bash
nano ~/kalender/config.yaml
```

Den Block mit `name: Demo` löschen, mit `Strg`+`O` speichern, `Strg`+`X`
schließen, dann:

```bash
sudo systemctl restart kalender
```

---

## Schritt 8 – Taster anschließen (optional)

**Vorher den Pi ausschalten und vom Strom trennen.**

Drei Taster, alle mit gemeinsamer Masse an **Pin 9 (GND)**:

```
        3V3  (1) (2)  5V
      GPIO2  (3) (4)  5V
      GPIO3  (5) (6)  GND
      GPIO4  (7) (8)  GPIO14
        GND  (9) (10) GPIO15   <- Pin 9  = GND, gemeinsam für alle drei
     GPIO17 (11) (12) GPIO18   <- Pin 11 = Taster 1
     GPIO27 (13) (14) GND      <- Pin 13 = Taster 2
     GPIO22 (15) (16) GPIO23   <- Pin 15 = Taster 3
```

Jeder Taster bekommt einen Draht auf seinen Signalstift und einen auf die
gemeinsame Masse. Ein Widerstand ist nicht nötig, die Polung ist egal.

| Taster | Wirkung |
|---|---|
| **1** (Pin 11) | kurz: Alarmton beenden – läutet nichts: zurück auf die aktuelle Woche. **20 s halten: Neustart** |
| **2** (Pin 13) | eine Woche vorwärts |
| **3** (Pin 15) | eine Woche zurück |

Wurde geblättert und danach fünf Minuten lang kein Taster mehr gedrückt,
springt die Anzeige von selbst auf die aktuelle Woche zurück. Die Frist stellst
du im Zahnrad unter *Anzeige* ein.

Du musst nicht alle drei anbringen: Trag in `config.yaml` bei
`gpio_forward` bzw. `gpio_back` eine `0` ein, wenn du darauf verzichtest.

Für den Neustart legt `install.sh` die Regel `/etc/sudoers.d/kalender-reboot`
an. Sie erlaubt dem Kalender genau einen Befehl ohne Passwort – `reboot` – und
sonst nichts. Willst du das nicht, entferne sie mit
`sudo rm /etc/sudoers.d/kalender-reboot`; der Taster beendet dann weiterhin den
Alarmton.

Nach dem Einschalten prüfen:

```bash
curl -s localhost:8080/api/button
```

Die Ausgabe enthält einen Zähler je Taster (`today`, `forward`, `back`); der
passende muss bei jedem Druck um eins steigen. Den Neustart probierst du am
besten gleich einmal aus – Taster 1 zwanzig Sekunden halten, der Pi fährt
herunter und kommt mit dem Kalender wieder hoch.

---

## Schritt 9 – Neu starten und abnehmen

```bash
sudo reboot
```

Nach dem Hochfahren muss die Wochenansicht von allein im Vollbild erscheinen.
Geh diese Liste durch:

- [ ] Der Kalender erscheint ohne Zutun, ohne Fensterrahmen und ohne Mauszeiger.
- [ ] Ganz links steht der heutige Tag, rechts davon die nächsten sechs.
- [ ] Deine Termine sind da, in den gewählten Farben.
- [ ] Oben rechts steht „aktualisiert HH:MM" mit einem grünen Punkt.
- [ ] Die Uhr oben rechts geht richtig.
- [ ] Der Bildschirm wird nach 10 Minuten nicht dunkel.
- [ ] Der Alarmton lässt sich im Zahnrad unter *Alarm* mit **Ton anhören** hören.
- [ ] Taster 1 beendet den Probeton (falls angeschlossen).
- [ ] Taster 2 und 3 blättern eine Woche vor und zurück, oben erscheint dabei
      der Hinweis „1 Woche voraus" bzw. „1 Woche zurück".
- [ ] Taster 1 bringt die Ansicht wieder auf die aktuelle Woche.
- [ ] Nach fünf Minuten ohne Tastendruck springt eine verschobene Ansicht von
      selbst zurück.

Dann kannst du Tastatur und Maus abziehen. Zum Ändern der Einstellungen
brauchst du sie später kurz wieder – oder du greifst per SSH zu. Wie du aus dem
Vollbild wieder herauskommst, steht weiter unten.

---

## Fehlersuche

| Beobachtung | Ursache und Abhilfe |
|---|---|
| Nach dem Neustart bleibt der Desktop sichtbar, kein Kalender | Autostart hat nicht gegriffen. Starte von Hand: `bash ~/kalender/kiosk/start-kiosk.sh` – erscheint der Kalender, prüfe Schritt 3 (Desktop Autologin). |
| Schwarzes Fenster mit Fehlermeldung „Seite nicht erreichbar" | Der Dienst läuft nicht: `systemctl status kalender` und `journalctl -u kalender -n 50`. |
| Anzeige leer, oben rechts „offline" | Kalenderadresse falsch oder kein Netz. Im Zahnrad den Knopf **Testen** benutzen. |
| Falscher Tag ganz links | Zeitzone oder Uhrzeit falsch: `timedatectl`, siehe Schritt 1. |
| Termine um Stunden verschoben | Zeitzone im Kalender: im Zahnrad unter *Allgemein* muss `Europe/Vienna` stehen. |
| Kein Alarmton, Leiste erscheint aber | Tonausgabe prüfen (Schritt 4). Steht in der Anzeige „Ton stummgeschaltet", hat Chromium den Ton blockiert – dann läuft der Kiosk noch mit alten Einstellungen: `bash ~/kalender/install.sh` erneut ausführen und neu starten. |
| Taster tut nichts | `journalctl -u kalender -n 50` ansehen. Beim Start muss je Taster eine Zeile wie `Taster 'forward' aktiv an GPIO27` stehen. Fehlt sie, prüfe die Verdrahtung. Bei einer Rechtemeldung: `sudo usermod -aG gpio $USER`, dann neu starten. |
| Ansicht steht auf der falschen Woche | Taster 1 kurz drücken (oder `Pos1` auf der Tastatur); nach fünf Minuten springt sie ohnehin von selbst zurück. Neben dem Datum steht, um wie viele Wochen sie verschoben ist. |
| Langes Halten startet nicht neu | Im Protokoll steht `Neustart fehlgeschlagen`. Dann fehlt die sudo-Regel: `ls -l /etc/sudoers.d/kalender-reboot` prüfen und notfalls `bash ~/kalender/install.sh` erneut ausführen. |
| Bildschirm wird nach einiger Zeit schwarz | `sudo raspi-config` → *Display Options* → *Screen Blanking* → *No*. |
| `install.sh: line 1: $'\r': command not found` | Zeilenenden aus Windows. Den `sed`-Befehl aus Schritt 5 ausführen. |

Nützliche Befehle im Alltag:

```bash
journalctl -u kalender -f
```

```bash
sudo systemctl restart kalender
```

---

## Aus dem Vollbild heraus zum Desktop

Willst du später am Betriebssystem des Pi etwas einstellen — WLAN, Tonausgabe,
Updates — musst du die Vollbildanzeige verlassen:

| Situation | Weg |
|---|---|
| Tastatur am Pi | **Alt+F4** – die Anzeige schließt sich, der Desktop erscheint |
| Terminal offen oder per SSH | `~/kalender/kiosk/stop-kiosk.sh` |
| Nichts davon greift | **Strg+Alt+F2** wechselt auf eine Textkonsole, dort anmelden und `~/kalender/kiosk/stop-kiosk.sh` ausführen; mit **Strg+Alt+F1** zurück |

Zurück zur Anzeige:

```bash
~/kalender/kiosk/start-kiosk.sh &
```

Alternativ `sudo reboot` – nach dem Hochfahren ist der Kalender wieder da. Der
Kalenderdienst läuft die ganze Zeit weiter, du verlierst also nichts.

Nur Kalender-Einstellungen ändern? Dafür musst du das Vollbild nicht verlassen,
dazu genügt das Zahnrad oben rechts.

## Später etwas ändern

* **Kalender, Farben, Alarm, Zeitfenster:** Zahnrad oben rechts (oder Taste `E`),
  wirkt sofort.
* **Taster-Pin, Port, Abrufintervall:** in `~/kalender/config.yaml`, danach
  `sudo systemctl restart kalender`.
* **Neue Programmfassung einspielen:** siehe unten.

Alle Einstellungen im Einzelnen sind in [README.md](README.md) beschrieben.

---

## Neue Programmfassung einspielen

Das Betriebssystem bleibt unangetastet, es werden nur die Programmdateien
ersetzt. Deine `config.yaml` mit allen Kalendern und Einstellungen bleibt
erhalten – ebenso `.venv` und der Zwischenspeicher.

**1. Neue Dateien auf den Pi bringen**, zunächst in einen Zwischenordner, damit
nichts Bestehendes überschrieben wird. Am Windows-Rechner:

```powershell
cd C:\Projekte
scp -r .\Kalender pi@192.168.1.50:/tmp/kalender-neu
```

Ein USB-Stick tut es genauso – Hauptsache, die neuen Dateien liegen zuerst
unter `/tmp/kalender-neu`.

**2. Programmteile ersetzen** (am Pi):

```bash
rm -rf ~/kalender/app ~/kalender/kiosk ~/kalender/systemd ~/kalender/demo
cp -a /tmp/kalender-neu/{app,kiosk,systemd,demo} ~/kalender/
cp -a /tmp/kalender-neu/{*.sh,*.md,requirements.txt,config.example.yaml} ~/kalender/
rm -rf /tmp/kalender-neu
```

**3. Übernehmen:**

```bash
bash ~/kalender/update.sh
```

Das Skript gleicht die Bibliotheken ab, prüft deine `config.yaml` und startet
den Dienst neu. Die Anzeige lädt sich danach innerhalb einer Minute von selbst
neu – du musst weder Tastatur anstecken noch den Kiosk anfassen.

**Wann stattdessen `bash ~/kalender/install.sh`?** Immer, wenn sich etwas am
System ändert: neue Pakete, GPIO, sudo-Regel, Autostart. Das Skript lässt sich
jederzeit gefahrlos erneut ausführen und behält deine Konfiguration; es dauert
nur länger. Im Zweifel ist es die sichere Wahl.

Wurde `kiosk/start-kiosk.sh` geändert, brauchst du zusätzlich einen `sudo
reboot` – diese Datei wird nur beim Start der Sitzung gelesen.

Nutzt du Git, wird alles zu:

```bash
cd ~/kalender && git pull && bash update.sh
```

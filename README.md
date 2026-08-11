# Kalender – Wochenansicht für Raspberry Pi 5

Wandkalender für ein Display ohne Touch. Zeigt **heute plus die nächsten 6 Tage**
nebeneinander, holt die Termine als iCal-Feeds (ICS) aus dem Internet und startet
beim Einschalten des Raspberry automatisch im Vollbild.

## Wie es aufgebaut ist

| Teil | Aufgabe |
|---|---|
| `app/server.py` | kleiner Webdienst auf `127.0.0.1:8080`, liefert Seite und `/api/week` |
| `app/store.py` | holt die Kalender im Hintergrund (Standard: alle 15 Minuten) |
| `app/sources.py` | HTTP-Abruf mit ETag und Offline-Cache auf der SD-Karte |
| `app/events.py` | wertet Serientermine aus und verteilt sie auf Tagesspalten |
| `app/static/` | die Anzeige (HTML/CSS/JS), aktualisiert sich jede Minute selbst |
| `app/static/settings.js` | Einstellungsdialog hinter dem Zahnrad |
| `app/static/alarm.js` | Alarmton bei Erinnerungen, Töne werden im Browser erzeugt |
| `app/button.py` | Taster am GPIO zum Abschalten des Alarmtons |
| `app/buzzer.py` | Piezo-Summer am GPIO, erzeugt die Alarmtöne per PWM |
| `app/alarm_runner.py` | löst den Summer aus, wenn eine Erinnerung fällig wird |
| `kiosk/start-kiosk.sh` | startet Chromium im Kiosk-Modus, startet ihn bei Absturz neu |
| `kiosk/stop-kiosk.sh` | beendet die Vollbildanzeige, um am Desktop zu arbeiten |
| `systemd/` | Vorlage für den Dienst `kalender.service` |

Der Dienst und die Anzeige sind bewusst getrennt: Der Dienst läuft ab dem Boot,
auch bevor der Bildschirm da ist, und überlebt einen Browser-Neustart.

> **Schritt-für-Schritt-Anleitung ab frischer Pi-OS-Installation:**
> [ANLEITUNG.md](ANLEITUNG.md)

## Installation auf dem Raspberry Pi

Voraussetzung: Raspberry Pi OS **mit Desktop** (Bookworm oder neuer), Netzwerk
eingerichtet, richtige Zeitzone (`sudo raspi-config` → Localisation Options).

```bash
git clone <dieses-repo> ~/kalender      # oder Ordner per USB/scp kopieren
cd ~/kalender
bash install.sh
```

Das Skript installiert die Systempakete, legt die Python-Umgebung an, richtet
`kalender.service` ein, trägt den Kiosk-Autostart ein (labwc, wayfire und
XDG-Autostart) und schaltet den Bildschirmschoner ab.

Danach die Kalender eintragen:

```bash
nano ~/kalender/config.yaml
sudo systemctl restart kalender
sudo reboot
```

Nach dem Neustart erscheint die Wochenansicht automatisch im Vollbild.

## Kalender-URLs beschaffen

* **Google Kalender** – Einstellungen → Kalender auswählen → *Geheime Adresse im
  iCal-Format*. Die URL endet auf `/basic.ics`.
* **Outlook / Microsoft 365** – Kalender → Freigeben → Veröffentlichen → ICS-Link.
* **Nextcloud** – Kalender → `…` → Link kopieren, `?export` anhängen.
* **Apple iCloud** – Kalender freigeben („Öffentlicher Kalender“), `webcal://`-Link.
  Der wird automatisch in `https://` umgeschrieben.
* **Müllabfuhr, Vereine, Schulen** – meist als ICS-Abo auf der Website.

Mehrere Kalender werden farblich unterschieden. Die geheimen URLs stehen im
Klartext in `config.yaml`; die Datei ist deshalb in `.gitignore` ausgenommen.

## Einstellungen über das Zahnrad

Oben rechts neben der Uhr sitzt ein Zahnrad. Ein Klick darauf öffnet die
Einstellungen; ohne Maus geht es auch mit der Taste `E`, `Esc` schließt wieder.
Dort lässt sich alles ändern, was im laufenden Betrieb gebraucht wird:

* **Kalender** – hinzufügen, entfernen, umbenennen, Farbe wählen (Farbfelder
  oder freie Farbwahl) und einzelne Termine über Stichwörter ausblenden. Der
  Knopf **Testen** ruft die Adresse sofort ab und meldet zurück, wie der
  Kalender heißt und wie viele Termine er in den nächsten 30 Tagen enthält –
  so merkst du Tippfehler vor dem Speichern. **Jetzt aktualisieren** holt alle
  gespeicherten Kalender sofort neu, ohne aufs Intervall zu warten, und meldet,
  ob es geklappt hat.
* **Hervorhebungen** – Regeln wie „Geburtstage", siehe unten.
* **Anzeige** – Anzahl Tage, Stundenraster oder Terminliste, Zeitfenster,
  Uhr und Kalenderwoche.
* **Nachtabsenkung** und **Allgemein** (Zeitzone, Sprache, Abrufintervall).

Gespeichert wird direkt in `config.yaml`; die vorherige Fassung bleibt als
`config.yaml.bak` liegen. Die Änderung greift sofort – **kein Neustart und kein
Reboot nötig**. Kalender, deren Adresse gleich geblieben ist, behalten ihre
Daten, damit die Anzeige beim Speichern nicht kurz leer wird. Fehlerhafte
Eingaben (unbekannte Zeitzone, ungültige Adresse, doppelter Kalender) werden
abgewiesen und im Dialog erklärt, die Datei bleibt in dem Fall unverändert.

Zwei bewusste Einschränkungen: Über die Oberfläche sind nur `https://`- und
`webcal://`-Adressen erlaubt, keine lokalen Dateipfade. Ein in der Datei
eingetragener lokaler Kalender (wie `demo/demo.ics`) wird im Dialog nur
angezeigt und bleibt beim Speichern erhalten.

## Einstellungen in der Datei (`config.yaml`)

Alles ist auch direkt in der Datei einstellbar – manches gibt es nur dort
(`server.host`, `server.port`, `refresh.retry_minutes`,
`refresh.stale_after_minutes`). Wichtigste Werte:

| Schlüssel | Bedeutung |
|---|---|
| `timezone`, `locale` | Zeitzone und Sprache der Beschriftung |
| `view.days` | Anzahl der Spalten (7 = heute + 6 Tage) |
| `view.day_start_hour` / `day_end_hour` | Zeitfenster des Stundenrasters, voreingestellt 6–22; Termine außerhalb landen in den Sammelzeilen, siehe oben |
| `highlights` | auffällige Termine, siehe oben |
| `alarm` | Alarmton bei Erinnerungen, siehe oben |
| `button` | Taster am GPIO, siehe oben (nur in der Datei einstellbar) |
| `view.layout` | `timegrid` (Stundenraster) oder `agenda` (Liste je Tag, gut für kleine Displays) |
| `view.return_to_today_minutes` | nach Blättern von selbst zurück auf die aktuelle Woche, `0` = aus |
| `view.dim` | Nachtabsenkung der Helligkeit |
| `refresh.interval_minutes` | Abstand der Internet-Abrufe |
| `calendars[].exclude` | Termine mit diesen Wörtern im Titel ausblenden |

Nach Änderungen direkt in der Datei: `sudo systemctl restart kalender`.
(Beim Speichern über das Zahnrad entfällt das.)

## Die Wochenansicht

Das Stundenraster zeigt **06:00 bis 22:00 Uhr**. Termine, die vollständig davor
oder danach liegen, gehen nicht verloren: Sie erscheinen gesammelt in einer
schmalen Zeile oberhalb („vor 06:00") bzw. unterhalb („nach 22:00") des
Rasters, mit Uhrzeit und Titel. Diese Zeilen tauchen nur auf, wenn es an
irgendeinem der sieben Tage etwas zu zeigen gibt, und kosten sonst keinen
Platz. Ein Termin, der über den Rand hinausreicht (etwa 05:00 bis 07:00),
bleibt im Raster und bekommt eine gestrichelte Kante; seine echte Anfangszeit
steht weiterhin im Termin.

Durch das engere Fenster fällt auf jede Stunde mehr Höhe, deshalb ist die
Stundenskala am linken Rand jetzt deutlich größer gesetzt.

Das Fenster lässt sich über das Zahnrad unter „Anzeige" ändern – wer wieder den
vollen Tag sehen will, stellt 00:00 bis 24:00 ein, dann bleiben die
Sammelzeilen leer.

## Alarm bei Erinnerungen

Trägt ein Termin eine Erinnerung (im iCal-Format `VALARM`, in Google Kalender
„Benachrichtigung: 15 Minuten vorher"), spielt der Kalender zu diesem Zeitpunkt
einen Ton und legt eine **große, mittig zentrierte Anzeige** über den Kalender:
Glockensymbol, Titel in sehr großer Schrift, darunter Uhrzeit, Ort, Kalender
und Vorlauf. Die Fläche nimmt rund 83 % des Bildschirms ein, der Kalender
dahinter wird abgedunkelt – so ist der Termin auch aus einigen Metern
Entfernung lesbar. Der Rahmen leuchtet in der Farbe des Kalenders und pulsiert
im Takt des Tons.

Ausgewertet werden sowohl Erinnerungen relativ zum Beginn als auch zum Ende des
Termins sowie feste Zeitpunkte.

**Termine ohne eigene Erinnerung bleiben still.** Wer möchte, dass sich auch
diese zum Terminbeginn melden, schaltet „Auch bei Terminbeginn" ein; ganztägige
Termine sind davon ausgenommen, sonst klingelte es um Mitternacht.

### Wo der Ton herauskommt

Zur Wahl stehen zwei Wege, umschaltbar im Zahnrad unter *Alarm* → **Ausgabe**:

| Ausgabe | Beschreibung |
|---|---|
| **Summer am GPIO** (Standard) | Piezo-Summer zwischen **Pin 12 (GPIO 18)** und **Pin 14 (GND)**. Den Ton erzeugt der Dienst selbst — er klingelt deshalb auch, wenn der Bildschirm aus ist oder der Browser hängt. |
| **Lautsprecher (HDMI/USB)** | Der Ton kommt wie zuvor aus dem Browser, über die Tonausgabe des Pi. Braucht keine Verdrahtung, aber einen laufenden Browser. |

Für den Summer nimmst du ein **passives** Piezo-Element („passive buzzer", ohne
eigene Elektronik) — ein aktiver Summer kann nur einen einzigen festen Ton.
Zwei Drähte genügen, ein Widerstand ist nicht nötig. Einen richtigen
Lautsprecher darfst du **nicht** direkt an GPIO hängen: Er zöge ein Vielfaches
dessen, was ein Pin verträgt.

Den Pin änderst du bei Bedarf in `config.yaml` unter `alarm.buzzer_gpio`; `0`
heißt „nicht angeschlossen". Danach `sudo systemctl restart kalender`.

### Einstellungen

Im Zahnrad, Abschnitt **Alarm**:

| Einstellung | Bedeutung |
|---|---|
| Aktiv | Alarm ganz an- oder abschalten |
| Ausgabe | Summer am GPIO oder Lautsprecher |
| Ton | Doppelpiep, Wecker, Glockenspiel, Gong oder Sanfter Ton |
| Lautstärke | 0 bis 100 % |
| Ende des Tons | „nach fester Dauer" oder „bei Tasteneingabe" |
| Dauer | Sekunden bei festem Ende, voreingestellt 10 |
| Auch bei Terminbeginn | aus – Termine ohne eigene Erinnerung bleiben still |

Der Knopf **Ton anhören** spielt die aktuelle Auswahl drei Sekunden lang ab —
je nach Einstellung über den Summer oder über den Lautsprecher. Beim Summer
klingt der Ton schlichter: Ein Piezo kann nur Tonhöhen, keine Klangfarben, die
fünf Melodien sind dort also Ton-Pausen-Muster.
Im Modus „bei Tasteneingabe" beendet jede Taste (und auch ein Mausklick) den
Ton; passiert nichts, hört er nach fünf Minuten von selbst auf, damit ein
Termin um drei Uhr früh nicht endlos läutet. Weil die Anzeige den Kalender
verdeckt, steht in beiden Betriebsarten unten, wie man sie vorzeitig loswird –
im Modus mit fester Dauer verschwindet sie zusätzlich von selbst.

Die Anzeige liegt außerhalb des abgedunkelten Bereichs: Die Nachtabsenkung
dimmt sie nicht mit, ein Alarm um drei Uhr früh ist also voll sichtbar.

Bei der Ausgabe **Lautsprecher** werden die Töne im Browser erzeugt (Web
Audio), es gibt also keine Audiodateien, die fehlen oder im falschen Format
vorliegen können. Damit Chromium ohne Benutzereingabe Ton ausgibt, startet
[start-kiosk.sh](kiosk/start-kiosk.sh) ihn mit
`--autoplay-policy=no-user-gesture-required`. Voraussetzung ist eine
angeschlossene Tonausgabe: **Der Raspberry Pi 5 hat keinen Klinkenausgang
mehr**, es bleiben Lautsprecher im Display über HDMI, ein USB-Lautsprecher oder
ein USB-Audioadapter. Ist der Ton stummgeschaltet, erscheint die Anzeige
trotzdem, mit dem Hinweis „Ton stummgeschaltet" — beim Summer entsprechend
„Summer nicht verfügbar".

Nach einem Neustart des Browsers werden Erinnerungen, die währenddessen fällig
gewesen wären, **nicht** nachgeholt.

## Taster am GPIO

Drei einfache Taster (Schließer, je zwei Anschlüsse) bedienen den Kalender —
praktisch, weil am Gerät sonst weder Maus noch Tastatur hängt.

| Taster | kurz drücken | lang drücken |
|---|---|---|
| **1** (GPIO 17, Pin 11) | Alarmton beenden; läutet gerade nichts: zurück auf die aktuelle Woche | 20 s: Neustart |
| **2** (GPIO 27, Pin 13) | eine Woche vorwärts | – |
| **3** (GPIO 22, Pin 15) | eine Woche zurück | – |

### Verdrahtung

Alle drei Taster teilen sich **Pin 9 (GND)** als gemeinsame Masse und gehen
jeweils auf ihren eigenen Signalstift. Die vier Stifte liegen auf der
40-poligen Leiste direkt untereinander in derselben Reihe:

```
        3V3  (1) (2)  5V
      GPIO2  (3) (4)  5V
      GPIO3  (5) (6)  GND
      GPIO4  (7) (8)  GPIO14
        GND  (9) (10) GPIO15   <- Pin 9  = GND, gemeinsam für alle drei
     GPIO17 (11) (12) GPIO18   <- Pin 11 = Taster 1 (Alarm aus / heute)
     GPIO27 (13) (14) GND      <- Pin 13 = Taster 2 (Woche vorwärts)
     GPIO22 (15) (16) GPIO23   <- Pin 15 = Taster 3 (Woche zurück)
```

Ein Widerstand ist nicht nötig: Der interne Pull-up ist eingeschaltet, der
Taster zieht den Eingang beim Drücken gegen Masse. Die Polung ist egal.
Entprellt wird in der Software (50 ms).

Andere Pins trägst du mit ihrer **BCM-Nummer** in `config.yaml` ein — nicht mit
der Nummer auf der Stiftleiste. `0` heißt „nicht angeschlossen", du kannst also
auch nur einen oder zwei Taster anbringen:

```yaml
button:
  enabled: true
  gpio: 17            # Taster 1
  gpio_forward: 27    # Taster 2
  gpio_back: 22       # Taster 3
  pull_up: true
  bounce_time: 0.05
```

Danach `sudo systemctl restart kalender`. Finger weg von GPIO 0 und 1 (HAT-
Erkennung), 2 und 3 (I²C, fest verdrahtete Pull-ups) sowie 14 und 15 (serielle
Konsole).

### Verhalten

**Taster 1 kurz drücken** beendet den Alarmton — in beiden Betriebsarten,
sowohl im Modus „bei Tasteneingabe" als auch vorzeitig im Modus „nach fester
Dauer". In der Alarmanzeige steht „Taster oder beliebige Taste drücken".
Läutet gerade nichts, springt die Ansicht zurück auf die aktuelle Woche. Der
Alarm hat also immer Vorrang: Ein Druck während des Läutens schaltet nur den
Ton ab und lässt die angezeigte Woche unberührt.

**Taster 2 und 3** blättern wochenweise vorwärts und zurück, bis zu ein Jahr in
jede Richtung. Solange nicht die aktuelle Woche zu sehen ist, steht neben dem
Datum ein Hinweis wie „2 Wochen voraus", und keine Spalte ist als heute
hervorgehoben. Erinnerungen bleiben davon unberührt: Sie richten sich immer
nach dem echten Datum und läuten auch dann, wenn du gerade eine andere Woche
ansiehst.

**Nach fünf Minuten ohne weiteren Tastendruck** springt die Anzeige von selbst
auf die aktuelle Woche zurück — sonst bliebe sie stehen, wenn jemand
weitergeblättert hat und weggegangen ist. Jeder Druck auf einen der drei Taster
setzt die Frist neu. Einstellbar im Zahnrad unter *Anzeige* → „Zurück auf heute
nach … Min."; `0` lässt die Ansicht stehen.

Ist eine Tastatur angesteckt, tun die Pfeiltasten `←` und `→` dasselbe, `Pos1`
springt auf heute.

**20 Sekunden gedrückt halten** startet den Pi neu — der Notausgang, wenn
Anzeige oder Browser einmal hängen. Die Erkennung läuft vollständig im Dienst
und braucht die Anzeige nicht, wirkt also gerade dann, wenn am Bildschirm
nichts mehr geht. Kürzeres Halten löst nichts aus; einen zweiten Neustart
löst derselbe Druck nicht aus, falls der Taster klemmt.

Die Haltezeit stellst du in `config.yaml` ein, `0` schaltet den Neustart ab:

```yaml
button:
  reboot_hold_seconds: 20
```

Damit der Dienst neu starten darf, legt `install.sh` die Regel
`/etc/sudoers.d/kalender-reboot` an. Sie erlaubt dem Benutzer **genau einen**
Befehl ohne Passwort — `reboot` — und sonst nichts. Vor dem Einrichten prüft
das Skript die Regel mit `visudo`; schlägt die Prüfung fehl, wird sie nicht
installiert und der Taster beendet weiterhin nur den Alarm. Entfernen kannst du
sie jederzeit mit `sudo rm /etc/sudoers.d/kalender-reboot`.

Abgefragt wird der Taster nur, solange ein Alarm läuft — im Ruhezustand
entsteht kein Datenverkehr. Die Reaktion erfolgt binnen etwa einer halben
Sekunde.

Fehlt die Hardware oder ist der Pin belegt, läuft alles Übrige unverändert
weiter; im Protokoll steht dann eine Zeile wie `Taster nicht verfuegbar (…)`.

### Prüfen

```bash
curl -s localhost:8080/api/button
```

Die Ausgabe zeigt einen Zähler je Taster (`today`, `forward`, `back`). Bei jedem
kurzen Druck muss der passende um eins steigen. Bleibt einer stehen, prüfe die
Verdrahtung und `journalctl -u kalender -n 50` — beim Start wird für jeden
erkannten Taster eine Zeile wie `Taster 'forward' aktiv an GPIO27`
protokolliert. Kommt dort eine Meldung über fehlende Rechte, gehört der
Benutzer in die Gruppe `gpio` (`sudo usermod -aG gpio $USER`, danach neu
starten).

## Farbe eines einzelnen Termins

Normalerweise bekommt jeder Termin die Farbe seines Kalenders aus den
Einstellungen. Liefert die Quelle für einen Termin eine **eigene** Farbe mit,
wird diese verwendet. Maßgeblich ist die Eigenschaft `COLOR` aus RFC 7986; sie
darf einen Hex-Wert (`#3366ff`) oder einen CSS-Farbnamen (`tomato`) enthalten.
Alles andere wird verworfen — die Daten kommen von fremden Servern und landen
direkt in der Darstellung.

Die Rangfolge, wenn mehreres zutrifft:

1. eine **Hervorhebungsregel** (z. B. Geburtstage) — sie hat immer Vorrang,
   sonst wäre sie ja wirkungslos
2. die **Farbe des Termins** aus dem Kalender
3. die **eingestellte Farbe des Kalenders**

**Wichtig zu Google Kalender:** Dort lässt sich pro Termin eine Farbe wählen,
aber Google überträgt sie **nicht** im ICS-Export — der hält sich an RFC 5545,
das keine Farbe kennt, und die Erweiterung RFC 7986 setzt Google in seinen
Exporten nicht um. Für Google-Kalender bleibt es deshalb bei der eingestellten
Farbe; die App bekommt schlicht keine andere geliefert. Wer trotzdem einzelne
Termine hervorheben will, nutzt dafür die Hervorhebungsregeln weiter unten:
Sie greifen über Stichwörter im Titel und sind vom Anbieter unabhängig.

Anbieter, die `COLOR` mitliefern (etwa Nextcloud), funktionieren dagegen ohne
weiteres Zutun.

## Geburtstage und andere auffällige Termine

Geburtstage werden pink dargestellt und mit 🎂 gekennzeichnet, unabhängig davon,
aus welchem Kalender sie kommen. In der Ganztags-Zeile stehen sie immer an
erster Stelle, damit sie nicht unter „+N weitere" verschwinden. Voreingestellt
ist:

```yaml
highlights:
  - name: Geburtstage
    match: ["geburtstag", "birthday", "bday", "🎂"]
    color: "#ff4fa3"
    icon: "🎂"
```

`match` prüft den Termintitel (Groß-/Kleinschreibung egal) und trifft damit
sowohl „Anna hat Geburtstag" (Google-Kontakte, deutsch) als auch
„Anna's birthday". Führst du einen eigenen Geburtstagskalender, ist der
Kalendername der sicherere Weg – dann greift die Regel für jeden Termin darin,
auch ohne passendes Stichwort:

```yaml
highlights:
  - name: Geburtstage
    calendars: ["Geburtstage"]     # Name aus dem Abschnitt calendars
    color: "#ff4fa3"
    icon: "🎂"
```

Weitere Regeln lassen sich anhängen (Urlaub, Dienste, Termine der Kinder). Die
erste passende Regel gewinnt.

## Betrieb

```bash
systemctl status kalender          # läuft der Dienst?
journalctl -u kalender -f          # Protokoll mitlesen
curl -s localhost:8080/api/week    # Rohdaten prüfen
curl -X POST localhost:8080/api/refresh   # sofort neu laden, wartet aufs Ergebnis
```

Verhalten bei Störungen:

* **Internet weg** – die zuletzt geladenen Termine bleiben stehen, oben rechts
  erscheint „offline – Stand HH:MM“. Wiederholung alle 2 Minuten.
* **Stromausfall** – systemd startet den Dienst, die Sitzung den Kiosk neu.
* **Chromium stürzt ab** – `start-kiosk.sh` startet ihn nach 5 Sekunden neu.
* **Tageswechsel** – die Spalten rutschen automatisch weiter, um 04:00 lädt die
  Seite einmal komplett neu.

## Aktualisieren

Das Betriebssystem bleibt unangetastet, es werden nur die Programmdateien
ersetzt. **Erhalten bleiben** in jedem Fall `config.yaml` (deine Kalender und
Einstellungen), die Sicherung `config.yaml.bak` und der Zwischenspeicher.

### Mit Git (am bequemsten)

```bash
cd ~/kalender
git pull
bash update.sh
```

### Ohne Git, Dateien von Windows

Am Windows-Rechner das neue Projekt auf den Pi legen — in einen Zwischenordner,
damit nichts Bestehendes überschrieben wird:

```powershell
cd C:\Projekte
scp -r .\Kalender pi@192.168.1.50:/tmp/kalender-neu
```

Dann am Pi die Programmteile ersetzen. `config.yaml`, `.venv` und `cache`
werden dabei nicht angefasst:

```bash
rm -rf ~/kalender/app ~/kalender/kiosk ~/kalender/systemd ~/kalender/demo
cp -a /tmp/kalender-neu/{app,kiosk,systemd,demo} ~/kalender/
cp -a /tmp/kalender-neu/{*.sh,*.md,requirements.txt,config.example.yaml} ~/kalender/
rm -rf /tmp/kalender-neu
bash ~/kalender/update.sh
```

Statt `scp` geht genauso ein USB-Stick — Hauptsache, die neuen Dateien landen
zuerst in `/tmp/kalender-neu`.

### Was `update.sh` macht

Zeilenenden reparieren, Python-Bibliotheken abgleichen, **die `config.yaml`
gegenprüfen** (eine fehlerhafte Datei bricht ab, bevor der Dienst steht), Dienst
neu starten und melden, ob er wieder antwortet.

Die Anzeige muss dabei niemand anfassen: Der Dienst liefert eine Kennung des
Programmstands mit, und sobald die sich ändert, lädt sich die Seite innerhalb
einer Minute von selbst neu.

### Wann stattdessen `install.sh`?

Immer dann, wenn sich etwas am System ändert — neue Pakete, GPIO, sudo-Regel,
Autostart. `install.sh` lässt sich jederzeit gefahrlos erneut ausführen, deine
Konfiguration bleibt erhalten. Es dauert nur länger, weil es Systempakete prüft.
Im Zweifel ist `install.sh` die sichere Wahl.

Wurde `kiosk/start-kiosk.sh` geändert, ist zusätzlich ein `sudo reboot` nötig:
Diese Datei wird nur beim Start der Sitzung gelesen.

## Aus dem Vollbild heraus zum Desktop

Der Kiosk startet Chromium nach einem Absturz von selbst neu — sonst bliebe der
Bildschirm nach einer Störung schwarz. Ein bewusstes Schließen erkennt das
Skript aber und startet dann **nicht** neu. Vier Wege, je nachdem was du zur
Hand hast:

| Situation | Weg |
|---|---|
| Tastatur am Pi | **Alt+F4** schließt die Anzeige, du landest auf dem Desktop |
| Terminal offen oder per SSH | `~/kalender/kiosk/stop-kiosk.sh` |
| Nichts davon greift | **Strg+Alt+F2** wechselt auf eine Textkonsole, dort anmelden und `~/kalender/kiosk/stop-kiosk.sh` ausführen; mit **Strg+Alt+F1** zurück zur Oberfläche |
| Von einem anderen Rechner | Per SSH einloggen und dasselbe Skript ausführen |

Zurück zur Anzeige — ohne Neustart:

```bash
~/kalender/kiosk/start-kiosk.sh &
```

Oder einfach `sudo reboot`; nach dem Hochfahren ist der Kalender wieder im
Vollbild. Der Datendienst läuft die ganze Zeit weiter, du verlierst also keine
Termine und keine Einstellungen — es verschwindet nur die Anzeige.

Für reine Kalender-Einstellungen musst du das Vollbild übrigens gar nicht
verlassen: Das **Zahnrad** oben rechts (oder die Taste `E`) genügt.

## Bedienung im Ausnahmefall

Im Normalbetrieb wird nichts bedient. Wenn Maus oder Tastatur angesteckt sind:

* **Zahnrad oben rechts** oder Taste `E` öffnet die Einstellungen, `Esc` schließt.
* Während ein Alarm läutet, beendet ihn jede Taste; sie löst dabei nichts
  anderes aus (öffnet also nicht versehentlich die Einstellungen). Ohne
  Tastatur geht das mit dem Taster am GPIO, siehe oben.
* `Alt`+`F4` beendet die Anzeige und bringt dich auf den Desktop, siehe oben.
* Fernwartung per SSH: `sudo systemctl restart kalender`.

Der Dienst hört bewusst nur auf `127.0.0.1`, die Einstellungen sind also nur am
Gerät selbst erreichbar – die geheimen Kalender-URLs liegen sonst offen im
Netz. Willst du vom Handy aus konfigurieren, setze `server.host` in
`config.yaml` auf `0.0.0.0` und sichere den Zugang im Router ab.

## Entwicklung unter Windows

```powershell
cd C:\Projekte\Kalender
.\run.ps1
```

Legt Umgebung und `config.yaml` an und öffnet die Anzeige im Browser. In der
Vorlage ist der Demokalender `demo/demo.ics` eingetragen, damit sofort Termine
sichtbar sind.

## Deinstallation

```bash
sudo systemctl disable --now kalender
sudo rm /etc/systemd/system/kalender.service && sudo systemctl daemon-reload
rm -f ~/.config/autostart/kalender-kiosk.desktop
sed -i '/start-kiosk.sh/d' ~/.config/labwc/autostart
```

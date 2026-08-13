/* Einstellungsdialog hinter dem Zahnrad.
   Schreibt ueber /api/settings die config.yaml und uebernimmt sie sofort. */

const settingsEl = {
  overlay: document.getElementById("settings"),
  body: document.getElementById("settingsBody"),
  message: document.getElementById("settingsMessage"),
  gear: document.getElementById("gear"),
  close: document.getElementById("settingsClose"),
  cancel: document.getElementById("settingsCancel"),
  save: document.getElementById("settingsSave"),
};

const TIMEZONES = [
  "Europe/Vienna", "Europe/Berlin", "Europe/Zurich", "Europe/Rome",
  "Europe/Prague", "Europe/Budapest", "Europe/London", "UTC",
];

let form = null;   // Sammelfunktionen des aktuell aufgebauten Formulars

/* ---------- kleine DOM-Hilfen ---------- */

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child != null) node.append(child);
  return node;
}

function field(label, input, hint) {
  return h("label", { class: "field" },
    h("span", { class: "flabel", text: label }),
    input,
    hint ? h("span", { class: "fhint", text: hint }) : null);
}

function section(title, hint, ...content) {
  return h("section", { class: "sect" },
    h("h3", { text: title }),
    hint ? h("p", { class: "sect-hint", text: hint }) : null,
    ...content);
}

function numberInput(value, min, max, step = 1) {
  return h("input", { type: "number", value, min, max, step, class: "num" });
}

function hourSelect(value, min, max) {
  const select = h("select");
  for (let hour = min; hour <= max; hour += 1) {
    select.append(h("option", {
      value: hour,
      text: `${String(hour).padStart(2, "0")}:00`,
      selected: hour === Number(value),
    }));
  }
  return select;
}

function colorPicker(value, palette) {
  let current = (value || palette[0]).toLowerCase();
  const input = h("input", { type: "color", value: current, class: "colorinput" });
  const swatches = palette.map((color) => {
    const button = h("button", {
      type: "button", class: "swatch", title: color,
      onclick: () => { current = color.toLowerCase(); input.value = current; paint(); },
    });
    button.style.background = color;
    return button;
  });
  input.addEventListener("input", () => { current = input.value.toLowerCase(); paint(); });

  function paint() {
    swatches.forEach((node, index) =>
      node.classList.toggle("active", palette[index].toLowerCase() === current));
  }
  paint();

  const wrap = h("div", { class: "colors" }, ...swatches, input);
  wrap.collect = () => current;
  return wrap;
}

const splitList = (text) => text.split(",").map((part) => part.trim()).filter(Boolean);

/* ---------- Kalenderzeilen ---------- */

function calendarRow(calendar, palette) {
  if (calendar.editable === false) {
    return h("div", { class: "row locked" },
      h("div", { class: "locked-name", text: calendar.name }),
      h("div", { class: "locked-url", text: calendar.url }),
      h("div", { class: "fhint", text: "lokale Datei – nur direkt in config.yaml änderbar" }));
  }

  const name = h("input", { type: "text", value: calendar.name || "", placeholder: "z. B. Familie" });
  const url = h("input", {
    type: "text", class: "wide", value: calendar.url || "",
    placeholder: "https://calendar.google.com/…/basic.ics",
  });
  const exclude = h("input", {
    type: "text", value: (calendar.exclude || []).join(", "), placeholder: "optional, z. B. privat",
  });
  const color = colorPicker(calendar.color, palette);
  const result = h("span", { class: "test-result" });

  const test = h("button", {
    type: "button", class: "ghost", text: "Testen",
    onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      result.className = "test-result";
      result.textContent = "prüfe…";
      try {
        const response = await fetch("/api/settings/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url.value.trim() }),
        });
        const data = await response.json();
        result.classList.add(data.ok ? "good" : "bad");
        const count = data.count === 1 ? "1 Termin" : `${data.count} Termine`;
        result.textContent = data.ok
          ? `${count} in 30 Tagen${data.name ? ` – ${data.name}` : ""}`
          : `Fehler: ${data.error}`;
      } catch (err) {
        result.classList.add("bad");
        result.textContent = `Fehler: ${err}`;
      } finally {
        button.disabled = false;
      }
    },
  });

  const row = h("div", { class: "row" },
    h("div", { class: "row-grid" },
      field("Name", name),
      field("Farbe", color),
      field("ICS-Adresse", url),
      field("Titel ausblenden", exclude, "mehrere durch Komma trennen")),
    h("div", { class: "row-actions" },
      test, result,
      h("button", {
        type: "button", class: "ghost danger", text: "Entfernen",
        onclick: () => row.remove(),
      })));

  row.collect = () => ({
    name: name.value.trim(),
    url: url.value.trim(),
    color: color.collect(),
    exclude: splitList(exclude.value),
  });
  return row;
}

function highlightRow(rule, palette) {
  const name = h("input", { type: "text", value: rule.name || "", placeholder: "z. B. Geburtstage" });
  const match = h("input", {
    type: "text", class: "wide", value: (rule.match || []).join(", "),
    placeholder: "geburtstag, birthday",
  });
  const calendars = h("input", {
    type: "text", value: (rule.calendars || []).join(", "), placeholder: "optional: Kalendername",
  });
  const icon = h("input", { type: "text", value: rule.icon || "", placeholder: "🎂", class: "icon" });
  const color = colorPicker(rule.color, palette);

  const row = h("div", { class: "row" },
    h("div", { class: "row-grid" },
      field("Name", name),
      field("Farbe", color),
      field("Stichwörter im Titel", match, "mehrere durch Komma trennen"),
      field("Ganze Kalender", calendars),
      field("Symbol", icon)),
    h("div", { class: "row-actions" },
      h("button", {
        type: "button", class: "ghost danger", text: "Entfernen",
        onclick: () => row.remove(),
      })));

  row.collect = () => ({
    name: name.value.trim(),
    match: splitList(match.value),
    calendars: splitList(calendars.value),
    color: color.collect(),
    icon: icon.value.trim(),
  });
  return row;
}

/* ---------- Formular aufbauen ---------- */

function buildForm(data) {
  const palette = data.palette || ["#4f9cf9"];
  settingsEl.body.replaceChildren();

  // Kalender
  const calendarList = h("div", { class: "list" },
    ...data.calendars.map((calendar) => calendarRow(calendar, palette)));
  const addCalendar = h("button", {
    type: "button", class: "ghost add", text: "+ Kalender hinzufügen",
    onclick: () => {
      const used = calendarList.querySelectorAll(".row").length;
      calendarList.append(calendarRow({ color: palette[used % palette.length] }, palette));
    },
  });

  // Sofort neu abrufen, ohne aufs Intervall zu warten.
  const refreshResult = h("span", { class: "test-result" });
  const refreshNow = h("button", {
    type: "button", class: "ghost", text: "Jetzt aktualisieren",
    onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      refreshResult.className = "test-result";
      refreshResult.textContent = "wird geholt…";
      try {
        const response = await fetch("/api/refresh", { method: "POST" });
        const data = await response.json();
        const time = new Intl.DateTimeFormat("de-AT", {
          hour: "2-digit", minute: "2-digit", hour12: false,
        }).format(new Date());
        if (data.ok) {
          refreshResult.classList.add("good");
          refreshResult.textContent = `aktualisiert ${time}`;
        } else {
          refreshResult.classList.add("bad");
          const problems = (data.problems || [])
            .map((p) => `${p.calendar}: ${p.message}`).join(" · ");
          refreshResult.textContent = problems || "Abruf fehlgeschlagen";
        }
        await poll();     // Anzeige im Hintergrund gleich mitziehen
      } catch (err) {
        refreshResult.classList.add("bad");
        refreshResult.textContent = `Fehler: ${err}`;
      } finally {
        button.disabled = false;
      }
    },
  });

  // Hervorhebungen
  const highlightList = h("div", { class: "list" },
    ...data.highlights.map((rule) => highlightRow(rule, palette)));
  const addHighlight = h("button", {
    type: "button", class: "ghost add", text: "+ Hervorhebung hinzufügen",
    onclick: () => highlightList.append(highlightRow({ color: "#ff4fa3" }, palette)),
  });

  // Alarm
  const alarm = data.alarm;
  const alarmOn = h("input", { type: "checkbox", checked: alarm.enabled });
  const output = h("select", {},
    ...(data.outputs || []).map((entry) => h("option", {
      value: entry.id, text: entry.name, selected: entry.id === alarm.output,
    })));
  const sound = h("select", {},
    ...(data.sounds || []).map((entry) => h("option", {
      value: entry.id, text: entry.name, selected: entry.id === alarm.sound,
    })));
  const volume = h("input", {
    type: "range", min: 0, max: 1, step: 0.05, value: alarm.volume, class: "range",
  });
  const volumeLabel = h("span", { class: "fhint", text: `${Math.round(alarm.volume * 100)} %` });
  volume.addEventListener("input", () => {
    volumeLabel.textContent = `${Math.round(Number(volume.value) * 100)} %`;
  });
  const stopMode = h("select", {},
    h("option", { value: "auto", text: "nach fester Dauer", selected: alarm.stop_mode === "auto" }),
    h("option", { value: "key", text: "bei Tasteneingabe", selected: alarm.stop_mode === "key" }));
  const duration = numberInput(alarm.duration_seconds, 1, 120);
  const atStart = h("input", { type: "checkbox", checked: alarm.at_event_start });

  const durationField = field("Dauer (Sekunden)", duration, "gilt bei festem Ende");
  const syncStopMode = () => {
    const auto = stopMode.value === "auto";
    duration.disabled = !auto;
    durationField.classList.toggle("disabled", !auto);
  };
  stopMode.addEventListener("change", syncStopMode);
  syncStopMode();

  const preview = h("button", {
    type: "button", class: "ghost", text: "Ton anhören",
    onclick: async (event) => {
      setMessage("");
      if (output.value !== "buzzer") {
        const ok = previewSound(sound.value, Number(volume.value), 3);
        if (!ok) setMessage("Der Browser hat die Tonausgabe blockiert.", "bad");
        return;
      }
      // Beim Summer erzeugt der Dienst den Ton.
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const response = await fetch(
          `/api/alarm/test?sound=${encodeURIComponent(sound.value)}`, { method: "POST" });
        const result = await response.json();
        if (!result.ok) setMessage(`Summer: ${result.error}`, "bad");
      } catch (err) {
        setMessage(`Summer nicht erreichbar: ${err}`, "bad");
      } finally {
        button.disabled = false;
      }
    },
  });

  // Anzeige
  const days = numberInput(data.view.days, 1, 14);
  const theme = h("select", {},
    ...(data.themes || []).map((entry) => h("option", {
      value: entry.id, text: entry.name, selected: entry.id === data.view.theme,
    })));
  // Sofort umschalten, damit man die Wirkung vor dem Speichern sieht.
  theme.addEventListener("change", () => {
    document.documentElement.dataset.theme = theme.value;
  });
  const layout = h("select", {},
    h("option", { value: "timegrid", text: "Stundenraster", selected: data.view.layout === "timegrid" }),
    h("option", { value: "agenda", text: "Terminliste", selected: data.view.layout === "agenda" }));
  const fromHour = hourSelect(data.view.day_start_hour, 0, 23);
  const toHour = hourSelect(data.view.day_end_hour, 1, 24);
  const hourStep = numberInput(data.view.hour_step, 1, 6);
  const backToToday = numberInput(data.view.return_to_today_minutes, 0, 240);
  const showClock = h("input", { type: "checkbox", checked: data.view.show_clock });
  const showWeek = h("input", { type: "checkbox", checked: data.view.show_weeknumber });

  const dimOn = h("input", { type: "checkbox", checked: data.view.dim.enabled });
  const dimFrom = hourSelect(data.view.dim.start_hour, 0, 23);
  const dimTo = hourSelect(data.view.dim.end_hour, 0, 23);
  const dimLevel = numberInput(data.view.dim.brightness, 0.1, 1, 0.05);

  // Allgemein
  const zoneList = h("datalist", { id: "zonelist" },
    ...TIMEZONES.map((zone) => h("option", { value: zone })));
  const timezone = h("input", { type: "text", value: data.timezone, list: "zonelist" });
  const locale = h("input", { type: "text", value: data.locale });
  const interval = numberInput(data.refresh.interval_minutes, 1, 1440);
  const timeout = numberInput(data.refresh.timeout_seconds, 5, 120);

  // Programmstand
  const updateResult = h("div", { class: "test-result" });
  const updateButton = h("button", {
    type: "button", class: "ghost", text: "Nach Updates suchen",
    onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      updateResult.className = "test-result";
      updateResult.textContent = "sucht…";
      try {
        const response = await fetch("/api/update", { method: "POST" });
        const data = await response.json();
        if (!data.ok) {
          updateResult.classList.add("bad");
          updateResult.textContent = data.error;
        } else if (!data.updated) {
          updateResult.classList.add("good");
          updateResult.textContent = data.message;
        } else {
          updateResult.classList.add("good");
          updateResult.textContent =
            `${data.message} (${data.commits} Änderung${data.commits === 1 ? "" : "en"})`;
        }
      } catch (err) {
        updateResult.classList.add("bad");
        updateResult.textContent = `Fehler: ${err}`;
      } finally {
        button.disabled = false;
      }
    },
  });

  settingsEl.body.append(
    section("Kalender", "Die ICS-Adresse steht beim Anbieter unter „Kalender veröffentlichen“ oder „Geheime Adresse im iCal-Format“.",
      calendarList, addCalendar,
      h("div", { class: "row-actions" },
        refreshNow, refreshResult,
        h("span", { class: "fhint", text: "holt die gespeicherten Kalender sofort neu" }))),
    section("Hervorhebungen", "Termine, die auffallen sollen – unabhängig vom Kalender.",
      highlightList, addHighlight),
    section("Alarm",
      `Klingelt zur Erinnerung eines Termins. Im Modus „bei Tasteneingabe“ hört der Ton spätestens nach ${Math.round((data.alarm_hard_limit_seconds || 300) / 60)} Minuten von selbst auf.`,
      h("div", { class: "row-grid" },
        field("Aktiv", alarmOn),
        field("Ausgabe", output, "Summer klingelt auch bei dunklem Bildschirm"),
        field("Ton", sound),
        field("Lautstärke", h("div", { class: "colors" }, volume, volumeLabel)),
        field("Ende des Tons", stopMode),
        durationField,
        field("Auch bei Terminbeginn", atStart, "für Termine ohne eigene Erinnerung")),
      h("div", { class: "row-actions" }, preview)),
    section("Anzeige", null,
      h("div", { class: "row-grid" },
        field("Anzahl Tage", days, "heute plus die folgenden"),
        field("Farbschema", theme, "wirkt sofort zum Ausprobieren"),
        field("Darstellung", layout),
        field("Zeitfenster von", fromHour),
        field("Zeitfenster bis", toHour),
        field("Stundenlinie alle … Std.", hourStep),
        field("Zurück auf heute nach … Min.", backToToday, "0 = stehen lassen"),
        field("Uhr anzeigen", showClock),
        field("Kalenderwoche anzeigen", showWeek))),
    section("Nachtabsenkung", "Dunkelt den Bildschirm in den angegebenen Stunden ab.",
      h("div", { class: "row-grid" },
        field("Aktiv", dimOn),
        field("Ab", dimFrom),
        field("Bis", dimTo),
        field("Helligkeit", dimLevel, "0.1 bis 1.0"))),
    section("Allgemein", null,
      h("div", { class: "row-grid" },
        field("Zeitzone", timezone),
        field("Sprache", locale, "z. B. de-AT"),
        field("Aktualisierung alle … Min.", interval),
        field("Zeitlimit je Abruf (Sek.)", timeout)),
      zoneList),
    section("Programmstand",
      `Läuft gerade: ${current?.version || "unbekannt"}. Der Knopf holt einen neuen Stand aus dem Repository, prüft ihn und startet das Gerät danach neu. Läuft der neue Stand nicht, wird der bisherige wiederhergestellt und nicht neu gestartet.`,
      h("div", { class: "row-actions" }, updateButton, updateResult)),
  );

  form = () => ({
    timezone: timezone.value.trim(),
    locale: locale.value.trim(),
    alarm: {
      enabled: alarmOn.checked,
      output: output.value,
      sound: sound.value,
      volume: Number(volume.value),
      stop_mode: stopMode.value,
      duration_seconds: Number(duration.value),
      at_event_start: atStart.checked,
    },
    refresh: {
      interval_minutes: Number(interval.value),
      timeout_seconds: Number(timeout.value),
    },
    view: {
      days: Number(days.value),
      theme: theme.value,
      layout: layout.value,
      day_start_hour: Number(fromHour.value),
      day_end_hour: Number(toHour.value),
      hour_step: Number(hourStep.value),
      return_to_today_minutes: Number(backToToday.value),
      show_clock: showClock.checked,
      show_weeknumber: showWeek.checked,
      dim: {
        enabled: dimOn.checked,
        start_hour: Number(dimFrom.value),
        end_hour: Number(dimTo.value),
        brightness: Number(dimLevel.value),
      },
    },
    calendars: [...calendarList.querySelectorAll(".row")]
      .filter((row) => typeof row.collect === "function")
      .map((row) => row.collect()),
    highlights: [...highlightList.querySelectorAll(".row")].map((row) => row.collect()),
  });
}

/* ---------- oeffnen, speichern, schliessen ---------- */

/* Der Dialog schliesst sich nach einer Weile ohne Eingabe von selbst. Sonst
   bliebe das Geraet darin stehen, wenn ihn jemand versehentlich geoeffnet hat.
   Jede Eingabe setzt die Frist neu - auch ein Tastendruck am Geraet. */
let settingsTimer = null;

function settingsTouch() {
  clearTimeout(settingsTimer);
  settingsTimer = null;
  if (settingsEl.overlay.hidden) return;
  const sekunden = Number(current?.view?.settings_timeout_seconds || 0);
  if (sekunden > 0) settingsTimer = setTimeout(closeSettings, sekunden * 1000);
}

for (const typ of ["click", "keydown", "input", "change"]) {
  settingsEl.overlay.addEventListener(typ, settingsTouch, true);
}

function setMessage(text, kind) {
  settingsEl.message.textContent = text || "";
  settingsEl.message.className = "message" + (kind ? ` ${kind}` : "");
}

async function openSettings() {
  setMessage("");
  settingsEl.body.replaceChildren(h("p", { class: "sect-hint", text: "Einstellungen werden geladen…" }));
  settingsEl.overlay.hidden = false;
  document.body.classList.add("settings-open");
  try {
    const response = await fetch("/api/settings", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    buildForm(await response.json());
  } catch (err) {
    setMessage(`Einstellungen nicht ladbar: ${err}`, "bad");
  }
  settingsTouch();
}

function closeSettings() {
  clearTimeout(settingsTimer);
  settingsTimer = null;
  navReset();    // Tastenfokus und Bildschirmtastatur zuruecksetzen
  stopAlarm();   // eine laufende Tonprobe beenden
  // Eine nicht gespeicherte Farbschema-Vorschau wieder zuruecknehmen.
  document.documentElement.dataset.theme = current?.view?.theme || "dark";
  settingsEl.overlay.hidden = true;
  document.body.classList.remove("settings-open");
  form = null;
}

async function saveSettings() {
  if (!form) return;
  settingsEl.save.disabled = true;
  setMessage("wird gespeichert…");
  try {
    const payload = form();
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      setMessage(data.error || `HTTP ${response.status}`, "bad");
      return;
    }
    // Gespeichertes Schema gleich vermerken, sonst blinkt beim Schliessen
    // kurz das vorherige auf.
    if (current?.view) current.view.theme = payload.view.theme;
    closeSettings();
    lastRenderedSignature = "";   // Anzeige komplett neu aufbauen
    await poll();
  } catch (err) {
    setMessage(`Speichern fehlgeschlagen: ${err}`, "bad");
  } finally {
    settingsEl.save.disabled = false;
  }
}

settingsEl.gear.addEventListener("click", openSettings);
settingsEl.close.addEventListener("click", closeSettings);
settingsEl.cancel.addEventListener("click", closeSettings);
settingsEl.save.addEventListener("click", saveSettings);
settingsEl.overlay.addEventListener("click", (event) => {
  if (event.target === settingsEl.overlay) closeSettings();
});

document.addEventListener("keydown", (event) => {
  // Die Taste, die gerade einen Alarm beendet hat, soll nichts weiter ausloesen.
  if (Date.now() - (window.__alarmStoppedAt || 0) < 1000) return;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
  if (event.key === "Escape" && !settingsEl.overlay.hidden) closeSettings();
  else if ((event.key === "e" || event.key === "E") && settingsEl.overlay.hidden && !typing) {
    openSettings();
  }
});

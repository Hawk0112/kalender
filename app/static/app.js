/* Wochenansicht: holt /api/week und baut das Raster neu auf.
   Alles laeuft ohne Benutzereingabe - die Seite aktualisiert sich selbst. */

const POLL_MS = 60_000;
const MAX_ALLDAY_ROWS = 4;

const el = {
  board: document.getElementById("board"),
  range: document.getElementById("rangeLabel"),
  week: document.getElementById("weekLabel"),
  offset: document.getElementById("offsetBadge"),
  clock: document.getElementById("clock"),
  status: document.getElementById("status"),
  statusText: document.getElementById("statusText"),
  splash: document.getElementById("splash"),
};

let current = null;        // zuletzt erfolgreich geladene Daten
let lastFetchOk = true;
let lastRenderedSignature = "";
let weekOffset = 0;        // angezeigte Woche, 0 = die aktuelle
let runningVersion = null; // Programmstand, mit dem diese Seite geladen wurde

/* ---------- Zeit-Hilfen (immer in der Kalender-Zeitzone) ---------- */

function nowInZone(timeZone) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date());
  const get = (type) => Number(parts.find((p) => p.type === type).value);
  return {
    year: get("year"), month: get("month"), day: get("day"),
    hour: get("hour") % 24, minute: get("minute"), second: get("second"),
  };
}

/** Wanduhrzeit aus einem ISO-String mit Offset lesen (ohne Zeitzonenumrechnung). */
function wallMinutes(iso) {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? Number(m[1]) * 60 + Number(m[2]) : 0;
}

function hhmm(iso) {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : "";
}

function dateFromISODate(value) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

/* ---------- Datenabruf ---------- */

async function poll() {
  try {
    const response = await fetch(`/api/week?offset=${weekOffset * 7}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    // Nach einem Update liefert der Dienst eine neue Kennung: dann die Seite
    // einmal frisch laden, damit die neue Oberfläche erscheint.
    if (data.version) {
      if (runningVersion === null) runningVersion = data.version;
      else if (runningVersion !== data.version) { location.reload(); return; }
    }
    current = data;
    // Der Dienst begrenzt die Verschiebung - danach richten.
    weekOffset = Math.round((current.offset_days || 0) / 7);
    lastFetchOk = true;
  } catch (err) {
    lastFetchOk = false;
    console.warn("Abruf fehlgeschlagen:", err);
  }
  if (current) {
    render(current);
    updateAlarms(current);
    el.splash.classList.add("hidden");
  }
}

/* ---------- Blättern ---------- */

let returnTimer = null;

/** Nach einer Weile ohne Tastendruck von selbst zurück auf die aktuelle Woche.
    Der regelmäßige Abruf setzt die Frist bewusst nicht zurück - sonst käme die
    Anzeige nie von allein zurück. */
function armReturnToToday(target) {
  clearTimeout(returnTimer);
  returnTimer = null;
  if (target === 0) return;
  const minutes = Number(current?.view?.return_to_today_minutes || 0);
  if (minutes > 0) {
    returnTimer = setTimeout(goToday, minutes * 60_000);
  }
}

function showWeek(offset) {
  const wanted = Math.max(-52, Math.min(52, Math.round(offset)));
  armReturnToToday(wanted);        // auch nachziehen, wenn sich nichts ändert
  if (wanted === weekOffset) return;
  weekOffset = wanted;
  poll();
}

function shiftWeeks(step) {
  showWeek(weekOffset + step);
}

function goToday() {
  showWeek(0);
}

function isCurrentWeek() {
  return weekOffset === 0;
}

/* ---------- Aufbau ---------- */

function render(data) {
  const locale = data.locale || "de-AT";
  const signature = JSON.stringify([data.days, data.view.range, data.view.layout]);
  if (signature !== lastRenderedSignature) {
    lastRenderedSignature = signature;
    buildBoard(data, locale);
  }
  updateHeader(data, locale);
  updateStatus(data);
  updateNowLine(data);
  applyDimming(data);
}

function buildBoard(data, locale) {
  const days = data.days;
  const view = data.view;
  const board = el.board;
  board.dataset.layout = view.layout;
  board.style.setProperty("--days", days.length);
  board.replaceChildren();

  // Auf schmalen Spalten kurze Wochentagsnamen, damit nichts abgeschnitten wird.
  const columnWidth = (window.innerWidth - 90) / days.length;
  board.classList.toggle("compact", columnWidth < 150);
  const weekdayFmt = new Intl.DateTimeFormat(locale, {
    weekday: columnWidth < 150 ? "short" : "long",
    timeZone: "UTC",
  });
  const monthFmt = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" });

  const heads = days.map((day) => {
    const date = dateFromISODate(day.date);
    const head = document.createElement("div");
    head.className = "dayhead cell";
    if (day.is_today) head.classList.add("today");
    if (day.is_weekend) head.classList.add("weekend");
    head.innerHTML =
      `<span class="dnum">${date.getUTCDate()}</span>` +
      `<span class="dname">${weekdayFmt.format(date)}</span>` +
      `<span class="dmon">${monthFmt.format(date)}</span>`;
    return head;
  });

  if (view.layout === "agenda") {
    board.append(...heads);
    days.forEach((day) => board.append(buildAgenda(day)));
    return;
  }

  const rowsNeeded = Math.min(
    MAX_ALLDAY_ROWS,
    Math.max(1, ...days.map((d) => d.all_day.length)),
  );
  board.style.setProperty("--allday-rows", rowsNeeded);

  const corner = document.createElement("div");
  corner.className = "corner";
  board.append(corner, ...heads);

  const gutterAllDay = document.createElement("div");
  gutterAllDay.className = "gutter-allday";
  gutterAllDay.textContent = "ganztags";
  board.append(gutterAllDay);
  days.forEach((day) => board.append(buildAllDay(day, rowsNeeded)));

  // Sammelzeilen nur aufbauen, wenn es dort auch etwas zu zeigen gibt.
  const hasEarly = days.some((day) => day.early.length);
  const hasLate = days.some((day) => day.late.length);
  board.classList.toggle("has-early", hasEarly);
  board.classList.toggle("has-late", hasLate);

  if (hasEarly) {
    board.append(edgeLabel(`vor ${hourLabel(view.range.start_hour)}`, "early"));
    days.forEach((day) => board.append(buildEdge(day, day.early, "early")));
  }

  board.append(buildHours(view.range, view.hour_step || 1));
  days.forEach((day) => board.append(buildDayBody(day, view.range)));

  if (hasLate) {
    board.append(edgeLabel(`nach ${hourLabel(view.range.end_hour)}`, "late"));
    days.forEach((day) => board.append(buildEdge(day, day.late, "late")));
  }
}

const hourLabel = (hour) => `${String(hour).padStart(2, "0")}:00`;

function edgeLabel(text, kind) {
  const node = document.createElement("div");
  node.className = `gutter-edge ${kind}`;
  node.textContent = text;
  return node;
}

/** Sammelbereich fuer Termine ausserhalb des Stundenrasters. */
function buildEdge(day, entries, kind) {
  const box = document.createElement("div");
  box.className = `edge ${kind} cell`;
  if (day.is_today) box.classList.add("today");
  if (day.is_weekend) box.classList.add("weekend");

  for (const event of entries) {
    const chip = document.createElement("div");
    chip.className = "chip time" + (event.past ? " past" : "") + (event.highlight ? " highlight" : "");
    chip.style.setProperty("--c", event.color);
    chip.title = `${hhmm(event.start)}–${hhmm(event.end)} ${event.title}`;

    const time = document.createElement("span");
    time.className = "chip-time";
    time.textContent = hhmm(event.start);
    chip.append(time);
    if (event.icon) {
      const icon = document.createElement("span");
      icon.className = "eicon";
      icon.textContent = event.icon;
      chip.append(icon);
    }
    chip.append(document.createTextNode(event.title));
    box.append(chip);
  }
  return box;
}

function buildAllDay(day, rowsNeeded) {
  const box = document.createElement("div");
  box.className = "allday cell";
  if (day.is_today) box.classList.add("today");
  if (day.is_weekend) box.classList.add("weekend");

  const visible = day.all_day.slice(0, rowsNeeded);
  const hidden = day.all_day.length - visible.length;

  visible.forEach((event) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (event.past ? " past" : "") + (event.highlight ? " highlight" : "");
    chip.style.setProperty("--c", event.color);
    chip.title = event.title;
    const arrowLeft = event.continues_before ? "‹ " : "";
    const arrowRight = event.continues_after ? " ›" : "";
    if (event.icon) {
      const icon = document.createElement("span");
      icon.className = "eicon";
      icon.textContent = event.icon;
      chip.append(icon);
    }
    chip.append(document.createTextNode(`${arrowLeft}${event.title}${arrowRight}`));
    box.append(chip);
  });

  if (hidden > 0) {
    const more = document.createElement("div");
    more.className = "more";
    more.textContent = `+${hidden} weitere`;
    box.append(more);
  }
  return box;
}

function buildHours(range, step) {
  const hours = document.createElement("div");
  hours.className = "hours";
  const total = (range.end_hour - range.start_hour) * 60;
  for (let h = range.start_hour; h <= range.end_hour; h += step) {
    const label = document.createElement("div");
    label.className = "hlabel";
    label.style.top = `${((h - range.start_hour) * 60 / total) * 100}%`;
    // Erste und letzte Beschriftung nach innen ruecken, sonst ragen sie heraus.
    if (h === range.start_hour) label.style.transform = "translateY(0)";
    else if (h >= range.end_hour) label.style.transform = "translateY(-100%)";
    label.textContent = `${String(h).padStart(2, "0")}:00`;
    hours.append(label);
  }
  return hours;
}

function buildDayBody(day, range) {
  const body = document.createElement("div");
  body.className = "daybody cell";
  body.dataset.date = day.date;
  if (day.is_today) body.classList.add("today");
  if (day.is_weekend) body.classList.add("weekend");

  const total = (range.end_hour - range.start_hour) * 60;
  for (let h = range.start_hour + 1; h < range.end_hour; h += 1) {
    const line = document.createElement("div");
    line.className = "hline";
    line.style.top = `${((h - range.start_hour) * 60 / total) * 100}%`;
    body.append(line);
  }

  for (const item of layoutOverlaps(day.timed)) {
    body.append(buildEvent(item, range, total));
  }
  return body;
}

function buildEvent(item, range, total) {
  const event = item.event;
  const offset = range.start_hour * 60;
  // Auf das sichtbare Zeitfenster zuschneiden - ein Termin von 05:00 bis 07:00
  // beginnt sonst optisch zu weit oben und wird zu hoch.
  const visibleStart = Math.max(item.start, offset);
  const visibleEnd = Math.min(item.end, offset + total);
  const top = ((visibleStart - offset) / total) * 100;
  const height = ((visibleEnd - visibleStart) / total) * 100;
  const width = 100 / item.columns;

  const node = document.createElement("div");
  node.className = "event";
  if (event.past) node.classList.add("past");
  if (event.running) node.classList.add("running");
  if (event.highlight) node.classList.add("highlight");
  if (item.start < offset) node.classList.add("cut-top");
  if (item.end > offset + total) node.classList.add("cut-bottom");
  if (visibleEnd - visibleStart <= 45) node.classList.add("short");
  node.style.setProperty("--c", event.color);
  node.style.top = `${Math.max(0, top)}%`;
  node.style.height = `${Math.max(0.8, Math.min(100 - Math.max(0, top), height))}%`;
  node.style.left = `calc(${item.column * width}% + 2px)`;
  node.style.width = `calc(${width}% - 4px)`;
  node.title = `${event.title} (${event.calendar})`;

  const time = document.createElement("div");
  time.className = "etime";
  time.textContent = event.continues_before
    ? `… ${hhmm(event.end)}`
    : hhmm(event.start);

  const title = document.createElement("div");
  title.className = "etitle";
  title.textContent = (event.icon ? `${event.icon} ` : "") + event.title;

  node.append(time, title);

  if (event.location && height > 8 && item.columns === 1) {
    const loc = document.createElement("div");
    loc.className = "eloc";
    loc.textContent = event.location;
    node.append(loc);
  }
  return node;
}

function buildAgenda(day) {
  const box = document.createElement("div");
  box.className = "agenda cell";
  if (day.is_today) box.classList.add("today");
  if (day.is_weekend) box.classList.add("weekend");

  // Reihenfolge ergibt sich aus den Sammelbereichen: frueh, Raster, spaet.
  const all = [...day.all_day, ...day.early, ...day.timed, ...day.late];
  if (!all.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "keine Termine";
    box.append(empty);
    return box;
  }

  for (const event of all) {
    const item = document.createElement("div");
    item.className = "item" + (event.past ? " past" : "") + (event.highlight ? " highlight" : "");
    item.style.setProperty("--c", event.color);
    const time = document.createElement("div");
    time.className = "etime";
    time.textContent = event.all_day ? "ganztags" : `${hhmm(event.start)}–${hhmm(event.end)}`;
    const title = document.createElement("div");
    title.className = "etitle";
    title.textContent = (event.icon ? `${event.icon} ` : "") + event.title;
    item.append(time, title);
    box.append(item);
  }
  return box;
}

/** Ueberlappende Termine nebeneinander anordnen. */
function layoutOverlaps(events) {
  const items = events.map((event) => ({
    event,
    start: wallMinutes(event.start),
    end: Math.max(wallMinutes(event.start) + 15, wallMinutes(event.end) || 1440),
  }));
  items.sort((a, b) => a.start - b.start || b.end - a.end);

  const result = [];
  let cluster = [];
  let clusterEnd = -1;

  const flush = () => {
    if (!cluster.length) return;
    const columnEnds = [];
    for (const item of cluster) {
      let index = columnEnds.findIndex((end) => end <= item.start);
      if (index === -1) {
        index = columnEnds.length;
        columnEnds.push(item.end);
      } else {
        columnEnds[index] = item.end;
      }
      item.column = index;
    }
    cluster.forEach((item) => { item.columns = columnEnds.length; });
    result.push(...cluster);
    cluster = [];
    clusterEnd = -1;
  };

  for (const item of items) {
    if (cluster.length && item.start >= clusterEnd) flush();
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.end);
  }
  flush();
  return result;
}

/* ---------- Kopfzeile, Status, Jetzt-Linie ---------- */

function updateHeader(data, locale) {
  const days = data.days;
  const first = dateFromISODate(days[0].date);
  const last = dateFromISODate(days[days.length - 1].date);
  const sameMonth = first.getUTCMonth() === last.getUTCMonth();
  const dayFmt = new Intl.DateTimeFormat(locale, { day: "numeric", timeZone: "UTC" });
  const longFmt = new Intl.DateTimeFormat(locale, {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
  el.range.textContent = sameMonth
    ? `${dayFmt.format(first)}. – ${longFmt.format(last)}`
    : `${new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", timeZone: "UTC" }).format(first)} – ${longFmt.format(last)}`;

  el.week.textContent = data.view.show_weeknumber
    ? `KW ${days[0].week}${days[0].week !== days[days.length - 1].week ? `/${days[days.length - 1].week}` : ""}`
    : "";

  // Deutlich machen, wenn nicht die aktuelle Woche zu sehen ist - sonst
  // wundert man sich, warum heute nicht ganz links steht.
  const offset = Math.round((data.offset_days || 0) / 7);
  el.offset.hidden = offset === 0;
  if (offset !== 0) {
    const amount = Math.abs(offset) === 1 ? "1 Woche" : `${Math.abs(offset)} Wochen`;
    el.offset.textContent = offset > 0 ? `${amount} voraus` : `${amount} zurück`;
  }
}

function tickClock() {
  if (!current || !current.view.show_clock) return;
  const now = nowInZone(current.timezone);
  el.clock.textContent =
    `${String(now.hour).padStart(2, "0")}:${String(now.minute).padStart(2, "0")}`;
}

function updateStatus(data) {
  const status = data.status;
  let state = "ok";
  let text = "aktuell";

  if (!lastFetchOk) {
    state = "error";
    text = "keine Verbindung zum Dienst";
  } else if (!status.online && status.last_success) {
    state = status.stale ? "error" : "stale";
    text = `offline – Stand ${hhmm(status.last_success) || "unbekannt"}`;
  } else if (status.stale) {
    state = "stale";
    text = "Daten veraltet";
  } else if (status.last_success) {
    const time = new Intl.DateTimeFormat("de-AT", {
      hour: "2-digit", minute: "2-digit", hour12: false, timeZone: data.timezone,
    }).format(new Date(status.last_success));
    text = `aktualisiert ${time}`;
  }

  el.status.dataset.state = state;
  el.statusText.textContent = text;
  el.status.title = (status.problems || []).map((p) => `${p.calendar}: ${p.message}`).join("\n");
}

function updateNowLine(data) {
  document.querySelectorAll(".nowline").forEach((node) => node.remove());
  const today = data.days.find((day) => day.is_today);
  if (!today || data.view.layout !== "timegrid") return;

  const body = el.board.querySelector(`.daybody[data-date="${today.date}"]`);
  if (!body) return;

  const range = data.view.range;
  const now = nowInZone(data.timezone);
  const minutes = now.hour * 60 + now.minute;
  const total = (range.end_hour - range.start_hour) * 60;
  const position = ((minutes - range.start_hour * 60) / total) * 100;
  if (position < 0 || position > 100) return;

  const line = document.createElement("div");
  line.className = "nowline";
  line.style.top = `${position}%`;
  body.append(line);
}

function applyDimming(data) {
  const dim = data.view.dim || {};
  if (!dim.enabled) {
    document.documentElement.style.setProperty("--dim", "1");
    return;
  }
  const hour = nowInZone(data.timezone).hour;
  const start = Number(dim.start_hour);
  const end = Number(dim.end_hour);
  const night = start <= end ? hour >= start && hour < end : hour >= start || hour < end;
  document.documentElement.style.setProperty(
    "--dim", night ? String(dim.brightness ?? 0.55) : "1",
  );
}

/* ---------- Takt ---------- */

const startedAt = Date.now();

function heartbeat() {
  tickClock();
  if (current) {
    updateNowLine(current);
    applyDimming(current);
  }
  // Einmal pro Nacht neu laden, damit der Kiosk-Browser aufgeraeumt startet.
  const uptimeHours = (Date.now() - startedAt) / 3_600_000;
  if (uptimeHours > 20 && current) {
    const now = nowInZone(current.timezone);
    if (now.hour === 4 && now.minute === 0) location.reload();
  }
}

window.addEventListener("resize", () => {
  lastRenderedSignature = "";
  if (current) render(current);
});

poll();
setInterval(poll, POLL_MS);
setInterval(heartbeat, 10_000);
tickClock();

/* Bedienung der Einstellungen mit nur drei Tastern.

   Taster 2 und 3 wandern von einem Bedienelement zum naechsten, Taster 1
   aktiviert es. Bei Zahlen und Auswahlfeldern schaltet Taster 1 in einen
   Aenderungsmodus, in dem 2 und 3 den Wert verstellen. Bei Textfeldern
   erscheint eine Bildschirmtastatur.

   Maus und Tastatur bleiben unberuehrt - dieser Teil kommt nur zum Zug, wenn
   die Taster benutzt werden. */

let navIndex = -1;
let navMode = "browse";      // browse | edit | keypad
let navTarget = null;        // Feld, das die Bildschirmtastatur gerade fuellt

/* ---------- Bedienelemente einsammeln ---------- */

function navItems() {
  if (settingsEl.overlay.hidden) return [];
  const auswahl = settingsEl.overlay.querySelectorAll(
    'input:not([type="color"]):not([disabled]), select:not([disabled]), button:not([disabled])',
  );
  return [...auswahl].filter((el) => el.offsetParent !== null);
}

function navShow(index) {
  const items = navItems();
  if (!items.length) return;
  navIndex = ((index % items.length) + items.length) % items.length;
  items.forEach((el) => el.classList.remove("nav-active", "nav-edit"));
  const aktiv = items[navIndex];
  aktiv.classList.add("nav-active");
  if (navMode === "edit") aktiv.classList.add("nav-edit");
  aktiv.scrollIntoView({ block: "nearest" });
}

function navStart() {
  navMode = "browse";
  // Nicht auf dem Schliessen-Kreuz beginnen - ein versehentlicher Druck auf
  // Taster 1 wuerde die Einstellungen sonst sofort wieder zumachen.
  const items = navItems();
  const erstesFeld = items.findIndex((el) => settingsEl.body.contains(el));
  navShow(erstesFeld >= 0 ? erstesFeld : 0);
}

function navClear() {
  // Ueber den ganzen Dialog raeumen, nicht nur ueber die sichtbaren Elemente -
  // sonst bleibt die Markierung auf einer verborgenen Taste zurueck.
  settingsEl.overlay
    .querySelectorAll(".nav-active, .nav-edit, .group-open")
    .forEach((el) => el.classList.remove("nav-active", "nav-edit", "group-open"));
  navIndex = -1;
  navMode = "browse";
}

/* ---------- Werte verstellen ---------- */

function navStep(el, richtung) {
  if (el.tagName === "SELECT") {
    const n = el.options.length;
    el.selectedIndex = (el.selectedIndex + richtung + n) % n;
  } else {
    const schritt = Number(el.step) || 1;
    const wert = Number(el.value) + richtung * schritt;
    const min = el.min === "" ? -Infinity : Number(el.min);
    const max = el.max === "" ? Infinity : Number(el.max);
    // Auf drei Nachkommastellen runden, sonst entstehen Werte wie 0.30000000004
    el.value = Math.round(Math.min(max, Math.max(min, wert)) * 1000) / 1000;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function navActivate() {
  const el = navItems()[navIndex];
  if (!el) return;

  if (el.tagName === "BUTTON") { el.click(); return; }
  if (el.type === "checkbox") {
    el.checked = !el.checked;
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  if (el.tagName === "SELECT" || el.type === "number" || el.type === "range") {
    navMode = navMode === "edit" ? "browse" : "edit";
    navShow(navIndex);
    return;
  }
  if (el.tagName === "INPUT") { keypadOpen(el); return; }
}

/* ---------- Bildschirmtastatur ---------- */

/* Zweistufig: erst eine Gruppe waehlen, dann darin ein Zeichen. Statt bis zu
   62 Schritten sind es so hoechstens rund 16 je Zeichen. */

const zeichen = (text) => text.split("").map((z) => ({ label: z, type: "char", wert: z }));

// Ganze Textbausteine - eine Google-Adresse besteht zur Haelfte daraus.
const KEYPAD_SNIPPETS = [
  "https://",
  "calendar.google.com/calendar/ical/",
  "%40group.calendar.google.com",
  "%40gmail.com",
  "/private-",
  "/public/basic.ics",
  "/basic.ics",
  ".ics",
  "webcal://",
].map((text) => ({ label: text, type: "char", wert: text, klasse: "snippet" }));

const KEYPAD_GROUPS = [
  { label: "a–i", keys: zeichen("abcdefghi") },
  { label: "j–r", keys: zeichen("jklmnopqr") },
  { label: "s–z", keys: zeichen("stuvwxyz") },
  { label: "0–9", keys: zeichen("0123456789") },
  { label: "ABC", keys: zeichen("ABCDEFGHIJKLMNOPQRSTUVWXYZ") },
  { label: "äöü", keys: zeichen("äöüßÄÖÜ") },
  { label: ".:/", keys: zeichen(":/.-_%#?&=@+,!()") },
  { label: "Bausteine", keys: KEYPAD_SNIPPETS },
  {
    label: "Befehle",
    keys: [
      { label: "Leerzeichen", type: "char", wert: " ", klasse: "wide" },
      { label: "⌫ Zeichen löschen", type: "back", klasse: "wide" },
      { label: "Alles leeren", type: "clear", klasse: "wide" },
      { label: "Abbruch", type: "cancel", klasse: "wide danger" },
      { label: "Fertig", type: "done", klasse: "wide primary" },
    ],
  },
];

let keypadLevel = "group";     // group | keys
let keypadGroup = 0;
let keypadIndex = 0;
let keypadGroupNodes = [];
let keypadKeys = [];

function keypadBuildGroups() {
  const el = document.getElementById("keypadGroups");
  el.replaceChildren();
  keypadGroupNodes = KEYPAD_GROUPS.map((gruppe, i) => {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "key group";
    node.textContent = gruppe.label;
    node.addEventListener("click", () => keypadEnterGroup(i));
    el.append(node);
    return node;
  });
}

function keypadBuildKeys() {
  const el = document.getElementById("keypadKeys");
  el.replaceChildren();
  keypadKeys = [];

  const add = (eintrag) => {
    const node = document.createElement("button");
    node.type = "button";
    node.className = `key ${eintrag.klasse || ""}`.trim();
    node.textContent = eintrag.label;
    node.addEventListener("click", () => keypadPress(eintrag));
    el.append(node);
    keypadKeys.push({ node, eintrag });
  };

  KEYPAD_GROUPS[keypadGroup].keys.forEach(add);
  // Ganz am Ende, damit ein Schritt zurueck vom ersten Zeichen hierher fuehrt.
  add({ label: "◀ Gruppen", type: "groups", klasse: "wide" });
}

function keypadShow(index) {
  const nodes = keypadLevel === "group"
    ? keypadGroupNodes
    : keypadKeys.map((k) => k.node);
  if (!nodes.length) return;
  keypadIndex = ((index % nodes.length) + nodes.length) % nodes.length;
  [...keypadGroupNodes, ...keypadKeys.map((k) => k.node)]
    .forEach((n) => n.classList.remove("nav-active"));
  keypadGroupNodes.forEach((n, i) =>
    n.classList.toggle("group-open", keypadLevel === "keys" && i === keypadGroup));
  const aktiv = nodes[keypadIndex];
  aktiv.classList.add("nav-active");
  aktiv.scrollIntoView({ block: "nearest" });
}

function keypadEnterGroup(index) {
  keypadGroup = ((index % KEYPAD_GROUPS.length) + KEYPAD_GROUPS.length) % KEYPAD_GROUPS.length;
  keypadLevel = "keys";
  keypadBuildKeys();
  keypadShow(0);
}

function keypadToGroups() {
  keypadLevel = "group";
  document.getElementById("keypadKeys").replaceChildren();
  keypadKeys = [];
  keypadShow(keypadGroup);
}

function keypadRefresh() {
  document.getElementById("keypadValue").textContent = navTarget ? navTarget.value : "";
}

function keypadOpen(input) {
  navTarget = input;
  // Ausgangswert merken, damit "Abbruch" ihn zurueckholen kann.
  input.dataset.navBefore = input.value;
  navMode = "keypad";
  keypadLevel = "group";
  keypadGroup = 0;
  document.getElementById("keypadLabel").textContent =
    input.closest(".field")?.querySelector(".flabel")?.textContent || "Eingabe";
  document.getElementById("keypad").hidden = false;
  keypadBuildGroups();
  document.getElementById("keypadKeys").replaceChildren();
  keypadKeys = [];
  keypadShow(0);
  keypadRefresh();
}

function keypadClose() {
  document.getElementById("keypad").hidden = true;
  navTarget = null;
  navMode = "browse";
  navShow(navIndex);
}

function keypadPress(eintrag) {
  if (!navTarget) return;
  switch (eintrag.type) {
    case "char":
      navTarget.value += eintrag.wert;
      break;
    case "back":
      navTarget.value = navTarget.value.slice(0, -1);
      break;
    case "clear":
      navTarget.value = "";
      break;
    case "groups":
      keypadToGroups();
      return;
    case "cancel":
      navTarget.value = navTarget.dataset.navBefore ?? navTarget.value;
      keypadClose();
      return;
    case "done":
      navTarget.dispatchEvent(new Event("change", { bubbles: true }));
      keypadClose();
      return;
  }
  navTarget.dispatchEvent(new Event("input", { bubbles: true }));
  keypadRefresh();
}

/* ---------- Anschluss an die Taster ---------- */

/** Wird von buttons.js aufgerufen, wenn die Einstellungen offen sind. */
function navHandle(action, schritte) {
  settingsTouch();     // jeder Tastendruck verlaengert die Frist des Dialogs
  if (action === "today") {
    if (navMode !== "keypad") navActivate();
    else if (keypadLevel === "group") keypadEnterGroup(keypadIndex);
    else keypadPress(keypadKeys[keypadIndex].eintrag);
    return;
  }
  if (!schritte) return;

  if (navMode === "keypad") keypadShow(keypadIndex + schritte);
  else if (navMode === "edit") navStep(navItems()[navIndex], schritte);
  else navShow(navIndex + schritte);
}

/** Beim Schliessen der Einstellungen aufraeumen. */
function navReset() {
  if (!document.getElementById("keypad").hidden) {
    document.getElementById("keypad").hidden = true;
  }
  navTarget = null;
  navClear();
}

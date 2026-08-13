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
    .querySelectorAll(".nav-active, .nav-edit")
    .forEach((el) => el.classList.remove("nav-active", "nav-edit"));
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

const KEYPAD_LOWER = "abcdefghijklmnopqrstuvwxyz".split("");
const KEYPAD_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
// Ziffern und die Zeichen, die in Adressen und Namen vorkommen.
const KEYPAD_DIGITS = "0123456789".split("");
const KEYPAD_SYMBOLS = [
  ":", "/", ".", "-", "_", "%", "#", "?", "&", "=", "@", "+", ",", "!", "(", ")",
  "ä", "ö", "ü", "ß",
];

let keypadKeys = [];
let keypadIndex = 0;
let keypadUpper = false;

function keypadBuild() {
  const el = document.getElementById("keypadKeys");
  el.replaceChildren();
  keypadKeys = [];

  const add = (label, action, klasse = "") => {
    const taste = document.createElement("button");
    taste.type = "button";
    taste.className = `key ${klasse}`.trim();
    taste.textContent = label;
    taste.addEventListener("click", () => keypadPress(action));
    el.append(taste);
    keypadKeys.push({ node: taste, action });
  };

  (keypadUpper ? KEYPAD_UPPER : KEYPAD_LOWER).forEach((z) => add(z, { type: "char", z }));
  KEYPAD_DIGITS.forEach((z) => add(z, { type: "char", z }));
  KEYPAD_SYMBOLS.forEach((z) => {
    add(keypadUpper ? z.toUpperCase() : z, { type: "char", z: keypadUpper ? z.toUpperCase() : z });
  });
  add(keypadUpper ? "abc" : "ABC", { type: "case" }, "wide");
  add("Leer", { type: "char", z: " " }, "wide");
  add("⌫", { type: "back" }, "wide");
  add("Leeren", { type: "clear" }, "wide");
  add("Abbruch", { type: "cancel" }, "wide danger");
  add("Fertig", { type: "done" }, "wide primary");

  keypadShow(Math.min(keypadIndex, keypadKeys.length - 1));
}

function keypadShow(index) {
  if (!keypadKeys.length) return;
  keypadIndex = ((index % keypadKeys.length) + keypadKeys.length) % keypadKeys.length;
  keypadKeys.forEach((k) => k.node.classList.remove("nav-active"));
  const aktiv = keypadKeys[keypadIndex].node;
  aktiv.classList.add("nav-active");
  aktiv.scrollIntoView({ block: "nearest" });
}

function keypadRefresh() {
  document.getElementById("keypadValue").textContent = navTarget ? navTarget.value : "";
}

function keypadOpen(input) {
  navTarget = input;
  // Ausgangswert merken, damit "Abbruch" ihn zurueckholen kann.
  input.dataset.navBefore = input.value;
  navMode = "keypad";
  keypadUpper = false;
  keypadIndex = 0;
  document.getElementById("keypadLabel").textContent =
    input.closest(".field")?.querySelector(".flabel")?.textContent || "Eingabe";
  document.getElementById("keypad").hidden = false;
  keypadBuild();
  keypadRefresh();
}

function keypadClose() {
  document.getElementById("keypad").hidden = true;
  navTarget = null;
  navMode = "browse";
  navShow(navIndex);
}

function keypadPress(action) {
  if (!navTarget) return;
  switch (action.type) {
    case "char":
      navTarget.value += action.z;
      break;
    case "back":
      navTarget.value = navTarget.value.slice(0, -1);
      break;
    case "clear":
      navTarget.value = "";
      break;
    case "case":
      keypadUpper = !keypadUpper;
      keypadBuild();
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
  if (action === "today") {
    if (navMode === "keypad") keypadPress(keypadKeys[keypadIndex].action);
    else navActivate();
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

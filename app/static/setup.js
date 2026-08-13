/* Einrichtung per Handy: zeigt einen QR-Code auf dem Kalender.

   Wer ihn scannt, landet unmittelbar auf der Einstellungsseite und kann die
   Kalenderadresse dort mit einer richtigen Tastatur eingeben. Der Zugang gilt
   nur, solange dieser Modus laeuft. */

const setupEl = {
  overlay: document.getElementById("setupOverlay"),
  qr: document.getElementById("setupQr"),
  address: document.getElementById("setupAddress"),
  code: document.getElementById("setupCode"),
  foot: document.getElementById("setupFoot"),
};

let setupTimer = null;

function setupVisible() {
  return !setupEl.overlay.hidden;
}

function setupRender(daten) {
  if (!daten.active) { setupHide(); return; }

  setupEl.qr.innerHTML = daten.qr || "";
  setupEl.address.textContent = daten.address || "—";
  setupEl.code.textContent = (daten.code || "").replace(/(\d{3})(\d{3})/, "$1 $2");

  const minuten = Math.floor(daten.remaining / 60);
  const sekunden = daten.remaining % 60;
  setupEl.foot.textContent =
    `Noch ${minuten}:${String(sekunden).padStart(2, "0")} Minuten – ` +
    "beliebige Taste beendet die Einrichtung";
  setupEl.overlay.hidden = false;
}

async function setupRefresh() {
  try {
    const antwort = await fetch("/api/setup", { cache: "no-store" });
    const daten = await antwort.json();
    if (setupVisible() || daten.active) setupRender(daten);
  } catch {
    /* Dienst kurz weg - beim naechsten Durchlauf erneut. */
  }
}

async function setupStart() {
  try {
    const antwort = await fetch("/api/setup", { method: "POST" });
    const daten = await antwort.json();
    if (!daten.ok) return daten;
    if (!daten.reachable) return { ok: false, error: "Keine Netzwerkadresse gefunden." };
    if (!daten.qr) {
      return { ok: false, error: "QR-Code nicht erzeugbar – segno fehlt." };
    }
    setupRender(daten);
    clearInterval(setupTimer);
    setupTimer = setInterval(setupRefresh, 1000);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

function setupHide() {
  clearInterval(setupTimer);
  setupTimer = null;
  setupEl.overlay.hidden = true;
  setupEl.qr.replaceChildren();
}

/** Beendet Anzeige und Zugang. */
function setupStop() {
  setupHide();
  fetch("/api/setup", { method: "DELETE" }).catch(() => {});
}

// Jede Eingabe am Geraet beendet die Anzeige - und damit den Zugang.
for (const typ of ["keydown", "mousedown", "touchstart"]) {
  document.addEventListener(typ, () => { if (setupVisible()) setupStop(); }, { passive: true });
}

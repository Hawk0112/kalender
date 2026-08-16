/* Termindetails zur Fehlersuche.

   Ein Mausklick auf einen Termin zeigt alles, was ueber ihn bekannt ist:
   die von der Anwendung abgeleiteten Werte und darunter die Rohdaten, so wie
   sie im Kalender stehen. Nur mit der Maus erreichbar - fuer die Bedienung
   mit den drei Tastern hat das keinen Nutzen. */

const detailsEl = {
  overlay: document.getElementById("details"),
  title: document.getElementById("detailsTitle"),
  body: document.getElementById("detailsBody"),
  close: document.getElementById("detailsClose"),
};

const ZEIT_FMT = new Intl.DateTimeFormat("de-AT", {
  weekday: "short", day: "numeric", month: "long", year: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false,
});

function detailsZeit(iso) {
  if (!iso) return "—";
  try {
    return `${ZEIT_FMT.format(new Date(iso))}  (${iso})`;
  } catch {
    return iso;
  }
}

function detailsZeile(name, wert, klasse = "") {
  const zeile = document.createElement("div");
  zeile.className = `detail-row ${klasse}`.trim();
  const links = document.createElement("div");
  links.className = "detail-name";
  links.textContent = name;
  const rechts = document.createElement("div");
  rechts.className = "detail-value";
  if (wert instanceof Node) rechts.append(wert);
  else rechts.textContent = wert === "" || wert == null ? "—" : String(wert);
  zeile.append(links, rechts);
  return zeile;
}

function detailsAbschnitt(titel) {
  const kopf = document.createElement("h3");
  kopf.className = "detail-head";
  kopf.textContent = titel;
  return kopf;
}

function detailsFarbe(farbe) {
  const box = document.createElement("span");
  box.className = "detail-color";
  const punkt = document.createElement("span");
  punkt.className = "detail-swatch";
  punkt.style.background = farbe;
  box.append(punkt, document.createTextNode(farbe));
  return box;
}

function detailsRender(d) {
  detailsEl.title.textContent = d.title || "Termin";
  detailsEl.body.replaceChildren();

  detailsEl.body.append(detailsAbschnitt("So zeigt der Kalender ihn an"));
  detailsEl.body.append(
    detailsZeile("Titel", d.title),
    detailsZeile("Kalender", d.calendar),
    detailsZeile("Beginn", detailsZeit(d.start)),
    detailsZeile("Ende", detailsZeit(d.end)),
    detailsZeile("Ganztägig", d.all_day ? "ja" : "nein"),
    detailsZeile("Ort", d.location),
    detailsZeile("Farbe", detailsFarbe(d.color)),
    detailsZeile("Farbe des Kalenders", detailsFarbe(d.source_color)),
    detailsZeile("Hervorhebung", d.highlight ? `${d.highlight} ${d.icon}` : "keine"),
    detailsZeile(
      "Erinnerungszeichen",
      d.reminder_mark ? `„${d.reminder_mark}“ am Titelanfang erkannt` : "keines",
    ),
  );

  const alarme = d.alarms || [];
  detailsEl.body.append(detailsAbschnitt(
    alarme.length ? `Erinnerungen (${alarme.length})` : "Erinnerungen",
  ));
  if (!alarme.length) {
    detailsEl.body.append(detailsZeile(
      "keine",
      "Dieser Termin bringt keine Erinnerung mit (VALARM fehlt) und trägt kein "
      + "Erinnerungszeichen am Titelanfang.",
      "detail-hint",
    ));
  } else {
    alarme.forEach((a, i) => {
      const vorlauf = Math.round((new Date(d.start) - new Date(a)) / 60000);
      detailsEl.body.append(detailsZeile(
        `Erinnerung ${i + 1}`,
        `${detailsZeit(a)} — ${vorlauf} Min. vor Beginn`,
      ));
    });
  }

  const roh = d.raw || {};
  detailsEl.body.append(detailsAbschnitt("Rohdaten aus dem Kalender"));
  (roh.eigenschaften || []).forEach((e) => {
    const params = e.parameter
      ? Object.entries(e.parameter).map(([k, v]) => `${k}=${v}`).join("  ")
      : "";
    detailsEl.body.append(detailsZeile(
      e.name, params ? `${e.wert}\n${params}` : e.wert, "detail-raw",
    ));
  });

  (roh.unterkomponenten || []).forEach((u) => {
    detailsEl.body.append(detailsAbschnitt(`Unterabschnitt ${u.art}`));
    u.eigenschaften.forEach((e) =>
      detailsEl.body.append(detailsZeile(e.name, e.wert, "detail-raw")));
  });
}

async function detailsOpen(id) {
  detailsEl.title.textContent = "Termin";
  detailsEl.body.replaceChildren(
    detailsZeile("", "wird geladen…", "detail-hint"),
  );
  detailsEl.overlay.hidden = false;
  try {
    const antwort = await fetch(`/api/event?id=${encodeURIComponent(id)}`, { cache: "no-store" });
    const daten = await antwort.json();
    if (!daten.ok) {
      detailsEl.body.replaceChildren(detailsZeile("Fehler", daten.error, "detail-hint"));
      return;
    }
    detailsRender(daten);
  } catch (err) {
    detailsEl.body.replaceChildren(detailsZeile("Fehler", String(err), "detail-hint"));
  }
}

function detailsClose() {
  detailsEl.overlay.hidden = true;
  detailsEl.body.replaceChildren();
}

/* Klick auf einen Termin - im Stundenraster, in der Ganztagszeile, in den
   Sammelzeilen und in der Terminliste. */
document.addEventListener("click", (event) => {
  const knoten = event.target.closest?.(".event, .chip, .agenda .item");
  if (!knoten || !knoten.dataset.eventId) return;
  detailsOpen(knoten.dataset.eventId);
});

detailsEl.close.addEventListener("click", detailsClose);
detailsEl.overlay.addEventListener("click", (event) => {
  if (event.target === detailsEl.overlay) detailsClose();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !detailsEl.overlay.hidden) detailsClose();
});

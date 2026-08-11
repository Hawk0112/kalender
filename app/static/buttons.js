/* Auswertung der Taster am GPIO.

   Die Schleife haengt dauerhaft in einer wartenden Abfrage: Der Dienst
   antwortet erst, wenn ein Taster gedrueckt wurde (oder nach 25 Sekunden).
   Dadurch reagiert die Anzeige sofort, ohne im Leerlauf staendig nachzufragen.

   Aufgaben:
     today   - laeutet ein Alarm, wird er beendet; sonst zurueck auf heute
     forward - eine Woche vorwaerts
     back    - eine Woche zurueck
*/

let buttonCounts = null;   // zuletzt bekannte Zaehlerstaende
let buttonLoopRunning = false;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function applyButtonCounts(data) {
  if (buttonCounts === null) {
    buttonCounts = data;    // erster Stand ist nur die Ausgangsbasis
    return;
  }

  const delta = (name) => Math.max(0, (data[name] || 0) - (buttonCounts[name] || 0));
  const today = delta("today");
  const steps = delta("forward") - delta("back");
  buttonCounts = data;

  if (today > 0) {
    // Ein laufender Alarm hat Vorrang, sonst zurueck auf die aktuelle Woche.
    if (alarmIsRinging()) stopAlarm();
    else goToday();
  }
  if (steps !== 0) shiftWeeks(steps);
}

async function buttonLoop() {
  if (buttonLoopRunning) return;
  buttonLoopRunning = true;

  for (;;) {
    try {
      const url = buttonCounts === null
        ? "/api/button"
        : `/api/button/wait?since=${buttonCounts.total}`;
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      applyButtonCounts(await response.json());
    } catch (err) {
      // Dienst gerade nicht erreichbar - in Ruhe erneut versuchen.
      await sleep(3000);
    }
  }
}

/* Dieselben Befehle über die Tastatur, falls einmal eine angesteckt ist. */
document.addEventListener("keydown", (event) => {
  if (Date.now() - (window.__alarmStoppedAt || 0) < 1000) return;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "")) return;
  if (!document.getElementById("settings").hidden) return;

  if (event.key === "ArrowRight" || event.key === "PageDown") shiftWeeks(1);
  else if (event.key === "ArrowLeft" || event.key === "PageUp") shiftWeeks(-1);
  else if (event.key === "Home") goToday();
});

buttonLoop();

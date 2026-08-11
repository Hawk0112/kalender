/* Alarm: spielt bei einer faelligen Erinnerung einen Ton und blendet den
   Termin ein. Die Toene werden im Browser erzeugt (Web Audio), es gibt also
   keine Audiodateien, die fehlen oder im falschen Format vorliegen koennen. */

const alarmEl = {
  banner: document.getElementById("alarmBanner"),
  title: document.getElementById("alarmTitle"),
  detail: document.getElementById("alarmDetail"),
  hint: document.getElementById("alarmHint"),
};

/* ---------- Tonerzeugung ---------- */

let audio = null;      // AudioContext, erst bei Bedarf angelegt
let master = null;     // Lautstaerkeregelung

function audioReady() {
  if (!audio) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    audio = new Ctx();
    master = audio.createGain();
    master.gain.value = 0.8;
    master.connect(audio.destination);
  }
  if (audio.state === "suspended") audio.resume().catch(() => {});
  return audio.state !== "suspended";
}

/** Einzelner Ton mit weichem Ein- und Ausschwingen. */
function tone(start, freq, duration, type = "sine", peak = 0.9) {
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.linearRampToValueAtTime(peak, start + 0.012);
  gain.gain.setValueAtTime(peak, start + duration * 0.6);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(gain);
  gain.connect(master);
  osc.start(start);
  osc.stop(start + duration + 0.05);
}

// Jeder Ton beschreibt einen Zyklus, der sich alle "period" Sekunden wiederholt.
const SOUNDS = {
  beep: {
    period: 1.5,
    play: (t) => { tone(t, 1000, 0.13, "sine"); tone(t + 0.22, 1000, 0.13, "sine"); },
  },
  alarm: {
    period: 1.6,
    play: (t) => {
      for (let i = 0; i < 8; i += 1) {
        tone(t + i * 0.17, i % 2 ? 700 : 950, 0.12, "square", 0.55);
      }
    },
  },
  chime: {
    period: 2.6,
    play: (t) => {
      [880, 1108.7, 1318.5].forEach((freq, index) => {
        tone(t + index * 0.19, freq, 1.0, "triangle", 0.7);
      });
    },
  },
  gong: {
    period: 3.2,
    play: (t) => {
      tone(t, 180, 2.6, "sine", 0.9);
      tone(t, 361, 2.0, "sine", 0.35);
      tone(t + 0.02, 540, 1.4, "sine", 0.16);
    },
  },
  soft: {
    period: 4.0,
    play: (t) => {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(523.25, t);
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.linearRampToValueAtTime(0.7, t + 0.7);
      gain.gain.linearRampToValueAtTime(0.7, t + 1.4);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 2.6);
      osc.connect(gain);
      gain.connect(master);
      osc.start(t);
      osc.stop(t + 2.7);
      tone(t + 0.05, 784, 2.2, "sine", 0.22);
    },
  },
};

let ringTimer = null;   // Wiederholung des Tonzyklus
let stopTimer = null;   // automatisches Ende
let ringing = false;

function startSound(soundId, volume) {
  if (!audioReady()) return false;
  const sound = SOUNDS[soundId] || SOUNDS.beep;
  master.gain.value = Math.max(0, Math.min(1, Number(volume ?? 0.8)));

  const cycle = () => {
    try {
      sound.play(audio.currentTime + 0.05);
    } catch (err) {
      console.warn("Ton nicht abspielbar:", err);
      stopSound();
    }
  };
  cycle();
  ringTimer = setInterval(cycle, sound.period * 1000);
  return true;
}

function stopSound() {
  if (ringTimer) { clearInterval(ringTimer); ringTimer = null; }
  if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
  if (master) {
    // Kurz ausblenden, damit es nicht knackt.
    const now = audio.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(0.0001, now + 0.08);
  }
}

/** Ton zum Ausprobieren in den Einstellungen. */
function previewSound(soundId, volume, seconds = 3) {
  stopAlarm();
  if (!startSound(soundId, volume)) return false;
  ringing = true;
  stopTimer = setTimeout(stopAlarm, seconds * 1000);
  return true;
}

/* ---------- Alarm mit Anzeige ----------
   Die Taster wertet buttons.js aus; von dort kommt stopAlarm(). */

function stopAlarm() {
  if (!ringing && !ringTimer) return;
  ringing = false;
  stopSound();
  alarmEl.banner.hidden = true;
  // Merker, damit dieselbe Taste nicht gleich die Einstellungen oeffnet.
  window.__alarmStoppedAt = Date.now();
}

function alarmIsRinging() {
  return ringing;
}

function fireAlarm(entry, settings) {
  const started = startSound(settings.sound, settings.volume);
  ringing = true;

  alarmEl.title.textContent = (entry.icon ? `${entry.icon} ` : "") + entry.title;
  const parts = [];
  if (!entry.all_day) parts.push(`${hhmm(entry.start)}–${hhmm(entry.end)}`);
  if (entry.location) parts.push(entry.location);
  parts.push(entry.calendar);
  if (entry.lead_minutes > 0) parts.push(`in ${entry.lead_minutes} Min.`);
  alarmEl.detail.textContent = parts.join(" · ");
  alarmEl.banner.style.setProperty("--c", entry.color);

  const hasButton = alarmData.button && alarmData.button.available;
  const stopWith = hasButton ? "Taster oder beliebige Taste drücken" : "Beliebige Taste drücken";

  // Die Anzeige deckt den Kalender ab, deshalb steht in beiden Betriebsarten
  // dabei, wie man sie vorzeitig loswird.
  alarmEl.hint.textContent = started ? stopWith : `Ton stummgeschaltet – ${stopWith}`;

  if (settings.stop_mode === "key") {
    // Sicherheitsnetz, falls niemand da ist.
    stopTimer = setTimeout(stopAlarm, (settings.hard_limit_seconds || 300) * 1000);
  } else {
    stopTimer = setTimeout(stopAlarm, Number(settings.duration_seconds || 10) * 1000);
  }
  alarmEl.banner.hidden = false;
}

/* ---------- Faelligkeit pruefen ---------- */

const firedAlarms = new Set();
let alarmData = { settings: null, list: [], button: null };

/** Wird nach jedem Abruf von app.js aufgerufen. */
function updateAlarms(data) {
  alarmData = {
    settings: data.alarm || null,
    list: data.alarms || [],
    button: data.button || null,
  };

  // Beim ersten Datensatz alles Vergangene als erledigt merken, damit nach
  // einem Neustart des Browsers nicht alte Erinnerungen nachklingeln.
  if (!updateAlarms.initialised) {
    updateAlarms.initialised = true;
    const now = Date.now();
    for (const entry of alarmData.list) {
      if (new Date(entry.at).getTime() <= now) firedAlarms.add(entry.id);
    }
  }
}

function checkAlarms() {
  const settings = alarmData.settings;
  if (!settings || !settings.enabled || ringing) return;

  const now = Date.now();
  for (const entry of alarmData.list) {
    if (firedAlarms.has(entry.id)) continue;
    const due = new Date(entry.at).getTime();
    // Nur ausloesen, wenn der Zeitpunkt gerade erst erreicht wurde.
    if (due <= now && now - due < 120_000) {
      firedAlarms.add(entry.id);
      fireAlarm(entry, settings);
      return;
    }
    if (due <= now) firedAlarms.add(entry.id);
  }

  // Speicher sauber halten: nur bekannte Erinnerungen merken.
  if (firedAlarms.size > 500) {
    const known = new Set(alarmData.list.map((entry) => entry.id));
    for (const id of firedAlarms) if (!known.has(id)) firedAlarms.delete(id);
  }
}

// Jede Eingabe beendet den Alarm - im Modus "auto" ebenso, das ist nie stoerend.
for (const type of ["keydown", "mousedown", "touchstart"]) {
  document.addEventListener(type, () => { if (ringing) stopAlarm(); }, { passive: true });
}

setInterval(checkAlarms, 1000);

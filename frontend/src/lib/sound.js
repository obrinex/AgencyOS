/**
 * Interface click feedback, synthesised in the browser.
 *
 * The same engine as obrinex.space, so a press here and a press there sound
 * identical — which is most of what makes two products feel like one studio.
 * No audio files: nothing to load, nothing to 404 after a deploy, and a build
 * that stays the same size.
 *
 * ## Off by default, unlike the website
 *
 * The marketing site starts with sound on because a visitor is there for two
 * minutes and the sound is part of the impression. This is a tool people have
 * open for eight hours, sometimes on a call, sometimes in an open office. A
 * work application that starts making noise nobody asked for is a support
 * ticket, so it waits to be switched on and then remembers.
 *
 * ## Why a click is noise and not a tone
 *
 * A pitched blip has a note, so the ear treats it as music and gets tired of it
 * by the twentieth press. Filtered noise has no pitch to tire of — it reads as
 * a mechanism, which is why good hardware sounds like this. Two layers: a
 * bright bandpassed tick for precision, and a low body underneath for weight.
 */

const PREF_KEY = "obx-crm-sound";

/** Master level. Matches the site so neither product is louder than the other. */
const SFX_LEVEL = 0.85;

let ctx = null;
let bus = null;
let lastAt = 0;
let failed = false;
let enabled = false;

/* ------------------------------------------------------------- preference */

export function soundEnabled() {
  return enabled;
}

export function loadSoundPref() {
  try {
    enabled = window.localStorage.getItem(PREF_KEY) === "1";
  } catch {
    enabled = false;
  }
  return enabled;
}

export function setSoundEnabled(on) {
  enabled = Boolean(on);
  try {
    window.localStorage.setItem(PREF_KEY, enabled ? "1" : "0");
  } catch {
    /* private mode — the choice just won't persist */
  }
  // Confirm the switch with the sound it switches on. Silence would be an
  // ambiguous answer to "did that work?".
  if (enabled) {
    unlock();
    click("confirm");
  }
  return enabled;
}

/* ---------------------------------------------------------------- context */

function audio() {
  if (failed || typeof window === "undefined") return null;
  if (ctx) return ctx;

  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) {
    failed = true;
    return null;
  }
  try {
    ctx = new Ctor();
    bus = ctx.createGain();
    bus.gain.value = SFX_LEVEL;
    bus.connect(ctx.destination);
    return ctx;
  } catch {
    failed = true;
    return null;
  }
}

/** Browsers refuse audio before a gesture; this must be called from inside one. */
export function unlock() {
  const c = audio();
  if (c && c.state === "suspended") c.resume();
}

/* ----------------------------------------------------------------- clicks */

const CLICKS = {
  // Buttons, links, rows.
  tap: {
    tick: { seconds: 0.03, decay: 0.0035, hz: 2600, q: 7, gain: 0.85 },
    body: { seconds: 0.05, decay: 0.012, hz: 420, gain: 0.5 },
  },
  // Menus, tabs, switches, disclosure — opening something is audibly a
  // different gesture from pressing something.
  soft: {
    tick: { seconds: 0.03, decay: 0.005, hz: 1400, q: 5, gain: 0.5 },
    body: { seconds: 0.07, decay: 0.018, hz: 300, gain: 0.6 },
  },
  // Save, submit, confirm. Two strikes 60ms apart — a latch closing. Nothing
  // else in the app makes this sound, so it always means "committed".
  confirm: {
    tick: { seconds: 0.03, decay: 0.004, hz: 3100, q: 8, gain: 1 },
    body: { seconds: 0.09, decay: 0.022, hz: 360, gain: 0.7 },
    double: 0.06,
  },
};

/**
 * One layer: noise under an exponential envelope, filtered, played once.
 *
 * The buffer is rebuilt per strike rather than cached — it is a few hundred
 * samples, and fresh randomness is what stops twenty presses in a row sounding
 * like a loop of one press.
 */
function strike(c, dest, at, o) {
  const frames = Math.max(1, Math.floor(o.seconds * c.sampleRate));
  // Decay in seconds, not samples, so the shape holds at 44.1k as well as 48k.
  const tau = Math.max(1, o.decay * c.sampleRate);

  const buf = c.createBuffer(1, frames, c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < frames; i += 1) {
    data[i] = (Math.random() * 2 - 1) * Math.exp(-i / tau);
  }

  const filter = c.createBiquadFilter();
  filter.type = o.type;
  filter.frequency.value = o.hz * (1 + (Math.random() - 0.5) * 0.24);
  if (o.q !== undefined) filter.Q.value = o.q;

  const g = c.createGain();
  g.gain.value = o.gain;

  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(filter).connect(g).connect(dest);
  src.onended = () => src.disconnect();
  src.start(at);
}

function press(c, spec, at, level = 1) {
  strike(c, bus, at, { ...spec.tick, gain: spec.tick.gain * level, type: "bandpass" });
  strike(c, bus, at, { ...spec.body, gain: spec.body.gain * level, type: "lowpass" });
}

export function click(variant = "tap") {
  if (!enabled) return;
  const c = audio();
  if (!c || !bus || c.state !== "running") return;

  // A pointerdown and its synthetic click can land on the same target; two
  // identical transients milliseconds apart phase into something that sounds
  // like a glitch rather than a press.
  const now = performance.now();
  if (now - lastAt < 45) return;
  lastAt = now;

  const spec = CLICKS[variant] || CLICKS.tap;
  const t = c.currentTime;
  press(c, spec, t);
  if (spec.double) press(c, spec, t + spec.double, 0.55);
}

/* ------------------------------------------------------------- delegation */

const SOFT =
  "summary, select, [role='switch'], [role='tab'], [role='combobox'], [role='menuitem'], [aria-expanded], [aria-haspopup], input[type='checkbox'], input[type='radio']";
const TAP = "button, a[href], [role='button'], [role='option']";

/** Which sound an element deserves, or null. */
function variantFor(target) {
  if (!(target instanceof Element)) return null;
  try {
    if (target.closest("[data-no-sound]")) return null;
    const forced = target.closest("[data-sound]");
    if (forced) {
      const v = forced.getAttribute("data-sound");
      if (v === "tap" || v === "soft" || v === "confirm") return v;
    }
    if (target.closest(SOFT)) return "soft";
    if (target.closest(TAP)) return "tap";
  } catch {
    // `closest` throws on a selector the browser doesn't understand, and one
    // throw here would silence the whole app for that user.
    return null;
  }
  return null;
}

/**
 * Listen once, at the document, for the whole application.
 *
 * Delegation rather than props means no existing page had to be edited to gain
 * click feedback — and none of them can break it. Returns a teardown.
 */
export function installSound() {
  loadSoundPref();

  const onPointerDown = (e) => {
    // The first gesture also unlocks the context, so the very press that turns
    // audio on is early enough to be heard.
    unlock();
    const v = variantFor(e.target);
    if (v) click(v);
  };

  const onKeyDown = (e) => {
    if (e.repeat) return;
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target;
    if (!el) return;
    const typing =
      el.tagName === "TEXTAREA" ||
      (el.tagName === "INPUT" &&
        !["checkbox", "radio", "button", "submit"].includes(el.type)) ||
      el.isContentEditable;
    // Enter in a text field is "send" and deserves the latch; space in one is
    // just typing and must stay silent.
    if (typing) {
      if (e.key === "Enter") click("confirm");
      return;
    }
    const v = variantFor(el);
    if (v) click(e.key === "Enter" ? "confirm" : v);
  };

  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown, true);
  return () => {
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("keydown", onKeyDown, true);
  };
}

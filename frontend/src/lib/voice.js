/**
 * The assistant's voice, in the members' portal only.
 *
 * ## Why only there
 *
 * obrinex.space shipped a site-wide narrator once. It worked, and it was the
 * wrong idea — a voice that follows you around is something to escape. The
 * voice now appears where someone has arrived somewhere that is *theirs*, which
 * is the only context in which being spoken to reads as welcome rather than as
 * an interruption. It is not in the CRM, and it is not in the client portal.
 *
 * ## The two hard problems
 *
 * 1. **Autoplay.** Browsers refuse audio until the page has had a gesture. A
 *    member arriving from the login screen has already clicked, so the greeting
 *    plays immediately; one who reloaded the portal directly has not, so the
 *    line waits and plays on their first click instead of being swallowed. It
 *    never nags for permission.
 *
 * 2. **Nothing to play.** If `npm run narration` has not been run, there is no
 *    mp3. Rather than silence, the line degrades to the member's own device
 *    voice — plainer, but the portal still says hello.
 *
 * The preference is separate from the click-sound preference in lib/sound.js.
 * They are different promises: one is feedback you asked for by pressing
 * something, the other is a voice that arrives on its own. Someone can
 * reasonably want either without the other.
 */

const PREF_KEY = "obx-crm-voice";

/** Where the pre-rendered audio for a line lives. Mirrors the website's path. */
export const audioUrlFor = (id) => `${process.env.PUBLIC_URL || ""}/audio/narrator/${id}.mp3`;

/** The text of each line, for the device-voice fallback. Ids match narration.json. */
export const LINES = {
  "portal-welcome": "Hi, valuable member. Glad to see you today.",
};

let enabled = true;
let current = null;
/** Bumped on every cancel, so a line in flight knows to abandon itself. */
let generation = 0;

/* ------------------------------------------------------------- preference */

export function voiceEnabled() {
  return enabled;
}

/** Defaults ON. The greeting is the feature; shipping it switched off would be
 *  shipping a setting instead. It is one short line, it is easy to silence, and
 *  the choice is remembered from then on. */
export function loadVoicePref() {
  try {
    enabled = window.localStorage.getItem(PREF_KEY) !== "0";
  } catch {
    enabled = true;
  }
  return enabled;
}

export function setVoiceEnabled(on) {
  enabled = Boolean(on);
  try {
    window.localStorage.setItem(PREF_KEY, enabled ? "1" : "0");
  } catch {
    /* private mode — the choice just won't persist */
  }
  // Stop mid-word when switched off. Anything else makes the off switch feel
  // broken, which is the one thing an off switch must never feel.
  if (!enabled) hush();
  return enabled;
}

/* ------------------------------------------------------------------ speech */

export function hush() {
  generation += 1;
  if (current) {
    current.pause();
    current.src = "";
    current = null;
  }
  try {
    window.speechSynthesis?.cancel();
  } catch {
    /* no synthesis on this device */
  }
}

/** The device's own voice — the fallback when the mp3 is missing or unplayable. */
function speakLocally(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth || typeof window.SpeechSynthesisUtterance !== "function") return resolve();
    try {
      const utterance = new window.SpeechSynthesisUtterance(text);
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.volume = 0.9;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      synth.speak(utterance);
    } catch {
      resolve();
    }
  });
}

/**
 * Speak one line. Resolves when it finishes, or immediately if the voice is off,
 * so a caller can always await it without knowing whether anything was audible.
 *
 * Returns `false` if the browser refused to start — which is how the caller
 * knows to wait for a gesture rather than assume the greeting was heard.
 */
export function say(id) {
  return new Promise((resolve) => {
    if (!enabled) return resolve(true);
    const text = LINES[id];

    // Whatever is speaking stops before anything else starts. Bumping the
    // counter marks the previous line abandoned, but an <audio> element already
    // playing does not care what a counter says — it runs to the end underneath
    // the new one, and two voices a few hundred milliseconds apart sound like a
    // corrupted file rather than like a bug. React's development double-invoke
    // of effects reaches here twice as a matter of course, so this is the
    // normal path, not an edge case.
    hush();
    generation += 1;
    const mine = generation;

    // `error` and a rejected play() can both fire for the same failure, and
    // `ended` can arrive after either. Settling once keeps that from starting
    // two fallback voices.
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };

    const el = new Audio(audioUrlFor(id));
    el.volume = 0.9;
    el.preload = "auto";
    current = el;

    const done = () => {
      if (current === el) current = null;
      finish(true);
    };

    // A missing file and a blocked autoplay both land here, and they need
    // opposite answers: no file means fall back to the device voice and call it
    // done; blocked means report failure so the caller can retry after a
    // gesture. `NotAllowedError` is the only reliable way to tell them apart.
    const degrade = (err) => {
      if (settled) return;
      if (current === el) current = null;
      if (generation !== mine) return finish(true);
      if (err?.name === "NotAllowedError") return finish(false);
      if (!text) return finish(true);
      void speakLocally(text).then(() => finish(true));
    };

    el.addEventListener("ended", done, { once: true });
    el.addEventListener("error", () => degrade(), { once: true });
    void el.play().catch(degrade);
  });
}

/**
 * Say a line as soon as the browser will allow it.
 *
 * If autoplay is refused, the line is held and spoken on the next real gesture
 * anywhere on the page — which is almost always within a second or two, and
 * costs the member nothing. Returns a teardown that also drops a pending line,
 * so leaving the portal never leaves a voice armed to fire on some other page.
 */
export function sayWhenAllowed(id) {
  let cancelled = false;
  let disarm = null;

  const armForGesture = () => {
    const events = ["pointerdown", "keydown", "touchstart"];
    const fire = () => {
      disarm?.();
      if (!cancelled) void say(id);
    };
    disarm = () => {
      disarm = null;
      events.forEach((name) => window.removeEventListener(name, fire, true));
    };
    events.forEach((name) =>
      window.addEventListener(name, fire, { capture: true, once: true })
    );
  };

  void say(id).then((ok) => {
    if (ok || cancelled) return;
    armForGesture();
  });

  return () => {
    cancelled = true;
    disarm?.();
    hush();
  };
}

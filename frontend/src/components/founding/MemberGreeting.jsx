import { useEffect, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { loadVoicePref, setVoiceEnabled, sayWhenAllowed, hush } from "@/lib/voice";

/** Greets the member when they open the portal, and the switch that stops it.
 *
 *  The greeting and its off switch are one component on purpose. A voice that
 *  arrives uninvited must carry its own way out — putting the toggle three
 *  screens away in a settings page means the only way to stop it is to close
 *  the tab, and someone who does that once does not come back.
 *
 *  Mounted inside the portal shell, so it speaks on every open of the portal
 *  and nowhere else. Switching tabs within the portal does not re-trigger it:
 *  the shell stays mounted, and being greeted again for tapping Members would
 *  be the site-wide narrator all over again.
 */
export default function MemberGreeting() {
  const [on, setOn] = useState(() => loadVoicePref());

  useEffect(() => {
    if (!on) return undefined;
    // A short beat after mount. Landing straight into speech collides with the
    // page still settling — and with the click that navigated here, which on a
    // slower device is still finishing its own sound.
    let stop = null;
    const timer = setTimeout(() => { stop = sayWhenAllowed("portal-welcome"); }, 600);
    return () => {
      clearTimeout(timer);
      stop?.();
      hush();
    };
    // Runs once per mount of the portal. `on` is read at mount rather than
    // watched: flipping the switch back on should not make the greeting replay
    // on the spot, which would be startling and would say the wrong thing about
    // what the switch does.
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => setOn(setVoiceEnabled(!on));

  return (
    <button
      onClick={toggle}
      data-testid="founding-voice-toggle"
      aria-pressed={on}
      title={on ? "Assistant voice on" : "Assistant voice off"}
      aria-label={on ? "Turn the assistant voice off" : "Turn the assistant voice on"}
      className={`obx-glass obx-lift flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors ${
        on ? "text-primary" : "text-carbon"
      }`}
    >
      {on ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
    </button>
  );
}

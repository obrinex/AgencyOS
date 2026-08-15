/**
 * Render every narrator line to a static mp3, once, offline.
 *
 *   npm run narration              only lines whose text has changed
 *   npm run narration -- --force   all of them again
 *
 * The same script as obrinex.space's, pointed at this repo — deliberately, so
 * the two products speak with one voice and one pipeline. Why not call a TTS API
 * from the browser instead:
 *
 *   Cost      the greeting plays every time a member opens the portal. A live
 *             call would bill for every open, forever, for one fixed sentence.
 *   Latency   a member would wait a second and a half to be said hello to — by
 *             which point they are already reading their passport.
 *   Fragility a missing or rotated key breaks a runtime call. It cannot break a
 *             file already sitting in public/.
 *
 * CRA copies public/ into build/ untouched, so the mp3 travels with the deploy
 * automatically and there is nothing to wire up.
 *
 * ## Where the key comes from
 *
 * This repo has no TTS key of its own and does not need one at runtime. The key
 * is only ever read here, at author time. Checked in order:
 *
 *   1. a real environment variable
 *   2. frontend/.env.local, frontend/.env
 *   3. ../../../obrinex web/.env.local — the website repo beside this one,
 *      which already owns the paid voice. Sharing it is the point: two products
 *      that sound like two studios is the thing this avoids.
 *
 * Without any key the script exits non-zero and changes nothing. The portal
 * still greets people — see src/lib/voice.js, which falls back to the member's
 * own device voice rather than to silence.
 */
import { readFile, writeFile, mkdir, readdir, unlink } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";

const root = process.cwd();
const OUT = path.join(root, "public", "audio", "narrator");
/** Records the text each mp3 was rendered from, so edits can be detected. */
const MANIFEST = path.join(OUT, "manifest.json");
const force = process.argv.includes("--force");

/* ------------------------------------------------------------------- env */

const ENV_FILES = [
  path.join(root, ".env.local"),
  path.join(root, ".env"),
  // The website repo, two levels up and across. Absent on a machine that only
  // checked out the CRM, which is why every read here is allowed to fail.
  path.join(root, "..", "..", "..", "obrinex web", ".env.local"),
];

for (const file of ENV_FILES) {
  try {
    const text = await readFile(file, "utf8");
    for (const line of text.split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
      if (!m) continue;
      const [, key, raw] = m;
      if (process.env[key]) continue; // a real env var always wins
      // Strip a trailing inline comment, but only when whitespace precedes the
      // hash — the exact rule dotenv uses. Getting this wrong once shipped an
      // API key with its own documentation glued to the end of it.
      process.env[key] = raw.replace(/\s+#.*$/, "").replace(/^["']|["']$/g, "");
    }
  } catch {
    /* file absent — fine */
  }
}

function resolveTts() {
  if (process.env.ELEVENLABS_API_KEY)
    return { provider: "elevenlabs", key: process.env.ELEVENLABS_API_KEY };
  if (process.env.OPENAI_API_KEY)
    return { provider: "openai", key: process.env.OPENAI_API_KEY };
  if (process.env.DEEPGRAM_API_KEY)
    return { provider: "deepgram", key: process.env.DEEPGRAM_API_KEY };
  return null;
}

/* ------------------------------------------------------------- synthesis */

async function synthesize({ provider, key }, text, voice) {
  if (provider === "deepgram") {
    const model = voice?.startsWith("aura") ? voice : "aura-2-thalia-en";
    const res = await fetch(
      `https://api.deepgram.com/v1/speak?model=${encodeURIComponent(model)}`,
      {
        method: "POST",
        headers: { Authorization: `Token ${key}`, "content-type": "application/json" },
        body: JSON.stringify({ text }),
      },
    );
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return Buffer.from(await res.arrayBuffer());
  }

  if (provider === "elevenlabs") {
    const id = process.env.ELEVENLABS_VOICE_ID ?? "EXAVITQu4vr4xnSDxMaL";
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${id}`, {
      method: "POST",
      headers: { "xi-api-key": key, "content-type": "application/json" },
      body: JSON.stringify({
        text,
        model_id: "eleven_turbo_v2_5",
        voice_settings: {
          stability: 0.55,
          similarity_boost: 0.75,
          style: 0.25,
          use_speaker_boost: true,
        },
      }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return Buffer.from(await res.arrayBuffer());
  }

  const res = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: "gpt-4o-mini-tts",
      voice: process.env.OPENAI_TTS_VOICE ?? "shimmer",
      input: text,
      instructions:
        "Warm, calm and unhurried. Greeting someone you are pleased to see, not announcing them.",
      response_format: "mp3",
    }),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

/* ----------------------------------------------------------------- main */

const cfg = resolveTts();
if (!cfg) {
  console.error(
    "\n[narration] No TTS key found.\n" +
      "[narration] Add DEEPGRAM_API_KEY (or ELEVENLABS_API_KEY / OPENAI_API_KEY)\n" +
      "[narration] to frontend/.env.local, or check out 'obrinex web' beside this repo.\n" +
      "[narration] The portal still greets members without this — the line falls\n" +
      "[narration] back to the member's own device voice.\n",
  );
  process.exit(1);
}

const { lines, voice } = JSON.parse(
  await readFile(path.join(root, "content", "narration.json"), "utf8"),
);
await mkdir(OUT, { recursive: true });

let manifest = {};
try {
  manifest = JSON.parse(await readFile(MANIFEST, "utf8"));
} catch {
  /* first run */
}

const stamp = (text) =>
  createHash("sha1").update(`${cfg.provider}:${voice}:${text}`).digest("hex").slice(0, 12);

console.log(`[narration] provider: ${cfg.provider}${voice ? ` (${voice})` : ""}`);

let made = 0;
let kept = 0;
let failedCount = 0;
for (const line of lines) {
  const want = stamp(line.text);
  if (!force && manifest[line.id] === want) {
    kept += 1;
    continue;
  }
  process.stdout.write(`[narration] ${line.id} … `);
  try {
    const audio = await synthesize(cfg, line.text, voice);
    await writeFile(path.join(OUT, `${line.id}.mp3`), audio);
    manifest[line.id] = want;
    made += 1;
    console.log(`${(audio.length / 1024).toFixed(0)} kB`);
  } catch (err) {
    failedCount += 1;
    console.log(`FAILED — ${err.message.slice(0, 160)}`);
  }
}

// A line deleted from the json should not leave an orphan mp3 in the deploy.
const known = new Set(lines.map((l) => `${l.id}.mp3`));
for (const file of await readdir(OUT)) {
  if (file === "manifest.json" || known.has(file)) continue;
  await unlink(path.join(OUT, file));
  delete manifest[file.replace(/\.mp3$/, "")];
  console.log(`[narration] removed orphan ${file}`);
}

await writeFile(MANIFEST, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`[narration] done — ${made} rendered, ${kept} unchanged, ${failedCount} failed`);
// Non-zero on failure so this can sit in front of a deploy without lying.
if (failedCount) process.exit(1);

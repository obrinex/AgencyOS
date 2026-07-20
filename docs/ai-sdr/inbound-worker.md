# Inbound replies — Cloudflare Email Routing Worker

This is the piece that lives outside the repo. Everything on the application
side is built and tested; this document is the ~30 minutes of setup that makes
replies actually arrive.

**Nothing here is live until `SDR_INBOUND_WEBHOOK_SECRET` is set in Vercel.**
Without it the endpoint returns 503 by design — an unsigned inbound reply can
stop a sequence, mark a lead as answered, and suppress an address permanently,
so failing closed is the only safe default.

---

## 1. What you are building

```
prospect replies
   ↓
Cloudflare Email Routing  (MX on your sending domain)
   ↓
Worker  — parses MIME, signs the payload
   ↓
POST /api/public/sdr/webhooks/inbound   (HMAC-SHA256 verified)
   ↓
match by Message-ID → classify → act
```

## 2. Prerequisites

- The sending domain's DNS is on Cloudflare (nameservers pointed there).
- Email Routing enabled for that domain: **Cloudflare dashboard → your domain →
  Email → Email Routing → Enable**. This adds MX records.

> **Order matters.** Enabling Email Routing changes MX. Do this *before* the
> ~3-week domain warm-up starts, not during it — changing MX mid-warm-up
> resets sender reputation progress.

## 3. Generate the shared secret

```bash
openssl rand -hex 32
```

Set it in both places, identically:

- **Vercel** (backend project → Settings → Environment Variables):
  `SDR_INBOUND_WEBHOOK_SECRET` — Production + Preview. Redeploy after adding
  it; Vercel only picks up env changes on a fresh deploy.
- **The Worker**, as an encrypted secret (step 5).

## 4. The Worker

Create a Worker (**Workers & Pages → Create → Worker**), then replace
`worker.js` with:

```js
// Parses inbound mail and forwards a signed JSON envelope to the SDR backend.
// Requires: npm i postal-mime  (or use the Cloudflare email parser of choice)
import PostalMime from "postal-mime";

const ENDPOINT = "https://<your-backend>.vercel.app/api/public/sdr/webhooks/inbound";

export default {
  async email(message, env, ctx) {
    const parsed = await PostalMime.parse(message.raw);

    const headers = {};
    for (const [key, value] of message.headers) headers[key] = value;

    const payload = JSON.stringify({
      id: message.headers.get("message-id") || crypto.randomUUID(),
      from: message.from,
      to: message.to,
      subject: parsed.subject || "",
      text: parsed.text || parsed.html || "",
      headers,
      received_at: new Date().toISOString(),
    });

    // HMAC-SHA256 over `{timestamp}.{body}` — must match providers/inbound_cloudflare.py
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(env.SDR_INBOUND_WEBHOOK_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const signature = await crypto.subtle.sign(
      "HMAC", key, new TextEncoder().encode(`${timestamp}.${payload}`),
    );
    const hex = [...new Uint8Array(signature)]
      .map((b) => b.toString(16).padStart(2, "0")).join("");

    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-SDR-Timestamp": timestamp,
        "X-SDR-Signature": hex,
      },
      body: payload,
    });

    // Non-2xx is logged, not thrown: bouncing the mail back to the prospect
    // because our backend blipped is far worse than losing a Worker log line.
    if (!response.ok) {
      console.error("SDR inbound rejected", response.status, await response.text());
    }
  },
};
```

Two details that matter:

- **The signed string is `{timestamp}.{body}`**, and the body must be the exact
  bytes sent. Re-serializing JSON anywhere between signing and sending breaks
  the signature.
- **Timestamp is seconds, not milliseconds.** The backend rejects anything more
  than 300 seconds old.

## 5. Wire it up

```bash
npx wrangler secret put SDR_INBOUND_WEBHOOK_SECRET   # paste the same value
npx wrangler deploy
```

Then **Email → Email Routing → Routing rules**, and send the reply address to
this Worker. Either:

- a catch-all rule → Worker (simplest), or
- a specific address (e.g. `replies@yourdomain.com`) → Worker.

If you use a specific address, set it in **AI SDR → Settings →
`reply_to_address`**. Until then it stays `None` and replies go to the From
identity — deliberately, because a `Reply-To` pointing at a mailbox that does
not exist bounces the prospect's answer.

## 6. Verify

```bash
# Should be 401 (signature missing) — NOT 503. A 503 means the secret is unset
# in Vercel, or you have not redeployed since setting it.
curl -i -X POST https://<your-backend>.vercel.app/api/public/sdr/webhooks/inbound \
  -H 'Content-Type: application/json' -d '{}'
```

Then send a real reply to a live thread and check **AI SDR → Inbox**. What you
should see:

| You reply with | Expected category | Expected effect |
|---|---|---|
| "Sounds interesting" | `interested` | sequence stops, lead marked replied |
| "Remove me" | `unsubscribe_request` | address suppressed permanently |
| an out-of-office | `out_of_office` | **sequence stays active**, next touch +7 days |

That third row is the one to check by hand. If an OOO stops the sequence, the
lead is stranded looking like a success and nobody will notice.

## 7. Failure modes

| Symptom | Cause |
|---|---|
| 503 | `SDR_INBOUND_WEBHOOK_SECRET` unset in Vercel, or set but not redeployed |
| 401 `invalid_signature` | Secret mismatch, or the body was re-serialized after signing |
| 401 `stale` | Worker clock skew, or milliseconds used instead of seconds |
| 400 `neither a Message-ID nor an id` | Parser dropped headers; check `postal-mime` version |
| 200 with `match_method: "none"` | Reply did not thread and the sender is unknown — stored for a human, visible in the Inbox |
| 200 with `match_method: "sender"` | Threading headers were stripped; matched by from-address and flagged for review |

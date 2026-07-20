# External services — what you need to provide

Built from the code, not from memory: every variable below is one the backend
actually reads (`os.environ` across `backend/**.py`), cross-checked against
what is currently set in Vercel.

**Free-tier bias throughout.** Everything the AI SDR module needs to run can
be free. The only unavoidable cost is a domain name, and the only thing that
is free-but-slow is the sending-domain warm-up.

> Quoted limits are what these providers advertised when this was written.
> Free tiers change often — check the current page before relying on a number.

---

## 1. Already set — nothing to do

Confirmed present in Vercel (Production + Preview):

| Variable | What it is |
|---|---|
| `MONGO_URL`, `DB_NAME` | MongoDB Atlas. **Password rotation still outstanding.** |
| `JWT_SECRET`, `VAULT_ENCRYPTION_KEY` | Signing and vault encryption |
| `ACCESS_EXPIRE_MIN` | Session lifetime — set to 60 |
| `RESEND_API_KEY`, `SENDER_EMAIL` | Outbound email |
| `GROQ_API_KEY`, `NVIDIA_API_KEY`, `NVIDIA_MODEL` | LLM chain (both free) |
| `CRON_SECRET` | Guards the drain endpoint |
| `FRONTEND_URL`, `BACKEND_URL`, `CORS_ORIGINS`, `ALLOWED_HOSTS` | Wiring |
| `COOKIE_SECURE`, `COOKIE_SAMESITE`, `APP_ENV` | Session behaviour |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | First-run admin seed |
| `CASHFREE_*` | Payments (unrelated to SDR) |
| `RUN_BACKGROUND_LOOPS`, `FILE_UPLOAD_DIR` | Runtime flags |

---

## 2. Needed to finish the AI SDR — all free

### 2.1 `SDR_INBOUND_WEBHOOK_SECRET` — **blocking inbound replies**

Not a third party. You generate it:

```bash
openssl rand -hex 32
```

Set the same value in Vercel **and** in the Cloudflare Worker
(`npx wrangler secret put SDR_INBOUND_WEBHOOK_SECRET`). Redeploy after — Vercel
only picks up env changes on a fresh deploy.

Until this exists the inbound endpoint returns 503 and **no reply is
processed**. That is deliberate: a forged reply can stop a sequence, mark a
lead as answered, and suppress an address permanently.

**Cost: free.**

### 2.2 Cloudflare Email Routing — **blocking inbound replies**

Routes mail for your sending domain to a Worker, which posts to the webhook.
Setup and Worker source: [`inbound-worker.md`](./inbound-worker.md).

Needs the domain's nameservers on Cloudflare. Workers free tier is generous
(100k requests/day) and inbound routing is free.

> **Ordering trap:** enabling Email Routing changes MX records. Do it
> **before** the sending-domain warm-up starts, not during — changing MX
> mid-warm-up resets sender reputation progress.

**Cost: free.**

### 2.3 `RESEND_WEBHOOK_SECRET` — **blocking delivery tracking**

Resend dashboard → Webhooks → add an endpoint pointing at
`/api/public/sdr/webhooks/resend`, then copy the signing secret.

Without it, bounces and complaints are never recorded: dead addresses stay in
rotation and spam complaints never suppress anyone. That is the fastest way to
burn a sending domain.

**Cost: free** (included with Resend).

### 2.4 An external pinger — **blocking everything**

Vercel has no long-running process, so the job queue only drains when
something calls `POST /api/sdr/jobs/drain` with the `CRON_SECRET`. Nothing
runs until this exists.

Free options, any one of them:

| Option | Notes |
|---|---|
| **cron-job.org** | Free, custom headers, 1-minute granularity. Simplest. |
| **GitHub Actions** cron | Free on public repos; private repos use included minutes. Minimum ~5 min, and scheduled runs can be delayed under load. |
| **Cloudflare Worker cron trigger** | Free, and you are already using Cloudflare for inbound. Fewest vendors. |
| Vercel Cron | Hobby plan allows one daily job — too coarse. Not viable here. |

Recommendation: **the Cloudflare Worker cron**, since that account already
exists for inbound mail.

The stalled-queue banner on the Agents page tells you if it dies.

### 2.5 A sending domain — **the long pole**

Not an API, but it gates going live and takes the longest. You need a domain
you control, verified in Resend with SPF/DKIM/DMARC, then a **~3-week warm-up**
ramping volume gradually.

Do not send from your main company domain until warm-up is done — a cold
domain sending cold email gets filtered, and reputation takes weeks to repair.

**Cost:** the domain (~$10–15/year). Everything else free.

---

## 3. Optional — improves things, none required

### 3.1 More LLM providers (free)

The chain already runs `groq → nvidia` and falls through automatically. Six
providers are supported; adding keys adds resilience when one rate-limits.
Set `SDR_LLM_PROVIDERS` to reorder.

| Provider | Variable | Note |
|---|---|---|
| Groq | `GROQ_API_KEY` | **set.** Fastest. |
| NVIDIA NIM | `NVIDIA_API_KEY` | **set.** Free credits. |
| Google Gemini | `GEMINI_API_KEY` | Free tier via AI Studio. Best value to add next. |
| Cerebras | `CEREBRAS_API_KEY` | Free tier, very fast. |
| OpenRouter | `OPENROUTER_API_KEY` | `:free` models cost nothing. Good last-resort fallback. |
| Mistral | `MISTRAL_API_KEY` | Free tier available. |

Adding **Gemini** and **OpenRouter** would give four independent fallbacks for
zero cost. Worth doing before launch.

### 3.2 Google Calendar OAuth — `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`

Google Cloud Console → OAuth 2.0 credentials. Redirect URI must be
`{FRONTEND_URL}/api/meetings/google/callback`.

**Not currently set.** Without it, meetings still work — bookings are recorded
and confirmation emails send — but nothing lands in a Google Calendar.

**Cost: free.** Note the OAuth consent screen needs verification before
external users can grant access; for internal use it can stay in testing mode.

### 3.3 `GOOGLE_PLACES_API_KEY` — lead discovery

**The one place a paid API appears.** Google Places gives richer business data
than the free alternative.

**You do not need it.** The module already uses **OpenStreetMap Overpass**,
which is free and unlimited, plus CSV import. Places is registered as an
optional provider and the chain skips it when the key is absent.

Google Cloud gives a recurring monthly credit that covers light use, but it is
a billing account with a card attached. **Recommendation: skip it.** Start
with OSM and CSV; add Places only if discovery quality proves limiting.

### 3.4 WhatsApp — `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ADMIN_NUMBER`

Meta Business verification plus per-template approval. **Weeks of lead time**,
like DNS warm-up, so start now if you want it this year.

`config/countries.py` already ranks WhatsApp above email for India, and the
sequencing engine does not assume email-first — but the channel provider is
not built, and building it before approval exists would be wasted work.

**Cost:** free tier of conversations per month; beyond that it is per
conversation. Verification itself is free but needs business documents.

### 3.5 A web-search provider — not configured, blocks one feature

Competitor analysis (deferred from Phase 4) needs one. The registry currently
holds OSM, Google Places and CSV import — those are *place* lookup, not web
search. Free-ish options: Brave Search API (free tier), SearXNG (self-hosted,
free), Tavily (free tier).

Nothing else depends on this. Configure one only if you want that feature.

---

## 4. Order to do them in

| # | Thing | Blocks | Cost | Time |
|---|---|---|---|---|
| 1 | **Rotate the Atlas password** | nothing, but it is exposed | free | minutes |
| 2 | Buy/choose the sending domain, verify in Resend | going live | ~$12/yr | hours |
| 3 | Cloudflare Email Routing + MX | inbound replies | free | ~30 min |
| 4 | **Warm-up starts** — do not send before | going live | free | **~3 weeks** |
| 5 | `SDR_INBOUND_WEBHOOK_SECRET` + Worker deploy | inbound replies | free | ~30 min |
| 6 | `RESEND_WEBHOOK_SECRET` | bounce handling | free | ~5 min |
| 7 | External pinger | everything | free | ~15 min |
| 8 | `GEMINI_API_KEY`, `OPENROUTER_API_KEY` | nothing | free | ~10 min |
| 9 | Google OAuth (calendar) | calendar events only | free | ~20 min |
| 10 | Start Meta/WhatsApp approval | WhatsApp | free | weeks |

Steps 2–4 are the critical path. **The 3-week warm-up clock does not start
until the DNS change is made**, so do that first even if everything else waits.

Total unavoidable spend: **one domain**. Everything else on this list is free.

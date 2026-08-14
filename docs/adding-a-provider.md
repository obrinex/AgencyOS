# Adding a provider

Two unrelated axes get called "adding an API". They are not the same job and
they do not cost the same.

| | LLM providers | Payment providers |
|---|---|---|
| Registry | `backend/llm_providers.py` | none - `cashfree` is imported directly |
| Call sites | 1 (`routers/ai.py`) | ~15 across 5 files |
| Cost of a new one | one dict entry, or an adapter | a refactor |

---

## LLM providers

### Gemini - already done

Gemini is in the registry. Set the key:

```
GEMINI_API_KEY=...
```

That is the whole change. With it set, Gemini joins the fallback chain in
`DEFAULT_ORDER` position 3, behind Groq and Cerebras (both faster, and their
limits reset per minute rather than per day). To put Gemini first:

```
LLM_PROVIDERS=gemini,groq,cerebras,nvidia
```

Verify at **AI Agents → Agent Monitor** - the provider card shows which keys
are set and the active chain order. `GEMINI_MODEL` overrides the model
(`gemini-2.0-flash` by default).

### OpenAI - one dict entry, already added

OpenAI speaks the same protocol as Gemini, Groq, Cerebras, NVIDIA, OpenRouter
and Mistral, so it is a table row and nothing else. Set `OPENAI_API_KEY` and
name it in `LLM_PROVIDERS`. `OPENAI_MODEL` overrides `gpt-4o-mini`.

### Claude - adapter, already added

Claude's API is genuinely different: the system prompt is a top-level argument
rather than a message, `max_tokens` is required, usage counts are named
`input_tokens`/`output_tokens`, and on Opus 4.8 a `temperature` argument is
**rejected with a 400**. The last one matters here because every existing call
site passes `temperature`.

`_AnthropicAdapter` in `providers.py` calls the official `anthropic` SDK and
normalises the result into the shape the rest of the codebase already reads,
dropping `temperature` on the way through. It is not the OpenAI client pointed
at Anthropic - that breaks on all four differences above.

One extra step, because the SDK is not bundled:

```
pip install anthropic          # and add `anthropic` to backend/requirements.txt
ANTHROPIC_API_KEY=...
LLM_PROVIDERS=anthropic,groq,gemini
```

It is deliberately not in `requirements.txt`: it is dead weight in every
Vercel cold start until someone actually opts in. If the key is set without
the package, the adapter raises an error naming this exact fix.

`ANTHROPIC_MODEL` overrides `claude-opus-4-8`. Opus is the default because
outreach copy quality is the one thing in this pipeline nobody has verified;
`claude-haiku-4-5` is the cheaper choice once volume matters more than prose.

### Why a paid key alone does nothing

`DEFAULT_ORDER` contains **only free providers**. OpenAI and Claude are absent
from it, so they are never reached by fallback - only when
`LLM_PROVIDERS` names them explicitly.

This is the point, not an oversight. The chain exists because free tiers
refuse requests; if a paid provider sat in it, "Groq is rate-limited" would
silently become a bill nobody chose. Two deliberate acts are required: set the
key, then name the provider. `test_no_paid_provider_can_be_reached_by_fallback`
pins it.

### Adding another OpenAI-protocol provider

One entry in `PROVIDERS`:

```python
"together": {
    "label": "Together AI",
    "protocol": OPENAI_PROTOCOL,
    "tier": "free",                       # or "paid"
    "base_url": "https://api.together.xyz/v1",
    "api_key_env": "TOGETHER_API_KEY",
    "default_model": "...",
    "model_env": "TOGETHER_MODEL",
    "free_note": "Shown in the monitor before a key is added.",
    "good_for": ["generation"],
},
```

Add to `DEFAULT_ORDER` only if `tier` is `free`. No other file changes.

---

## Payment providers - Razorpay

**There is no payment abstraction to extend.** `cashfree` is imported and
called directly from `routers/public.py` (11 sites), `routers/settings.py`,
`reminders.py`, `routers/automations.py` and `go_live_cashfree.py`. Concrete
types leak too: `cashfree.CashfreeError` is caught by name, and
`cashfree_link_id` is a field on stored invoice documents.

So adding Razorpay is not a config change. Roughly, in order:

1. **Extract the interface first, with Cashfree as the only implementation.**
   Five operations carry the whole surface: `create_payment_link`,
   `fetch_payment_link`, `fetch_settlement_rate`, `verify_webhook`,
   `supports_currency` - plus `is_configured()` / `environment()` for the
   settings page. Ship this with no behaviour change and confirm production is
   still taking payments before writing a line of Razorpay code.

2. **Rename the stored field.** `cashfree_link_id` on invoices has to become
   provider-agnostic (`payment_link_id` + `payment_provider`) with a
   backfill, or Razorpay invoices are unreadable by the reminder job. Do this
   as its own migration - see the `$nin` partial index incident behind index
   and schema changes against live billing data deserve their own blast radius.

3. **Then** add the Razorpay implementation.

Webhook verification is the part to be most careful with: Cashfree signs
`timestamp + raw_body` with HMAC-SHA256 base64, Razorpay signs the raw body
alone with hex digest. These are not interchangeable, and getting it wrong
means either rejecting real payments or accepting forged ones. The signature
check belongs in each implementation, never in shared code.

Worth saying plainly: **do not build this speculatively.** An unused payment
abstraction is pure risk on a live billing path. Extract it when Razorpay is
actually being added, not before.

---

## Where the seams are

- LLM: `backend/llm_providers.py` - `PROVIDERS`, `chain()`
- LLM callers: `routers/ai.py:_select_provider()`
- Payments: no seam yet; `backend/cashfree.py` is the thing to extract
- Tenancy: `repositories/base.scope()` - see

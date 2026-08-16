# Z.AI Research Lab Provider

ARKANA uses Z.AI only for explicit Owner-invoked research drafting and result
explanation. The API key is server-only and is never returned by the browser
routes, persisted in PostgreSQL, or logged.

Required local `.env` values:

```env
AI_ENABLED=true
AI_PROVIDER=zai
ZAI_API_KEY=<owner token>
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
AI_MODEL_FAST=glm-4.7
AI_MODEL_REASONING=glm-5.1
AI_REQUEST_LIMIT=100
```

`glm-4.7` is used for Hemat and `glm-5.1` for Lanjutan. There is no automatic
model substitution and no fallback to Meta. A provider `404`, `400`, or `422`
is reported as `MODEL_UNAVAILABLE` with the configured model name; `401/403`
is `AUTHENTICATION_FAILED`.

Z.AI JSON mode remains subject to ARKANA's own typed hypothesis and research
rule validation. AI drafts must still be owner-confirmed before deterministic
research. It cannot count patterns, make evidence, backtest, create a
strategy, deploy, or trade.

# AI Provider Configuration

ARKANA uses one server-side, provider-agnostic AI gateway. The AI provider is
optional and is never placed in the historical-analysis, backtest, or MT5
execution path.

## Tencent TokenHub / GLM 5.1

Use the owner-issued TokenHub API key only in the local `.env` file:

```dotenv
AI_ENABLED=true
AI_PROVIDER=tencent
AI_API_KEY=<TokenHub API key>
AI_BASE_URL=https://tokenhub-intl.tencentcloudmaas.com/v1
AI_PROTOCOL=openai_compatible
AI_ENDPOINT_PATH=/chat/completions
AI_AUTH_HEADER=Authorization
AI_AUTH_PREFIX="Bearer "
AI_EXTRA_HEADERS_JSON={}
AI_JSON_MODE=false
AI_THINKING_ENABLED=false
AI_MODEL_FAST=glm-5.1
AI_MODEL_REASONING=glm-5.1
```

Then recreate only the research service:

```bash
docker compose up -d --force-recreate research
```

`AI_JSON_MODE=false` intentionally matches the supplied TokenHub request
contract. ARKANA still requires the model to return parseable structured JSON;
malformed output is rejected instead of becoming an executable research rule.

## Other providers

OpenAI-compatible providers use `AI_PROTOCOL=openai_compatible` and configure
their base URL, endpoint path, auth header/prefix, optional extra headers, and
models. Native Anthropic Messages API is also supported with
`AI_PROTOCOL=anthropic_messages`, `/messages`, `x-api-key`, and an
`anthropic-version` extra header. A provider with another protocol needs a
small explicit adapter; it is never silently treated as compatible.

Provider/model metadata is persisted only as AI-draft provenance. API keys are
never returned by ARKANA APIs or sent to the web browser.

## Recommended free option: OpenRouter

OpenRouter provides `openrouter/free`, which selects an available free model
and uses the standard OpenAI-compatible chat-completions contract. It is a
reasonable low-volume temporary provider for ARKANA Research Lab; free-model
availability and rate limits are provider controlled.

For a stable structured-output workflow, ARKANA pins the verified free model
`openai/gpt-oss-20b:free` rather than relying on the random free router. If a
free-model response is not valid JSON, ARKANA makes at most one retry and then
rejects it; it never saves free text as a research definition.

```dotenv
AI_ENABLED=true
AI_PROVIDER=openrouter
AI_API_KEY=<OpenRouter API key>
AI_BASE_URL=https://openrouter.ai/api/v1
AI_PROTOCOL=openai_compatible
AI_ENDPOINT_PATH=/chat/completions
AI_AUTH_HEADER=Authorization
AI_AUTH_PREFIX="Bearer "
AI_EXTRA_HEADERS_JSON={}
AI_JSON_MODE=true
AI_THINKING_ENABLED=false
AI_MODEL_FAST=openai/gpt-oss-20b:free
AI_MODEL_REASONING=openai/gpt-oss-20b:free
AI_REQUEST_LIMIT=20
```

## Alternative free option: Groq

Groq also exposes an OpenAI-compatible endpoint and publishes free-plan rate
limits. Select an available model from its console, then configure its base URL
as `https://api.groq.com/openai/v1` with the same OpenAI-compatible protocol.

# Sprint 10 — AI Research Assistant Optimization

**Status: IMPLEMENTATION COMPLETE — OWNER AI PROVIDER OAT DEFERRED.**

## 1. Goal

Add an optional, auditable, cost-controlled AI assistant to help the owner express research questions and understand already-computed ARKANA evidence. It improves the research conversation; it does not become a data source, analytics engine, strategy author, or execution component.

The existing deterministic parser remains the first route. A provider call is only a deliberate fallback for a question that deterministic routing cannot interpret, or an explicit owner request to explain a saved deterministic result.

## 2. Actual baseline and architecture fit

- `services/research/app/hypotheses.py` already provides deterministic parsing for known question classes and persists `parser_source` as `DETERMINISTIC` or `NONE`.
- `ResearchHypothesis` and ADR-006/ADR-007 already separate question interpretation, typed schema validation, availability assessment, and execution eligibility.
- Historical OHLC computation, discovery, similarity, research runs, and backtests are already deterministic and fingerprinted. The registered production dataset is MT5 XAUUSD OHLC with `UNVERIFIED_BROKER_TIME`.
- There is currently **no** LLM provider SDK, credential, model call, prompt store, cost ledger, or AI API endpoint.
- The implementation belongs in the existing FastAPI research service and Next.js BFF/UI. It does not require Redis, Kafka, a new microservice, or new trading infrastructure.

## 3. Exact scope

### A. Deterministic-first routing

1. Preserve all existing deterministic routes without a provider call.
2. For unresolved/open questions, show the deterministic clarification state first.
3. Offer an explicit owner action, for example **“Bantu merumuskan pertanyaan”** or **“Jelaskan hasil ini”**. There is no automatic background escalation.
4. Classify every response as `DETERMINISTIC`, `AI_ASSISTED`, `AI_UNAVAILABLE`, `AI_BLOCKED_BY_POLICY`, or `CACHE_HIT` for audit. These are assistant-route records, not replacements for hypothesis/eligibility status.

### B. AI-assisted hypothesis drafting

The assistant may transform a user question into a proposed typed hypothesis draft or a concise clarification request. Before persistence, ARKANA must:

- validate the returned JSON against the existing mode-specific schema;
- run the existing data/capability registry assessment;
- display the entire editable draft and its availability/eligibility truthfully;
- require the owner to save the draft explicitly.

Invalid, unsupported, or unsafe output produces a non-executable clarification result; it must never silently produce a research run.

### C. AI-assisted result explanation

The assistant may explain a selected, already-saved research, discovery, similarity, or backtest result using a compact, structured local summary. It may explain limitations, support, train/holdout distinctions, and propose non-executable follow-up research questions.

Every explanation must state that it is an interpretation of deterministic evidence and link back to the run/result fingerprint or identifier used as context.

### D. Audit and cost visibility

Persist a minimal AI interaction audit record: owner action type, sanitized input fingerprint, prompt-template version, provider/model identifier, response status, cache status, input/output token counts when supplied by provider, estimated cost when pricing is configured, latency, and created time. Do not persist provider API keys. Avoid retaining full user prose unless the owner has explicitly chosen local audit retention; a fingerprint plus the existing saved hypothesis/run is normally sufficient.

Provide an owner-facing **AI Usage** view with current enabled state, configured provider/model aliases, request count, cache-hit count, token/cost totals where available, and clear `NOT_REPORTED` when the provider does not supply usage data.

## 4. AI/LLM boundaries

### The assistant may

- draft or clarify a research hypothesis;
- summarize and explain deterministic, locally-computed result summaries;
- identify missing data/capability already reported by ARKANA;
- suggest optional follow-up research questions.

### The assistant must not

- receive raw OHLC, tick, Bid/Ask, or full historical datasets;
- calculate or invent historical statistics, support, PnL, MFE/MAE, or causal claims;
- alter deterministic computation, fingerprints, data quality, or timezone semantics;
- override availability assessment, execution eligibility, approval, or DEMO-only policy;
- create a strategy, approve a version, create a backtest, deploy to MT5, or send a configuration;
- issue BUY/SELL instructions, choose a realtime trade, or be invoked from MT5/`OnTick`;
- enable LIVE trading or automatic live promotion.

## 5. Provider and model requirements

Sprint 10 is provider-agnostic. No provider or model is selected in the current repository; an owner selection is required at implementation time.

An approved provider/model combination must support:

1. server-side HTTPS API access with credentials stored only in server environment variables/secrets;
2. reliable structured JSON/schema output or a response format that ARKANA can validate strictly before use;
3. a documented model identifier/version and usage reporting where available;
4. an owner-acceptable data-retention/privacy policy for compact prompts; raw market data is excluded regardless;
5. explicit timeout, retry, and failure semantics without affecting research/EA availability;
6. independently configurable low-cost and escalation model aliases.

Proposed configuration contract (names are not yet implemented):

```text
AI_ENABLED=false
AI_PROVIDER=<owner-approved provider>
AI_API_KEY=<server secret; never NEXT_PUBLIC_*>
AI_MODEL_FAST=<low-cost structured-output model>
AI_MODEL_REASONING=<optional stronger model>
AI_MONTHLY_BUDGET_USD=<owner-set hard ceiling>
AI_REQUEST_MAX_INPUT_TOKENS=4000
AI_REQUEST_MAX_OUTPUT_TOKENS=800
AI_REQUEST_MAX_COST_USD=0.05
```

The default is disabled. A provider outage, invalid key, unsupported model, or exhausted budget returns an honest unavailable/budget result and preserves the deterministic workflow.

## 6. Cost-control strategy

1. **Deterministic first:** known intents never call a model.
2. **Explicit owner action:** no automatic AI call while typing, opening a chart, refreshing discovery, or loading a result.
3. **Compact context only:** send schema, user question, selected result summary, IDs/fingerprints, and documented limitations—not bar arrays, tick data, sample histories, or database dumps.
4. **Two model lanes:** fast/low-cost by default; optional stronger lane only for a clearly labeled owner escalation.
5. **Strict budgets:** per-request input/output caps, provider timeout, monthly hard ceiling, and optional owner-confirmed override—not silent overage.
6. **Fingerprint cache:** cache the sanitized request fingerprint + prompt-template version + model alias + compact-context fingerprint in PostgreSQL. A cache hit returns the exact prior validated response without a provider call. No Redis is needed.
7. **Observable spend:** usage/cost is persisted when provided; otherwise show `NOT_REPORTED`, never a fabricated estimate.

## 7. Out of scope

- RAG/vector database, embeddings, agent orchestration, autonomous background research, batch provider jobs, or multi-provider marketplace;
- external news/macro ingestion or using the model as a substitute for them;
- sending data to an LLM for feature generation, discovery, similarity, or backtest computation;
- strategy code generation, MQL generation, automatic strategy promotion, or any execution change;
- changes to Sprint 06–09 methodology, config contracts, EA logic, deployment, or Command Center telemetry.

## 8. Acceptance criteria

1. Known deterministic question creates the same deterministic draft and records no provider request.
2. With `AI_ENABLED=false`, assistant controls explain that AI is disabled and no outbound request is made.
3. An explicit AI request produces only schema-valid editable draft/clarification or a safe failure state.
4. Existing availability assessment and `execution_eligibility` are always applied after AI drafting.
5. Explanation requests receive only compact calculated summaries; automated contract tests prove raw bar/tick arrays are excluded.
6. Identical valid request/context/model/template returns a cache hit without a new provider call.
7. Budget exhaustion, timeout, malformed JSON, and provider failure are honest and leave hypotheses, strategies, deployments, and EA state unchanged.
8. Usage audit exposes provider/model alias, cache state, token/cost when supplied, and `NOT_REPORTED` otherwise.
9. No AI endpoint is reachable from MT5 or invoked in the realtime execution/deployment path.
10. Python/API tests, frontend tests, lint, typecheck, and production build pass. Real provider calls are owner acceptance only and must use a constrained test key/budget.

## 9. Owner Acceptance Test plan

1. Start with `AI_ENABLED=false`. Open Research Lab and submit a known existing question; confirm its deterministic result and no AI usage record.
2. Try an open question and select the optional assistant action; confirm the UI clearly says AI is disabled and creates no strategy/run/deployment.
3. Configure the owner-approved provider with a minimal test budget and submit the same open question deliberately. Confirm a clearly labeled **AI-assisted draft** or clarification appears, not an automatic saved hypothesis.
4. Inspect/edit the draft, then save only if desired. Confirm data/capability assessment and eligibility remain ARKANA-determined.
5. Request an explanation of a saved Sprint 09 result. Confirm it references the result/fingerprint, uses historical-evidence wording, contains no BUY/SELL recommendation, and does not expose raw OHLC rows.
6. Repeat the identical request. Confirm `CACHE_HIT` and no additional provider usage.
7. Set a deliberately tiny budget or temporarily invalidate the key. Confirm a clear unavailable/budget message and no impact on EA, deployment, strategy approval, or existing research.
8. Open Command Center and keep the DEMO EA running while the provider is unavailable. Confirm telemetry/EA behavior remains unaffected.

## 10. Roadmap impact

Sprint 10 does not change the accepted Sprint 09 research methodology or any execution behavior. It adds an optional interpretation layer only. Sprint 11 remains Demo Validation & Live Readiness Assessment and cannot begin by treating AI output as evidence, strategy approval, or live-readiness approval. Historical Bid/Ask precision validation, verified sessions, and external data remain separate owner-approved future capabilities.

## 11. Implementation record

Implemented in the existing FastAPI service and Next.js BFF/UI:

- `services/research/app/ai_gateway.py`: optional OpenAI-compatible structured-output adapter, deterministic fingerprint cache, server-side key use, timeout/safe failure, owner budget reservation, and compact-only prompts.
- `AIInteraction` / migration `008_ai_interactions.sql`: request fingerprint, route status, provider/model alias, token usage where supplied, reserved estimated cost, latency, and response audit. Raw owner prompt is represented by a hash rather than persisted in this audit record.
- API: `GET /api/v1/ai/usage`, `POST /api/v1/ai/draft`, and `POST /api/v1/ai/explanations/research-runs/{id}`. Explanation context is the saved run result only; raw sample/bar arrays are excluded.
- Research Lab: explicit **Bantu merumuskan (AI)** and **Jelaskan hasil ini (AI)** actions plus an AI usage status card. Normal **Build interpretation** remains deterministic.
- Docker/.env contract now passes AI server-only settings to the Research container. Defaults are `AI_ENABLED=false` and a zero monthly budget.

The provider endpoint must expose an OpenAI-compatible `/chat/completions` structured JSON response for this initial adapter. No real provider call was made during workspace verification; provider/key/budget behaviour is an Owner Acceptance step.

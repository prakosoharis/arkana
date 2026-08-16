# ARKANA product boundaries

ARKANA is a trading research and command-center application, not an autonomous
trading system.

- ARKANA Web/API performs research, audit, configuration, and visibility.
- MT5 EA owns real-time execution; never place web/API/LLM calls in `OnTick`.
- An LLM may draft or explain research only. It is never historical evidence,
  a trading signal, an approval authority, or a live-execution dependency.
- New strategies require owner approval and DEMO validation before any LIVE
  consideration. LIVE remains locked unless explicitly scoped by the owner.
- Preserve `BACKTEST V1 = COMPLETE / LOCKED`; do not refactor it incidentally.

Prefer the smallest change that solves the stated task. Do not invent market
data, repair gaps silently, infer broker sessions/timezones, or expose secrets.

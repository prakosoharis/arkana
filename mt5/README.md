# ARKANA MT5 Execution Prototype

`Experts/ARKANA_ENGINE.mq5` is one generic EA for the Sprint 05 registered `BULLISH_REVERSAL_M1` configuration. It runs independently of ARKANA Web after it has read a valid local configuration.

## Safety boundaries

- It refuses any account other than `ACCOUNT_TRADE_MODE_DEMO` at initialization and on every M1 evaluation.
- It never calls HTTP, the web API, a database, or an LLM from `OnTick`.
- A malformed reload keeps the last valid configuration; no valid configuration means no trade.
- `ARKANA_EMERGENCY_STOP=1` as an MT5 global variable blocks new entries. It does not force-close positions.
- `enabled=false` is the default. Sprint 07 adds approved DEMO config sync and acknowledgement; the EA's realtime path remains local and independent of the web/API.

## Local owner acceptance (MetaTrader 5 demo terminal)

1. In MetaEditor, open and compile `Experts/ARKANA_ENGINE.mq5`; compilation must have zero errors.
2. In MT5, choose a **demo** account and open an M1 chart whose exact symbol matches `broker_symbol` in the config.
3. On macOS, attach the EA once with `enabled=false`, then open the **Experts** tab (or Journal) in MT5. Copy the exact path printed after `ARKANA strategy.ini is missing. Copy a disabled config to:`. MT5's macOS menu may not expose **File → Open Common Data Folder**.
4. The EA automatically creates its safe `FILE_COMMON/ARKANA` folder. It does **not** create a config file or enable trading. Copy `strategy.ini.example` to the exact printed path and rename it `strategy.ini`.
5. Attach the EA with AutoTrading disabled first. Confirm `telemetry.csv` appears in the same common `Files/ARKANA` folder and records `CONFIG_LOADED`/`HEARTBEAT`.
6. Confirm attaching to a live account fails. Do not bypass this guard.
7. Set `enabled=true` only on a demo account after checking volume, stop/target, and max spread values. Test `ARKANA_EMERGENCY_STOP=1` in MT5 Global Variables and confirm new entries are blocked.

The example is a disabled, checksum-valid local prototype input. For deployment, ARKANA generates the config and checksum; do not edit the generated file manually.
# Incremental historical collector (macOS)

For hourly research-data freshness, compile and attach `ARKANA_DATA_COLLECTOR` to any
`XAUUSD.m` chart. It is a non-trading Expert Advisor: it only polls
`FILE_COMMON/ARKANA/historical/requests/` on its timer and writes completed M1 CSV
responses under `FILE_COMMON/ARKANA/historical/increments/`. Keep AutoTrading disabled
if you are only running this collector. It does not use `OnTick`, place orders, or alter
`ARKANA_ENGINE` configuration.

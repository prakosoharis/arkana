# Local Development Status

This handoff package contains ARKANA specifications and a UI reference, not a runnable ARKANA application. There are no frontend/backend commands, package manifest, environment template, database, dataset, MT5 EA, Docker configuration, or automated test configuration to run.

To review the static prototype only:

```bash
cd /Users/investree/Documents/project/trade/ARKANA_Codex_Handoff_v1
python3 -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/ui-reference/ARKANA_Trading_Intelligence_UI_v2.html`, then stop the server with `Ctrl-C`. Its chart, prices, EA state, positions, backtest, and deployment values are dummy prototype data, not ARKANA services.

See [CURRENT_STATE.md](CURRENT_STATE.md) for the audited inventory, unavailable checks, and prerequisites for a real local startup.

"use client";

import Link from "next/link";
import React, { useState } from "react";

type Trade = { entry_timestamp: string; exit_timestamp: string; entry_price: number; exit_price: number; exit_reason: string; net_pnl_price: number; mae_price: number; mfe_price: number };
type Backtest = { id: string; fingerprint: string; reused: boolean; configuration: Record<string, number | string>; result: { metrics: Record<string, number | string | null>; split: { split_timestamp: string | null; in_sample: Record<string, number | string | null>; out_of_sample: Record<string, number | string | null> }; walk_forward: { available: boolean; reason?: string | null }; cost_sensitivity: Record<string, { net_pnl_price: number; trade_count: number }>; warning: string }; trades: Trade[] };

const initial = { stop_distance: 0.10, target_distance: 0.10, spread_price: 0.02, commission_price: 0 };
const readable = (key: string) => key.replaceAll("_", " ");
const display = (value: number | string | null) => value === null ? "—" : typeof value === "number" ? value.toFixed(4) : value;

export function BacktestLab() {
  const [config, setConfig] = useState(initial);
  const [run, setRun] = useState<Backtest | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const update = (key: keyof typeof initial, value: number) => setConfig((current) => ({ ...current, [key]: value }));

  async function execute() {
    setBusy(true); setMessage("");
    try {
      const response = await fetch("/api/v1/backtests", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(config) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Backtest failed.");
      setRun(body); setMessage(body.reused ? "Identical inputs were reused from the recorded backtest run." : "Backtest completed against the registered M1 dataset.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Backtest failed."); }
    finally { setBusy(false); }
  }

  return <main className="backtest-page"><header><div><Link className="back-link" href="/research">← Research Lab</Link><h1>Backtest Lab</h1><p>Deterministic broad M1 experiment. This cannot activate a strategy or place a trade.</p></div><span className="mode-badge">M1 · STOP FIRST</span></header><section className="backtest-content"><div className="backtest-grid"><section className="panel backtest-config"><h2>Registered candidate</h2><p className="muted"><strong>BULLISH REVERSAL M1</strong><br />Bearish candle → bullish candle, then long at the next M1 open. Every value below is an explicit XAUUSD price unit.</p><div className="backtest-form">{Object.entries(config).map(([key, value]) => <label key={key}>{readable(key)}<input aria-label={readable(key)} type="number" min="0" step="0.01" value={value} onChange={(event) => update(key as keyof typeof initial, event.target.valueAsNumber)} /></label>)}</div><div className="policy"><strong>Locked execution assumptions</strong><span>Long entry: next M1 open + spread</span><span>When SL and TP both occur inside one M1 candle: stop first</span><span>Precision Bid/Ask tick validation: unavailable (no registered tick dataset)</span></div><button className="run-button" disabled={busy} onClick={execute}>{busy ? "Running…" : "Run deterministic backtest"}</button></section><section className="panel backtest-info"><h2>Guardrails</h2><p>Results are historical price-unit simulation only. They do not account for position size, leverage, financing, slippage, or live execution quality.</p><p>No strategy record, approval, deployment, MT5 configuration, or trading instruction is created here.</p><p>Fingerprint includes the dataset, candidate version, all costs, price parameters, M1 resolution, and ambiguity policy.</p></section></div>{message && <p className="notice">{message}</p>}{run && <section className="panel result-panel"><div className="panel-header"><div><h2>Recorded result</h2><p>Run {run.id.slice(0, 8)} · fingerprint {run.fingerprint.slice(0, 12)} · {run.reused ? "reused" : "new"}</p></div><span className="mode-badge">EXPERIMENT ONLY</span></div><p className="warning-line">{run.result.warning}</p><MetricGrid title="Overall metrics" metrics={run.result.metrics} /><div className="split-grid"><MetricGrid title={`In sample (before ${run.result.split.split_timestamp ?? "—"})`} metrics={run.result.split.in_sample} /><MetricGrid title="Out of sample" metrics={run.result.split.out_of_sample} /></div><section className="cost-table"><h2>Cost sensitivity</h2><table><thead><tr><th>Spread multiplier</th><th>Trades</th><th>Net price PnL</th></tr></thead><tbody>{Object.entries(run.result.cost_sensitivity).map(([multiple, metrics]) => <tr key={multiple}><td>{multiple}×</td><td>{metrics.trade_count}</td><td>{metrics.net_pnl_price.toFixed(4)}</td></tr>)}</tbody></table><p className="muted">Walk-forward: {run.result.walk_forward.available ? "available" : run.result.walk_forward.reason}</p></section><section className="trade-table"><h2>Trade ledger</h2>{run.trades.length ? <table><thead><tr><th>Entry</th><th>Exit</th><th>Reason</th><th>Net PnL</th><th>MAE / MFE</th></tr></thead><tbody>{run.trades.map((trade, index) => <tr key={`${trade.entry_timestamp}-${index}`}><td>{trade.entry_timestamp}<br />{trade.entry_price.toFixed(3)}</td><td>{trade.exit_timestamp}<br />{trade.exit_price.toFixed(3)}</td><td>{trade.exit_reason}</td><td>{trade.net_pnl_price.toFixed(4)}</td><td>{trade.mae_price.toFixed(4)} / {trade.mfe_price.toFixed(4)}</td></tr>)}</tbody></table> : <p className="muted">No qualifying entries occurred for the selected data and candidate.</p>}</section></section>}</section></main>;
}

function MetricGrid({ title, metrics }: { title: string; metrics: Record<string, number | string | null> }) {
  return <section className="metric-block"><h2>{title}</h2><div className="metric-grid">{Object.entries(metrics).map(([key, value]) => <article key={key}><small>{readable(key)}</small><strong>{display(value)}</strong></article>)}</div></section>;
}

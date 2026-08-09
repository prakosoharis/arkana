"use client";

import Link from "next/link";
import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { CandlestickChart } from "./candlestick-chart";
import { type BarsResponse, type Dataset, displayTime, TIMEFRAMES, type Timeframe } from "../lib/market";

const disabledLive = ["Live Decision", "Positions"];
const disabledStrategies = ["Demo Deployment"];
const disabledSystem = ["Journal", "Settings"];

export function MarketDataWorkspace() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [timeframe, setTimeframe] = useState<Timeframe>("M1");
  const [bars, setBars] = useState<BarsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const registry = await fetch("/api/v1/datasets", { cache: "no-store" });
      if (!registry.ok) throw new Error("Market-data service is unavailable.");
      const payload = await registry.json() as { datasets: Dataset[] };
      setDatasets(payload.datasets);
      const response = await fetch(`/api/v1/bars?symbol=XAUUSD&timeframe=${timeframe}&limit=1000`, { cache: "no-store" });
      if (!response.ok) throw new Error((await response.json()).detail ?? "Cannot load bars.");
      setBars(await response.json() as BarsResponse);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unknown error");
      setBars(null);
    } finally { setLoading(false); }
  }, [timeframe]);

  useEffect(() => { void load(); }, [load]);

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportStatus("Importing and deriving timeframes…"); setError(null);
    const form = new FormData(); form.set("file", file);
    const response = await fetch("/api/v1/imports/csv?symbol=XAUUSD&source=MT5_CSV&timezone_status=UNVERIFIED_BROKER_TIME", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) { setError(payload.detail ?? "Import failed."); setImportStatus(null); return; }
    setImportStatus(payload.already_imported ? "Already imported: identical file reused." : "Import complete: Parquet and derived timeframes are ready.");
    await load();
  }

  const dataset = datasets.find((item) => item.symbol === "XAUUSD");
  const meta = bars?.meta;
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span>△</span><div><strong>ARKANA</strong><small>TRADING INTELLIGENCE</small></div></div>
      <p className="section-label">LIVE</p>{disabledLive.map((item) => <button className="nav disabled" disabled key={item}>{item}</button>)}
      <p className="section-label">RESEARCH</p><Link className="nav" href="/research">Research Lab</Link><Link className="nav" href="/backtest">Backtest Lab</Link>
      <p className="section-label">STRATEGIES</p><Link className="nav" href="/strategies">Strategy Library</Link>{disabledStrategies.map((item) => <button className="nav disabled" disabled key={item}>{item}</button>)}
      <p className="section-label">SYSTEM</p><button className="nav active">▦ Market &amp; Data</button>{disabledSystem.map((item) => <button className="nav disabled" disabled key={item}>{item}</button>)}
      <div className="safety"><strong>RESEARCH MODE</strong><small>No MT5 feed or trading execution in Sprint 01.</small></div>
    </aside>
    <main><header><div><h1>Market &amp; Data</h1><p>Historical XAUUSD from imported files. No synthetic fallback candles.</p></div><label className="import"><input type="file" accept=".csv,text/csv" onChange={importCsv} />Import MT5 CSV</label></header>
      <section className="content">
        {importStatus && <p className="notice">{importStatus}</p>}{error && <p className="error">{error}</p>}
        <div className="cards">
          <article><small>Dataset status</small><strong>{dataset ? "READY" : "NO DATA"}</strong><span>{dataset ? dataset.symbol : "Import an XAUUSD M1 CSV"}</span></article>
          <article><small>Source</small><strong>{dataset?.source ?? "—"}</strong><span>Processed as Parquet</span></article>
          <article><small>Timezone</small><strong>{dataset?.timezone_status ?? "UNKNOWN"}</strong><span>No timestamp conversion by assumption</span></article>
          <article><small>Imported</small><strong>{displayTime(dataset?.imported_at)}</strong><span>Metadata stored in PostgreSQL</span></article>
        </div>
        <div className="panel"><div className="panel-header"><div><h2>Historical chart</h2><p>{meta?.status === "READY" ? `${meta.source} · ${meta.timezone_status}` : "No data available"}</p></div><div className="timeframes">{TIMEFRAMES.map((item) => <button className={item === timeframe ? "selected" : ""} key={item} onClick={() => setTimeframe(item)}>{item}</button>)}</div></div>
          {loading ? <div className="state">Loading historical bars…</div> : error ? <div className="state error">Cannot load data.</div> : bars?.bars.length ? <><CandlestickChart bars={bars.bars} /><footer>Visible range: {displayTime(meta?.range_start)} — {displayTime(meta?.range_end)} · {bars.bars.length} bars returned</footer></> : <div className="state">No data. Import an MT5-compatible XAUUSD M1 CSV to view real candles.</div>}
        </div>
        <div className="panel"><h2>Dataset registry</h2>{dataset ? <table><thead><tr><th>Timeframe</th><th>Rows</th><th>Start</th><th>End</th></tr></thead><tbody>{dataset.timeframes.map((item) => <tr key={item.timeframe}><td>{item.timeframe}</td><td>{item.row_count.toLocaleString()}</td><td>{displayTime(item.range_start)}</td><td>{displayTime(item.range_end)}</td></tr>)}</tbody></table> : <p className="muted">No registered dataset.</p>}</div>
      </section>
    </main>
  </div>;
}

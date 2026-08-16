"use client";

import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { CandlestickChart } from "./candlestick-chart";
import { type BarsResponse, type Dataset, displayBrokerTime, displayTime, TIMEFRAMES, type Timeframe } from "../lib/market";


export function MarketDataWorkspace() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [timeframe, setTimeframe] = useState<Timeframe>("M1");
  const [bars, setBars] = useState<BarsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [mt5Status, setMt5Status] = useState<{status:string;broker_symbol?:string;timezone_status?:string;source?:string;latest_market_timestamp?:string|null;last_successful_sync_at?:string|null;next_scheduled_sync_at?:string|null;pending_request?:{request_id:string;requested_from_timestamp:string}|null;error?:string}|null>(null);

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
  useEffect(() => { fetch("/api/v1/mt5-historical/status").then(r=>r.json()).then(setMt5Status).catch(()=>setMt5Status({status:"FAILED",error:"MT5 acquisition service unavailable"})); }, []);

  async function syncMt5(){setImportStatus("Requesting only missing completed M1 candles from MT5…");const r=await fetch("/api/v1/mt5-historical/sync",{method:"POST"});const b=await r.json();setImportStatus(r.ok?(b.status==="AWAITING_MT5"?`Menunggu collector MT5 · mulai ${b.requested_from_timestamp}`:`Historical data ${b.status} · ${b.added_m1_rows??0} M1 candle baru`):b.detail??"MT5 historical sync failed");await load();setMt5Status(await (await fetch("/api/v1/mt5-historical/status")).json());}

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
  const visibleStart = bars?.bars[0]?.timestamp; const visibleEnd = bars?.bars[bars.bars.length - 1]?.timestamp;
  return <><header><div><h1>Market &amp; Data</h1><p>Historical XAUUSD from registered MT5 data. No synthetic fallback candles.</p></div></header>
      <section className="content">
        {importStatus && <p className="notice">{importStatus}</p>}{error && <p className="error">{error}</p>}
        <div className="cards">
          <article><small>Dataset status</small><strong>{dataset ? "READY" : "NO DATA"}</strong><span>{dataset ? dataset.symbol : "Import an XAUUSD M1 CSV"}</span></article>
          <article><small>Source</small><strong>{dataset?.source ?? "—"}</strong><span>Processed as Parquet</span></article>
          <article><small>Timezone</small><strong>{dataset?.timezone_status ?? "UNKNOWN"}</strong><span>No timestamp conversion by assumption</span></article>
          <article><small>Last successful sync</small><strong>{displayTime(mt5Status?.last_successful_sync_at)}</strong><span>{mt5Status?.last_successful_sync_at ? "Service time" : "Belum ada incremental sync yang berhasil"}</span></article>
        </div>
        <div className="panel"><div className="panel-header"><div><h2>MT5 / Data Connection</h2><p>Hourly incremental research sync. Trading and ARKANA_ENGINE remain separate.</p></div><button className="secondary" onClick={syncMt5}>Sync Now</button></div><div className="metric-block"><p><strong>{mt5Status?.status??"LOADING"}</strong> · Source: {mt5Status?.source??"MT5"} · Broker symbol: {mt5Status?.broker_symbol??"XAUUSD.m"}</p><p>Latest market data (broker time): <strong>{displayBrokerTime(mt5Status?.latest_market_timestamp)}</strong></p><p>Last successful sync (service time): <strong>{displayTime(mt5Status?.last_successful_sync_at)}</strong> · Next automatic sync: <strong>{displayTime(mt5Status?.next_scheduled_sync_at)}</strong></p><p>Timezone: <strong>{mt5Status?.timezone_status??"UNVERIFIED_BROKER_TIME"}</strong> — no UTC or session assumption.</p>{mt5Status?.pending_request&&<p className="muted">MT5 request {mt5Status.pending_request.request_id.slice(0,8)} pending from {mt5Status.pending_request.requested_from_timestamp}.</p>}{mt5Status?.error&&<p className="error">{mt5Status.error}</p>}</div><details className="discovery-advanced"><summary>Data Management</summary><p className="muted">Initial bootstrap/recovery only: run ARKANA_HISTORICAL_EXPORTER in MT5, then import its full snapshot below. Regular use is Sync Now or the automatic hourly collector.</p><label className="import"><input type="file" accept=".csv,text/csv" onChange={importCsv} />Import MT5 CSV</label></details></div>
        <div className="panel"><div className="panel-header"><div><h2>Historical chart</h2><p>{meta?.status === "READY" ? `${meta.source} · ${meta.timezone_status}` : "No data available"}</p></div><div className="timeframes">{TIMEFRAMES.map((item) => <button className={item === timeframe ? "selected" : ""} key={item} onClick={() => setTimeframe(item)}>{item}</button>)}</div></div>
          {loading ? <div className="state">Loading historical bars…</div> : error ? <div className="state error">Cannot load data.</div> : bars?.bars.length ? <><CandlestickChart bars={bars.bars} /><footer>Visible chart range: {displayBrokerTime(visibleStart)} — {displayBrokerTime(visibleEnd)} · latest {bars.bars.length} bars returned. Dataset coverage: {displayBrokerTime(meta?.range_start)} — {displayBrokerTime(meta?.range_end)}.</footer></> : <div className="state">No data. Import an MT5-compatible XAUUSD M1 CSV to view real candles.</div>}
        </div>
        <div className="panel"><h2>Dataset registry</h2>{dataset ? <><p className="muted">Dataset bootstrap registered: {displayTime(dataset.imported_at)}. Ini metadata awal, bukan waktu Sync Now terakhir.</p><table><thead><tr><th>Timeframe</th><th>Rows</th><th>Start</th><th>End</th></tr></thead><tbody>{dataset.timeframes.map((item) => <tr key={item.timeframe}><td>{item.timeframe}</td><td>{item.row_count.toLocaleString()}</td><td>{displayBrokerTime(item.range_start)}</td><td>{displayBrokerTime(item.range_end)}</td></tr>)}</tbody></table></> : <p className="muted">No registered dataset.</p>}</div>
      </section>
    </>;
}

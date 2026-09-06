"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";

/**
 * ARK-S28-02. The Owner's own experiment, runnable by the Owner.
 *
 * Every number here is the answer to one question: after price met the line,
 * did it reach the profit distance first, the loss distance first, or neither
 * in the time allowed? The four ways a bar can meet a line are always shown
 * together, because the interesting one cannot be known in advance.
 */

type Row = {
  event: string;
  distance: string;
  timeout_bars: number;
  regime: string;
  break_even_rate: number;
  edge: number | null;
  baseline_rate: number | null;
  baseline_resolved: number;
  edge_over_baseline: number | null;
  events: number;
  target_first: number;
  stop_first: number;
  unresolved: number;
  beyond_data: number;
  target_rate: number | null;
  target_rate_of_resolved: number | null;
  median_bars_to_target?: number | null;
  median_bars_to_stop?: number | null;
  year?: number;
  month?: string;
};

type Probe = {
  fingerprint: string;
  reused: boolean;
  touches: number;
  spec: { timeframe: string; level: { kind: string; period: number }; spread_price: number; splits: string[]; coverage: string; trend: { lookback: number; threshold_percent: number } };
  policy: { coverage: string; coverages: string[]; readable_splits: string[]; ambiguity: string; entry: string };
  respect: Respect;
  geometry: { target_multiple: number; break_even_rate: number; note: string; spread_price: number; baseline_samples: number; spread_cost_points: Record<string, number>; baseline_note: string };
  warning: string;
  asset: { timeframe: string; registered_row_count: number; measured_row_count: number };
  coverage: { bars: number; start: string | null; end: string | null; touches: Record<string, number>; touches_total: number };
  summary: Row[];
  per_year: Row[];
  per_month: Row[];
};

type Side = { touches: number; bounced: number; broke: number; respect_rate: number | null };
type Respect = Record<string, { BUY: Side; SELL: Side }>;
type ScanRow = { kind: string; period: number; respect: Respect };
type Scan = { rows: ScanRow[]; coverage: { bars: number; start: string | null; end: string | null }; warning: string; reused: boolean };

type Options = { level_kinds: string[]; coverages?: string[]; timeframes: Array<{ timeframe: string; rows: number }> };

// ARK-S30-02. The Owner's hypothesis, made selectable: a moving average is
// support while it rises and resistance while it falls, and means nothing while
// it is flat. "Semua" stays beside the three, because a split without its own
// control is a number nobody can check.
const REGIMES = [
  { id: "SEMUA", label: "Semua kondisi" },
  { id: "NAIK", label: "Saat garis naik" },
  { id: "DATAR", label: "Saat garis datar" },
  { id: "TURUN", label: "Saat garis turun" },
] as const;

type RegimeId = (typeof REGIMES)[number]["id"];

/** The most respected lines for one side, under one regime, thin rows dropped. */
export function topRespected(rows: ScanRow[], side: "BUY" | "SELL", regime: string, minimumTouches: number, take = 5): ScanRow[] {
  return rows
    .filter(row => (row.respect[regime]?.[side]?.touches ?? 0) >= minimumTouches)
    .filter(row => row.respect[regime]?.[side]?.respect_rate != null)
    .sort((a, b) => (b.respect[regime][side].respect_rate ?? 0) - (a.respect[regime][side].respect_rate ?? 0))
    .slice(0, take);
}

// ARK-S29-02. The Owner asked for the latest synced bar, and was right to: with
// the reserve held back the M5 window ends in December 2024 while they trade
// September 2026. The choice is theirs, and the price of each side is on the
// button rather than buried in a footnote.
const COVERAGES = [
  { id: "ALL", label: "Sampai data terkini", hint: "seluruh data, ikut sync terbaru" },
  { id: "RESEARCH", label: "Sisakan 20% untuk vonis", hint: "berhenti lebih awal, tapi masih ada juri" },
] as const;

type CoverageId = (typeof COVERAGES)[number]["id"];

const EVENT_LABEL: Record<string, string> = {
  BOUNCE_FROM_ABOVE: "Mantul dari atas (BUY)",
  BREAK_DOWN: "Tembus ke bawah (SELL)",
  BOUNCE_FROM_BELOW: "Mantul dari bawah (SELL)",
  BREAK_UP: "Tembus ke atas (BUY)",
};

const percent = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`);
const count = (value: number) => value.toLocaleString("id-ID");
const bars = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${value}`);
/** 0 is the sentinel for "followed until it resolved"; printing it would read as a limit of zero. */
export const timeoutLabel = (value: number) => (value ? `${value}` : "tanpa batas");

/** What a single row is worth saying out loud. */
/** Points of win rate above the break-even the geometry itself imposes. */
export const edgeLabel = (edge: number | null | undefined) =>
  edge === null || edge === undefined ? "—" : `${edge >= 0 ? "+" : ""}${(edge * 100).toFixed(1)}`;
export const edgeTone = (edge: number | null | undefined) =>
  edge === null || edge === undefined ? "muted" : edge > 0.015 ? "edge-good" : edge > 0 ? "edge-thin" : "edge-bad";

export function judge(row: Row, minimumResolved: number): { label: string; tone: string; why: string } {
  const resolved = row.target_first + row.stop_first;
  if (resolved < minimumResolved) return { label: "SAMPEL KURANG", tone: "weak", why: `Baru ${count(resolved)} kejadian yang selesai.` };
  // ARK-S32-01: judged against a coin flip of the same direction, not against
  // break-even. Break-even removes the geometry dial; it does not remove gold's
  // drift, and drift produced every positive number ever found here.
  const edge = row.edge_over_baseline ?? row.edge;
  if (edge === null || edge === undefined) return { label: "TIDAK TERUKUR", tone: "weak", why: "Tidak ada kejadian yang selesai." };
  const against = row.edge_over_baseline !== null && row.edge_over_baseline !== undefined
    ? `entry acak (${percent(row.baseline_rate)})` : `impas ${percent(row.break_even_rate)}`;
  if (edge > 0.015) return { label: "MENARIK", tone: "strong", why: `Unggul ${edgeLabel(edge)} poin di atas ${against}.` };
  if (edge > 0) return { label: "TIPIS", tone: "medium", why: `Cuma ${edgeLabel(edge)} poin di atas ${against} — bisa hilang oleh komisi dan slippage.` };
  return { label: "TIDAK TAMBAH APA-APA", tone: "weak", why: `${edgeLabel(edge)} poin terhadap ${against} — sinyalnya tidak lebih baik dari lempar koin.` };
}

/** The toll, stated before the measurement rather than discovered after it.
 *  Entering long at `open + s` puts the target `d*m + s` away and the stop
 *  `d - s` away, so a driftless walk lands `s/((1+m)d)` under break-even. */
export function costPoints(spread: number, kind: "PERCENT" | "FIXED", value: number, multiple: number, price = 4500): string {
  const distance = kind === "PERCENT" ? (price * value) / 100 : value;
  if (!Number.isFinite(distance) || distance <= 0 || !Number.isFinite(spread)) return "—";
  return `-${((100 * spread) / ((1 + multiple) * distance)).toFixed(2)}`;
}

export function resolvedShare(row: Row): number | null {
  const total = row.events;
  return total ? (row.target_first + row.stop_first) / total : null;
}

export function LevelTouchLab({ embedded = false }: { embedded?: boolean } = {}) {
  const [options, setOptions] = useState<Options | null>(null);
  const [timeframe, setTimeframe] = useState("M15");
  const [kind, setKind] = useState("EMA");
  const [period, setPeriod] = useState(23);
  // ARK-S31-01: percent of price, because $5 is 0.11% at 4,500 and 0.25% at 2,000.
  const [distanceKind, setDistanceKind] = useState<"PERCENT" | "FIXED">("PERCENT");
  const [distances, setDistances] = useState("0.12");
  const [targetMultiple, setTargetMultiple] = useState(1);
  const [atrMultiple, setAtrMultiple] = useState(1.5);
  const [useAtr, setUseAtr] = useState(false);
  // Blank by default: a $5 target on gold does not sit open for days, so a
  // limit is a knob in the way of the question rather than part of it.
  const [timeouts, setTimeouts] = useState("");
  // One number is the normal case. Comparing several at once is a deliberate
  // extra, not the shape the first-time reader has to decode.
  const [compare, setCompare] = useState(false);
  const [spread, setSpread] = useState(0.25);
  const [coverage, setCoverage] = useState<CoverageId>("ALL");
  const [regime, setRegime] = useState<RegimeId>("SEMUA");
  const [trendLookback, setTrendLookback] = useState(20);
  const [trendThreshold, setTrendThreshold] = useState(0.15);
  const [scan, setScan] = useState<Scan | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanRange, setScanRange] = useState({ from: 20, to: 50 });
  const [data, setData] = useState<Probe | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    void (async () => {
      const response = await fetch("/api/v1/level-touch/options", { cache: "no-store" });
      if (response.ok) setOptions(await response.json());
    })();
  }, []);

  const numbers = (value: string) => value.split(",").map(item => Number(item.trim())).filter(item => Number.isFinite(item) && item > 0);

  const spec = useMemo(() => ({
    timeframe,
    level: { kind, period },
    distances: [
      ...numbers(distances).slice(0, useAtr ? 3 : 4).map(value => ({ kind: distanceKind, value })),
      ...(useAtr ? [{ kind: "ATR", multiple: atrMultiple, period: 14 }] : []),
    ],
    target_multiple: targetMultiple,
    timeouts: numbers(timeouts).map(value => Math.round(value)),   // [] means no limit
    spread_price: spread,
    coverage,
    trend: { lookback: trendLookback, threshold_percent: trendThreshold },
  }), [timeframe, kind, period, distanceKind, distances, targetMultiple, useAtr, atrMultiple, timeouts, spread, coverage, trendLookback, trendThreshold]);

  const run = useCallback(async () => {
    setBusy(true); setMessage("Menghitung… M1 bisa memakan waktu sekitar semenit."); setData(null); setOpenRow(null);
    try {
      const response = await fetch("/api/v1/level-touch", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Pengukuran gagal.");
      setData(body);
      setAttempts(current => current + 1);
      setMessage(body.reused ? "Diambil dari hasil yang sudah tersimpan." : "Selesai dihitung dan disimpan.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Pengukuran gagal.");
    } finally {
      setBusy(false);
    }
  }, [spec]);

  const ranked = useMemo(() => {
    if (!data) return [];
    return data.summary.filter(row => row.regime === regime)
      .sort((a, b) => ((b.edge_over_baseline ?? b.edge) ?? -1) - ((a.edge_over_baseline ?? a.edge) ?? -1));
  }, [data, regime]);

  const runScan = useCallback(async () => {
    setScanBusy(true); setScan(null);
    try {
      const response = await fetch("/api/v1/level-touch/scan", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ timeframe, kinds: ["EMA", "SMA"], minimum_period: scanRange.from, maximum_period: scanRange.to,
                               coverage, trend: { lookback: trendLookback, threshold_percent: trendThreshold } }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Pemindaian gagal.");
      setScan(body);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Pemindaian gagal.");
    } finally {
      setScanBusy(false);
    }
  }, [timeframe, scanRange, coverage, trendLookback, trendThreshold]);

  const rowKey = (row: Row) => `${row.event}|${row.distance}|${row.timeout_bars}|${row.regime}`;

  const body = <>
      <section className="panel backtest-config">
        <h2>Susun percobaan Anda</h2>
        <div className="timeframes">
          {(options?.timeframes ?? []).map(item => <button key={item.timeframe} className={item.timeframe === timeframe ? "selected" : ""} onClick={() => setTimeframe(item.timeframe)}>
            {item.timeframe}<small> · {count(item.rows)}</small>
          </button>)}
        </div>
        <div className="backtest-form">
          <label>Jenis garis<select value={kind} onChange={event => setKind(event.target.value)}>{(options?.level_kinds ?? ["EMA", "SMA"]).map(item => <option key={item} value={item}>{item}</option>)}</select>
            <small>Garis yang harus disentuh harga.</small></label>
          <label>Periode<input aria-label="Periode" type="number" min="1" max="500" value={period} onChange={event => setPeriod(Math.round(event.target.valueAsNumber))} />
            <small>Berapa candle dipakai untuk menghitung garisnya.</small></label>
          <label>Satuan jarak<select value={distanceKind} onChange={event => setDistanceKind(event.target.value as "PERCENT" | "FIXED")}>
              <option value="PERCENT">Persen dari harga</option>
              <option value="FIXED">Dolar tetap</option>
            </select>
            <small>$5 itu 0,11% saat emas 4.500 tapi 0,25% saat 2.000. Persen tetap berarti sama sepanjang sejarah.</small></label>
          <label>Jarak SL ({distanceKind === "PERCENT" ? "%" : "dolar"}){compare
            ? <input aria-label="Jarak SL" value={distances} onChange={event => setDistances(event.target.value)} />
            : <input aria-label="Jarak SL" type="number" min="0.01" step={distanceKind === "PERCENT" ? "0.01" : "0.1"} value={distances} onChange={event => setDistances(event.target.value)} />}
            <small>{distanceKind === "PERCENT" ? "0,12% kira-kira setara 50 pips saat emas di 4.500." : "Isi 5 berarti SL $5."}</small></label>
          <label>TP = SL x berapa<input aria-label="TP dikali" type="number" min="0.1" max="10" step="0.1" value={targetMultiple} onChange={event => setTargetMultiple(event.target.valueAsNumber)} />
            <small>1 berarti TP = SL, impas di 50%. Isi 0,5 dan winrate naik sendirinya — tapi impasnya ikut naik ke 66,7%. Yang penting selisihnya.</small></label>
          <label>Batas waktu (opsional){compare
            ? <input aria-label="Batas waktu" placeholder="kosongkan = tanpa batas" value={timeouts} onChange={event => setTimeouts(event.target.value)} />
            : <input aria-label="Batas waktu" type="number" min="1" step="1" placeholder="kosongkan = tanpa batas" value={timeouts} onChange={event => setTimeouts(event.target.value)} />}
            <small><strong>Kosongkan saja</strong> — posisi diikuti sampai kena TP atau SL. Isi angka hanya kalau Anda memang mau menutup paksa setelah sekian candle.</small></label>
          <label>Spread<input aria-label="Spread" type="number" min="0" step="0.01" value={spread} onChange={event => setSpread(event.target.valueAsNumber)} />
            <small>Ongkos masuk, dibebankan ke harga entry.</small></label>
          <label>Kelipatan ATR<input aria-label="Kelipatan ATR" type="number" min="0.1" step="0.1" value={atrMultiple} disabled={!useAtr} onChange={event => setAtrMultiple(event.target.valueAsNumber)} />
            <small>TP/SL yang ikut volatilitas: 1,5 berarti 1,5x rata-rata gerak candle terakhir. Berguna karena $5 di 2018 itu jarak jauh, di 2026 dekat.</small></label>
        </div>
        <label className="explorer-filter">
          <input type="checkbox" checked={compare} onChange={event => { setCompare(event.target.checked); if (!event.target.checked) { setDistances(distances.split(",")[0].trim()); setTimeouts(timeouts.split(",")[0].trim()); } }} />
          Bandingkan beberapa angka sekaligus (pisahkan dengan koma)
        </label>
        <label className="explorer-filter">
          <input type="checkbox" checked={useAtr} onChange={event => setUseAtr(event.target.checked)} />
          Tambahkan sekalian jarak yang mengikuti volatilitas (ATR)
        </label>
        <div className="backtest-form">
          <label>Trend dinilai dari berapa candle<input aria-label="Trend lookback" type="number" min="2" max="500" value={trendLookback} onChange={event => setTrendLookback(Math.round(event.target.valueAsNumber))} />
            <small>Kemiringan garis diukur dari sekian candle ke belakang.</small></label>
          <label>Ambang trend (%)<input aria-label="Ambang trend" type="number" min="0" step="0.05" value={trendThreshold} onChange={event => setTrendThreshold(event.target.valueAsNumber)} />
            <small>Di atas ini disebut naik, di bawah minusnya disebut turun, di antaranya datar.</small></label>
        </div>
        <p className="muted">Sampai data kapan?</p>
        <div className="timeframes">
          {COVERAGES.map(item => <button key={item.id} className={item.id === coverage ? "selected" : ""} onClick={() => setCoverage(item.id)}>
            {item.label}<small> · {item.hint}</small>
          </button>)}
        </div>
        <p className="muted">Dengan spread {spread} dan SL {distanceKind === "PERCENT" ? `${distances}%` : `$${distances}`}, ongkosnya kira-kira <strong>{costPoints(spread, distanceKind, Number(distances.split(",")[0]), targetMultiple, 4500)}</strong> poin winrate. Itu yang harus dilewati sinyal apa pun sebelum menghasilkan apa-apa.</p>
        <div className="actions explorer-actions">
          <button className="run-button" disabled={busy} onClick={() => void run()}>Ukur</button>
        </div>
        <p className="muted">Kalau SL dan TP tersentuh di candle yang sama, SL yang menang — aturan paling pesimis, sama dengan mesin backtest. Impas untuk bentuk sekarang: <strong>{(100 / (1 + targetMultiple)).toFixed(1)}%</strong>. Winrate di bawah itu berarti rugi, berapa pun besarnya.</p>
        {coverage === "ALL"
          ? <p className="muted"><strong>Seluruh data dipakai, sampai sync terakhir.</strong> Hasilnya ikut berubah setiap kali Anda sync. Konsekuensinya: tidak ada lagi potongan sejarah yang belum pernah Anda lihat, jadi tidak ada yang bisa jadi juri netral. Pembuktian yang tersisa adalah <strong>forward test</strong> — catat sinyalnya mulai hari ini, lalu bandingkan dengan kenyataan.</p>
          : <p className="muted">Membaca <strong>80% data pertama</strong>. 20% terakhir dikunci dan tidak pernah dibaca di sini, supaya masih ada bagian yang bisa memberi vonis netral nanti — dengan harga datanya berhenti lebih awal.</p>}
        {attempts > 0 && <p className="muted">Anda sudah menjalankan <strong>{attempts}</strong> percobaan di sesi ini. Makin banyak dicoba, makin besar peluang angka bagus muncul karena kebetulan.</p>}
      </section>

      {message && <p className="notice">{message}</p>}

      {data && <>
        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>{data.spec.level.kind} {data.spec.level.period} · {data.asset.timeframe} · {count(data.coverage.touches_total)} sentuhan</h2>
            <p>{data.coverage.start?.slice(0, 10)} sampai {data.coverage.end?.slice(0, 10)} · {count(data.asset.measured_row_count)} dari {count(data.asset.registered_row_count)} candle · sidik jari {data.fingerprint.slice(0, 12)}</p>
            <p className="muted">{data.policy.coverage === "ALL" ? "Sampai candle terakhir yang tersinkron. Angka ini akan berubah setelah sync berikutnya." : "Berhenti di tanggal itu karena 20% candle terbaru sengaja dikunci."}</p>
          </div><span className="mode-badge">{data.reused ? "TERSIMPAN" : "BARU DIHITUNG"}</span></div>
          <section className="command-metrics">
            {Object.entries(data.coverage.touches).map(([event, value]) => <article key={event}>
              <small>{EVENT_LABEL[event] ?? event}</small><strong>{count(value)}</strong>
            </article>)}
          </section>
        </section>

        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>Seberapa sering garisnya di-respect</h2>
            <p>Mantul artinya candle-nya ditutup kembali di sisi asalnya. Ini bukan soal untung — mantul itu reaksi satu candle, menang butuh perjalanan beberapa dolar.</p>
          </div></div>
          <div className="explorer-table"><table>
            <thead><tr><th>Kondisi garis</th><th>BUY: sentuhan dari atas</th><th>Mantul</th><th>Tembus</th><th>Respect</th><th>SELL: sentuhan dari bawah</th><th>Mantul</th><th>Tembus</th><th>Respect</th></tr></thead>
            <tbody>{REGIMES.map(item => {
              const value = data.respect?.[item.id];
              if (!value) return null;
              return <tr key={item.id} className={item.id === regime ? "explorer-detail" : undefined}>
                <td><strong>{item.label}</strong></td>
                <td>{count(value.BUY.touches)}</td><td>{count(value.BUY.bounced)}</td><td>{count(value.BUY.broke)}</td>
                <td><strong>{percent(value.BUY.respect_rate)}</strong></td>
                <td>{count(value.SELL.touches)}</td><td>{count(value.SELL.bounced)}</td><td>{count(value.SELL.broke)}</td>
                <td><strong>{percent(value.SELL.respect_rate)}</strong></td>
              </tr>;
            })}</tbody>
          </table></div>
        </section>

        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>Hasil, diurutkan dari selisih terhadap entry acak</h2>
            <p><strong>Winrate saja tidak berarti apa-apa</strong> — perkecil TP dan winrate naik sendirinya. <strong>Selisih terhadap impas pun belum cukup</strong>: emas naik terus 2017–2026, jadi asal beli pun kelihatan unggul. Kolom <strong>vs acak</strong> membandingkan sinyal Anda dengan lempar koin ke arah yang sama, di candle yang sama, dengan bentuk dan spread yang sama. Itu satu-satunya angka yang tidak bisa dipalsukan oleh tren.</p>
          </div></div>
          <div className="explorer-controls">
            <div className="timeframes">
              {REGIMES.map(item => <button key={item.id} className={item.id === regime ? "selected" : ""} onClick={() => setRegime(item.id)}>{item.label}</button>)}
            </div>
            <p className="muted">Kondisi garis dinilai dari kemiringannya sendiri selama {data.spec.trend.lookback} candle terakhir, ambang {data.spec.trend.threshold_percent}%.</p>
          </div>
          <div className="explorer-table">
            <table>
              <thead><tr><th>Kejadian</th><th>TP/SL</th><th>Batas waktu</th><th>Sentuhan</th><th>Selesai</th><th>Winrate</th><th>Impas</th><th>vs impas</th><th>Entry acak</th><th>vs acak</th><th>Med. candle</th><th>Penilaian</th><th /></tr></thead>
              <tbody>
                {ranked.map(row => {
                  const key = rowKey(row);
                  const state = judge(row, 300);
                  const yearRows = data.per_year.filter(item => rowKey(item) === key).sort((a, b) => (a.year ?? 0) - (b.year ?? 0));
                  const monthRows = data.per_month.filter(item => rowKey(item) === key).sort((a, b) => String(a.month).localeCompare(String(b.month)));
                  return <React.Fragment key={key}>
                    <tr>
                      <td><strong>{EVENT_LABEL[row.event] ?? row.event}</strong></td>
                      <td>{row.distance.replace("FIXED_", "$").replace("ATR_", "ATR ")}</td>
                      <td>{timeoutLabel(row.timeout_bars)}</td>
                      <td>{count(row.events)}</td>
                      <td>{count(row.target_first + row.stop_first)}<small>{percent(resolvedShare(row))} dari sentuhan</small></td>
                      <td><strong>{percent(row.target_rate_of_resolved)}</strong></td>
                      <td className="muted">{percent(row.break_even_rate)}</td>
                      <td className="muted">{edgeLabel(row.edge)}</td>
                      <td className="muted">{percent(row.baseline_rate)}</td>
                      <td className={edgeTone(row.edge_over_baseline)}><strong>{edgeLabel(row.edge_over_baseline)}</strong></td>
                      <td>{bars(row.median_bars_to_target)}</td>
                      <td><span className={`explorer-verdict ${state.tone}`}>{state.label}</span><small>{state.why}</small></td>
                      <td><button className="sample-use" onClick={() => setOpenRow(openRow === key ? null : key)}>{openRow === key ? "Tutup" : "Rinci"}</button></td>
                    </tr>
                    {openRow === key && <tr className="explorer-detail"><td colSpan={13}>
                      <h3>Per tahun</h3>
                      <table>
                        <thead><tr><th>Tahun</th><th>Sentuhan</th><th>TP</th><th>SL</th><th>Belum selesai</th><th>Winrate</th></tr></thead>
                        <tbody>{yearRows.map(item => <tr key={item.year}>
                          <td>{item.year}</td><td>{count(item.events)}</td><td>{count(item.target_first)}</td>
                          <td>{count(item.stop_first)}</td><td>{count(item.unresolved)}</td>
                          <td>{percent(item.target_rate_of_resolved)}</td>
                        </tr>)}</tbody>
                      </table>
                      <h3>Per bulan (12 terakhir)</h3>
                      <table>
                        <thead><tr><th>Bulan</th><th>Sentuhan</th><th>TP</th><th>SL</th><th>Winrate</th></tr></thead>
                        <tbody>{monthRows.slice(-12).map(item => <tr key={item.month}>
                          <td>{item.month}</td><td>{count(item.events)}</td><td>{count(item.target_first)}</td>
                          <td>{count(item.stop_first)}</td><td>{percent(item.target_rate_of_resolved)}</td>
                        </tr>)}</tbody>
                      </table>
                    </td></tr>}
                  </React.Fragment>;
                })}
              </tbody>
            </table>
          </div>
          <p className="warning-line">{data.geometry.baseline_note} Dibanding dengan {count(data.geometry.baseline_samples)} entry acak per arah.</p>
          <p className="warning-line">{data.warning}</p>
        </section>
      </>}

      <section className="panel result-panel">
        <div className="panel-header"><div>
          <h2>Pindai: garis mana yang paling di-respect?</h2>
          <p>Menyapu EMA dan SMA sekaligus di {timeframe}, lalu memberi lima teratas untuk BUY dan untuk SELL. Hanya menghitung mantul versus tembus — bukan untung rugi.</p>
        </div><span className="mode-badge">{scan ? `${scan.rows.length} GARIS` : "BELUM DIPINDAI"}</span></div>
        <div className="explorer-controls">
          <div className="backtest-form">
            <label>Periode dari<input aria-label="Periode dari" type="number" min="2" max="200" value={scanRange.from} onChange={event => setScanRange(current => ({ ...current, from: Math.round(event.target.valueAsNumber) }))} /></label>
            <label>sampai<input aria-label="Periode sampai" type="number" min="2" max="200" value={scanRange.to} onChange={event => setScanRange(current => ({ ...current, to: Math.round(event.target.valueAsNumber) }))} /></label>
          </div>
          <div className="actions"><button className="run-button" disabled={scanBusy} onClick={() => void runScan()}>{scanBusy ? "Memindai…" : `Pindai ${timeframe}`}</button></div>
        </div>
        {scan && <>
          <p className="muted explorer-note">{scan.coverage.start?.slice(0, 10)} sampai {scan.coverage.end?.slice(0, 10)} · {count(scan.coverage.bars)} candle · kondisi garis: <strong>{REGIMES.find(item => item.id === regime)?.label}</strong> (ganti di atas).</p>
          <div className="explorer-runs">
            {(["BUY", "SELL"] as const).map(side => {
              const top = topRespected(scan.rows, side, regime, 500);
              return <section key={side}>
                <h3>{side === "BUY" ? "Untuk BUY — sentuhan dari atas lalu mantul" : "Untuk SELL — sentuhan dari bawah lalu mantul"}</h3>
                {top.length ? <table>
                  <thead><tr><th>Garis</th><th>Respect</th><th>Mantul</th><th>Tembus</th><th>Semua kondisi</th></tr></thead>
                  <tbody>{top.map(row => <tr key={`${row.kind}${row.period}`}>
                    <td><strong>{row.kind} {row.period}</strong></td>
                    <td><strong>{percent(row.respect[regime][side].respect_rate)}</strong></td>
                    <td>{count(row.respect[regime][side].bounced)}</td>
                    <td>{count(row.respect[regime][side].broke)}</td>
                    <td className="muted">{percent(row.respect.SEMUA?.[side]?.respect_rate)}</td>
                  </tr>)}</tbody>
                </table> : <p className="muted">Tidak ada garis dengan sampel cukup (min 500 sentuhan) di kondisi ini.</p>}
              </section>;
            })}
          </div>
          <p className="warning-line">{scan.warning}</p>
        </>}
      </section>
  </>;

  if (embedded) return body;
  return <main className="backtest-page">
    <header>
      <div>
        <Link className="back-link" href="/explore">← Riset Pasar</Link>
        <h1>Uji Sentuhan Garis</h1>
        <p>Saat harga menyentuh sebuah garis: duluan kena TP, SL, atau tidak dua-duanya?</p>
      </div>
      <span className="mode-badge">PENGUKURAN SAJA</span>
    </header>
    <section className="backtest-content">{body}</section>
  </main>;
}

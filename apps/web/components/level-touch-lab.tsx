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
  spec: { timeframe: string; level: { kind: string; period: number }; spread_price: number; splits: string[] };
  policy: { readable_splits: string[]; ambiguity: string; entry: string };
  warning: string;
  asset: { timeframe: string; registered_row_count: number; measured_row_count: number };
  coverage: { bars: number; start: string | null; end: string | null; touches: Record<string, number>; touches_total: number };
  summary: Row[];
  per_year: Row[];
  per_month: Row[];
};

type Options = { level_kinds: string[]; timeframes: Array<{ timeframe: string; rows: number }> };

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
export function judge(row: Row, minimumResolved: number): { label: string; tone: string; why: string } {
  const resolved = row.target_first + row.stop_first;
  if (resolved < minimumResolved) return { label: "SAMPEL KURANG", tone: "weak", why: `Baru ${count(resolved)} kejadian yang selesai.` };
  const rate = row.target_rate_of_resolved ?? 0;
  if (rate >= 0.55) return { label: "MENARIK", tone: "strong", why: "Di atas 55% — layak diperiksa per tahun." };
  if (rate >= 0.50) return { label: "TIPIS", tone: "medium", why: "Di atas 50% tapi belum tentu menutup spread." };
  return { label: "TIDAK UNGGUL", tone: "weak", why: "Di bawah 50% — kalah lebih sering dari menang." };
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
  const [distances, setDistances] = useState("5");
  const [atrMultiple, setAtrMultiple] = useState(1.5);
  const [useAtr, setUseAtr] = useState(false);
  // Blank by default: a $5 target on gold does not sit open for days, so a
  // limit is a knob in the way of the question rather than part of it.
  const [timeouts, setTimeouts] = useState("");
  // One number is the normal case. Comparing several at once is a deliberate
  // extra, not the shape the first-time reader has to decode.
  const [compare, setCompare] = useState(false);
  const [spread, setSpread] = useState(0.25);
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
      ...numbers(distances).slice(0, useAtr ? 3 : 4).map(value => ({ kind: "FIXED", value })),
      ...(useAtr ? [{ kind: "ATR", multiple: atrMultiple, period: 14 }] : []),
    ],
    timeouts: numbers(timeouts).map(value => Math.round(value)),   // [] means no limit
    spread_price: spread,
  }), [timeframe, kind, period, distances, useAtr, atrMultiple, timeouts, spread]);

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
    return [...data.summary].sort((a, b) => (b.target_rate_of_resolved ?? -1) - (a.target_rate_of_resolved ?? -1));
  }, [data]);

  const rowKey = (row: Row) => `${row.event}|${row.distance}|${row.timeout_bars}`;

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
          <label>TP dan SL (dolar){compare
            ? <input aria-label="TP dan SL" value={distances} onChange={event => setDistances(event.target.value)} />
            : <input aria-label="TP dan SL" type="number" min="0.1" step="0.1" value={distances} onChange={event => setDistances(event.target.value)} />}
            <small>Keduanya sama besar. Isi <strong>5</strong> berarti TP $5 dan SL $5.</small></label>
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
        <div className="actions explorer-actions">
          <button className="run-button" disabled={busy} onClick={() => void run()}>Ukur</button>
        </div>
        <p className="muted">TP dan SL selalu sama besar, jadi <strong>winrate adalah satu-satunya angka yang penting</strong>. Kalau SL dan TP tersentuh di candle yang sama, SL yang menang — aturan paling pesimis, sama dengan mesin backtest.</p>
        <p className="muted">Membaca <strong>80% data pertama</strong>. 20% terakhir tetap terkunci dan tidak pernah dibaca di sini — itu satu-satunya bagian yang nanti bisa memberi vonis, justru karena Anda bebas mencoba berkali-kali di halaman ini.</p>
        {attempts > 0 && <p className="muted">Anda sudah menjalankan <strong>{attempts}</strong> percobaan di sesi ini. Makin banyak dicoba, makin besar peluang angka bagus muncul karena kebetulan.</p>}
      </section>

      {message && <p className="notice">{message}</p>}

      {data && <>
        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>{data.spec.level.kind} {data.spec.level.period} · {data.asset.timeframe} · {count(data.coverage.touches_total)} sentuhan</h2>
            <p>{data.coverage.start?.slice(0, 10)} sampai {data.coverage.end?.slice(0, 10)} · {count(data.asset.measured_row_count)} dari {count(data.asset.registered_row_count)} candle · sidik jari {data.fingerprint.slice(0, 12)}</p>
            <p className="muted">Berhenti di tanggal itu karena 20% candle terbaru sengaja dikunci.</p>
          </div><span className="mode-badge">{data.reused ? "TERSIMPAN" : "BARU DIHITUNG"}</span></div>
          <section className="command-metrics">
            {Object.entries(data.coverage.touches).map(([event, value]) => <article key={event}>
              <small>{EVENT_LABEL[event] ?? event}</small><strong>{count(value)}</strong>
            </article>)}
          </section>
        </section>

        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>Hasil, diurutkan dari winrate tertinggi</h2>
            <p>Winrate dihitung dari kejadian yang <em>selesai</em> saja. Yang belum selesai dalam batas waktu dihitung terpisah, bukan disembunyikan.</p>
          </div></div>
          <div className="explorer-table">
            <table>
              <thead><tr><th>Kejadian</th><th>TP/SL</th><th>Batas waktu</th><th>Sentuhan</th><th>Selesai</th><th>Winrate</th><th>Med. candle ke TP</th><th>Penilaian</th><th /></tr></thead>
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
                      <td>{bars(row.median_bars_to_target)}</td>
                      <td><span className={`explorer-verdict ${state.tone}`}>{state.label}</span><small>{state.why}</small></td>
                      <td><button className="sample-use" onClick={() => setOpenRow(openRow === key ? null : key)}>{openRow === key ? "Tutup" : "Rinci"}</button></td>
                    </tr>
                    {openRow === key && <tr className="explorer-detail"><td colSpan={9}>
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
          <p className="warning-line">{data.warning}</p>
        </section>
      </>}
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

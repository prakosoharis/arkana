"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";

/**
 * ARK-S26-01. The first screen in this application that answers a question the
 * Owner actually asked, in the Owner's own words, without first requiring a
 * strategy to exist.
 *
 * Every rate is rendered beside its sample count and its year-to-year spread.
 * A percentage on its own is the thing that misleads, so the layout does not
 * allow one to appear alone.
 */

type Consistency = {
  years_measured: number;
  sufficient_years: boolean;
  minimum_up_rate: number | null;
  maximum_up_rate: number | null;
  spread: number | null;
  years_above_half: number | null;
};

type Row = {
  key: number;
  label: string;
  bars: number;
  up: number;
  down: number;
  flat: number;
  up_rate: number | null;
  down_rate: number | null;
  mean_range: number | null;
  mean_body: number | null;
  sufficient_sample: boolean;
  consistency: Consistency;
  per_year: Record<string, { bars: number; up_rate: number | null; down_rate: number | null; mean_range: number | null }>;
};

type RunLength = { length: number; occurrences: number; closed_runs: number; mean_move: number | null };

type Exploration = {
  timeframe: string;
  display_timezone: string;
  bars_measured: number;
  fingerprint: string;
  reused: boolean;
  clock: { source: string; display_timezone: string; dataset_timezone_status: string; note: string; caveat: string; measured_from: string; ambiguous_window: string; broker_offset_utc: { us_daylight_saving: string; us_standard_time: string } };
  policy: { minimum_samples: number; minimum_years: number; size_window: number; large_multiple: number; small_multiple: number };
  warning: string;
  coverage: { bars: number; start: string | null; end: string | null; years: number; up_rate: number | null; down_rate: number | null; mean_range: number | null };
  per_year: Array<{ year: number; bars: number; up_rate: number | null; mean_range: number | null }>;
  time_of_day: Row[];
  hour_of_day: Row[];
  day_of_week: Row[];
  runs: Record<"UP" | "DOWN", { total: number; mean_length: number | null; lengths: RunLength[] }>;
  follow_through: Array<{ key: string; bars: number; up_rate: number | null; down_rate: number | null; mean_range: number | null; mean_body: number | null; sufficient_sample: boolean }>;
};

type TimeframeOption = { timeframe: string; rows: number; measured: Record<string, boolean> };

const ZONES = [
  { id: "WIB", label: "Jam WIB", hint: "jam di HP Anda" },
  { id: "BROKER", label: "Jam broker", hint: "persis seperti di MT5" },
] as const;

const VIEWS = [
  { id: "time_of_day", label: "Per jam:menit" },
  { id: "hour_of_day", label: "Per jam" },
  { id: "day_of_week", label: "Per hari" },
  { id: "runs", label: "Rentetan naik/turun" },
  { id: "follow", label: "Setelah candle tertentu" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

const SORTS = [
  { id: "down", label: "Paling sering merah" },
  { id: "up", label: "Paling sering hijau" },
  { id: "time", label: "Urut waktu" },
  { id: "range", label: "Range terbesar" },
] as const;

type SortId = (typeof SORTS)[number]["id"];

const percent = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`);
const price = (value: number | null | undefined) => (value === null || value === undefined ? "—" : value.toFixed(3));
const count = (value: number) => value.toLocaleString("id-ID");

/** How trustworthy a row is, in one word the Owner can act on. */
export function verdict(row: Row, minimumSamples: number): { label: string; tone: string; why: string } {
  if (!row.sufficient_sample) return { label: "SAMPEL KURANG", tone: "weak", why: `Baru ${count(row.bars)} candle, minimal ${count(minimumSamples)}.` };
  if (!row.consistency.sufficient_years) return { label: "TAHUN KURANG", tone: "weak", why: `Hanya ${row.consistency.years_measured} tahun yang sampelnya cukup.` };
  const spread = row.consistency.spread ?? 1;
  if (spread > 0.2) return { label: "TIDAK KONSISTEN", tone: "weak", why: `Selisih antar tahun ${percent(spread)} — angkanya berpindah-pindah.` };
  if (spread > 0.1) return { label: "AGAK GOYANG", tone: "medium", why: `Selisih antar tahun ${percent(spread)}.` };
  return { label: "KONSISTEN", tone: "strong", why: `Selisih antar tahun hanya ${percent(spread)} selama ${row.consistency.years_measured} tahun.` };
}

export function sortRows(rows: Row[], sort: SortId): Row[] {
  const copy = [...rows];
  if (sort === "time") return copy.sort((a, b) => a.key - b.key);
  if (sort === "range") return copy.sort((a, b) => (b.mean_range ?? -1) - (a.mean_range ?? -1));
  const field = sort === "down" ? "down_rate" : "up_rate";
  return copy.sort((a, b) => (b[field] ?? -1) - (a[field] ?? -1));
}

function RowTable({ rows, minimumSamples, onlySufficient, query, limit }: { rows: Row[]; minimumSamples: number; onlySufficient: boolean; query: string; limit: number }) {
  const [open, setOpen] = useState<number | null>(null);
  const filtered = rows
    .filter(row => (onlySufficient ? row.sufficient_sample : true))
    .filter(row => (query.trim() ? row.label.includes(query.trim()) : true));
  const shown = filtered.slice(0, limit);
  if (!shown.length) return <p className="empty-library muted">Tidak ada baris yang cocok. Coba matikan filter &quot;sampel cukup&quot; atau kosongkan pencarian.</p>;
  return <div className="explorer-table">
    <table>
      <thead><tr><th>Waktu</th><th>Hijau</th><th>Merah</th><th>Jumlah candle</th><th>Rata-rata range</th><th>Konsistensi antar tahun</th><th /></tr></thead>
      <tbody>
        {shown.map(row => {
          const state = verdict(row, minimumSamples);
          return <React.Fragment key={row.key}>
            <tr>
              <td><strong>{row.label}</strong></td>
              <td>{percent(row.up_rate)}</td>
              <td>{percent(row.down_rate)}</td>
              <td>{count(row.bars)}</td>
              <td>{price(row.mean_range)}</td>
              <td><span className={`explorer-verdict ${state.tone}`}>{state.label}</span><small>{state.why}</small></td>
              <td><button className="sample-use" onClick={() => setOpen(open === row.key ? null : row.key)}>{open === row.key ? "Tutup" : "Per tahun"}</button></td>
            </tr>
            {open === row.key && <tr className="explorer-detail"><td colSpan={7}>
              <table>
                <thead><tr><th>Tahun</th><th>Hijau</th><th>Merah</th><th>Candle</th><th>Rata-rata range</th></tr></thead>
                <tbody>{Object.entries(row.per_year).map(([year, value]) => <tr key={year}>
                  <td>{year}</td><td>{percent(value.up_rate)}</td><td>{percent(value.down_rate)}</td>
                  <td>{count(value.bars)}</td><td>{price(value.mean_range)}</td>
                </tr>)}</tbody>
              </table>
            </td></tr>}
          </React.Fragment>;
        })}
      </tbody>
    </table>
    {filtered.length > shown.length && <p className="muted explorer-more">Menampilkan {shown.length} dari {count(filtered.length)} baris. Pakai pencarian untuk mempersempit.</p>}
  </div>;
}

export function RunsPanel({ runs }: { runs: Exploration["runs"] }) {
  return <div className="explorer-runs">
    {(["UP", "DOWN"] as const).map(direction => {
      const data = runs[direction];
      const top = data.lengths.slice(0, 10);
      const total = data.total || 1;
      return <section key={direction}>
        <h3>{direction === "UP" ? "Rentetan candle hijau" : "Rentetan candle merah"}</h3>
        <p className="muted">Terjadi {count(data.total)} kali. Rata-rata bertahan {data.mean_length?.toFixed(2) ?? "—"} candle berturut-turut.</p>
        <table>
          <thead><tr><th>Panjang</th><th>Berapa kali</th><th>Porsi</th><th>Rata-rata jarak tempuh</th></tr></thead>
          <tbody>{top.map(item => <tr key={item.length}>
            <td>{item.length} candle</td><td>{count(item.occurrences)}</td>
            <td>{percent(item.occurrences / total)}</td><td>{price(item.mean_move)}</td>
          </tr>)}</tbody>
        </table>
      </section>;
    })}
  </div>;
}

export function FollowPanel({ rows, minimumSamples, policy }: { rows: Exploration["follow_through"]; minimumSamples: number; policy: Exploration["policy"] }) {
  const name = (key: string) => {
    const [direction, size] = key.split("_");
    return `${direction === "UP" ? "Hijau" : "Merah"} ${size.toLowerCase()}`;
  };
  return <div className="explorer-table">
    <p className="muted explorer-note">
      Ukuran candle dinilai relatif terhadap rata-rata {policy.size_window} candle sebelumnya —
      besar = lebih dari {policy.large_multiple}×, kecil = kurang dari {policy.small_multiple}×.
      Baris di bawah menjawab: <strong>setelah candle seperti ini, candle berikutnya biasanya apa?</strong>
    </p>
    <table>
      <thead><tr><th>Candle sebelumnya</th><th>Berikutnya hijau</th><th>Berikutnya merah</th><th>Jumlah kejadian</th><th>Rata-rata badan berikutnya</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.key}>
        <td><strong>{name(row.key)}</strong></td>
        <td>{percent(row.up_rate)}</td>
        <td>{percent(row.down_rate)}</td>
        <td>{count(row.bars)}{!row.sufficient_sample && <small> · di bawah {count(minimumSamples)}</small>}</td>
        <td>{price(row.mean_body)}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export function MarketExplorer({ embedded = false }: { embedded?: boolean } = {}) {
  const [options, setOptions] = useState<TimeframeOption[]>([]);
  const [timeframe, setTimeframe] = useState("M5");
  const [zone, setZone] = useState<"WIB" | "BROKER">("WIB");
  const [data, setData] = useState<Exploration | null>(null);
  const [view, setView] = useState<ViewId>("time_of_day");
  const [sort, setSort] = useState<SortId>("down");
  const [onlySufficient, setOnlySufficient] = useState(true);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void (async () => {
      const response = await fetch("/api/v1/market-explorer/timeframes", { cache: "no-store" });
      if (response.ok) {
        const body = await response.json();
        setOptions(body.timeframes ?? []);
        if (body.timeframes?.length && !body.timeframes.some((item: TimeframeOption) => item.timeframe === "M5")) {
          setTimeframe(body.timeframes[0].timeframe);
        }
      }
    })();
  }, []);

  const load = useCallback(async (target: string, targetZone: string, refresh = false) => {
    setBusy(true); setMessage(refresh ? "Menghitung ulang dari awal…" : "Membaca data…"); setData(null);
    try {
      const response = await fetch(`/api/v1/market-explorer/${target}?timezone=${targetZone}${refresh ? "&refresh=true" : ""}`, { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Pengukuran gagal.");
      setData(body);
      setMessage(body.reused ? "Diambil dari hasil yang sudah tersimpan." : "Selesai dihitung dan disimpan.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Pengukuran gagal.");
    } finally {
      setBusy(false);
    }
  }, []);

  const rows: Row[] = useMemo(() => {
    if (!data) return [];
    if (view === "time_of_day") return sortRows(data.time_of_day, sort);
    if (view === "hour_of_day") return sortRows(data.hour_of_day, sort);
    if (view === "day_of_week") return sortRows(data.day_of_week, sort);
    return [];
  }, [data, view, sort]);

  const body = <>
      <section className="panel backtest-config">
        <h2>Pilih timeframe dan jam</h2>
        <div className="timeframes">
          {options.map(option => <button key={option.timeframe} className={option.timeframe === timeframe ? "selected" : ""} onClick={() => setTimeframe(option.timeframe)}>
            {option.timeframe}<small> · {count(option.rows)}</small>
          </button>)}
        </div>
        <div className="timeframes explorer-zones">
          {ZONES.map(item => <button key={item.id} className={item.id === zone ? "selected" : ""} onClick={() => setZone(item.id)}>
            {item.label}<small> · {item.hint}</small>
          </button>)}
        </div>
        <div className="actions explorer-actions">
          <button className="run-button" disabled={busy} onClick={() => void load(timeframe, zone)}>Ukur {timeframe}</button>
          <button className="secondary" disabled={busy || !data} onClick={() => void load(timeframe, zone, true)}>Hitung ulang</button>
        </div>
        <p className="muted">Jam broker Anda tertinggal <strong>4 jam</strong> dari WIB saat daylight saving Amerika aktif (sekitar Maret–November), dan <strong>5 jam</strong> di luar itu. Karena selisihnya berubah, mengganti pilihan jam berarti menghitung ulang pengelompokannya, bukan sekadar menggeser label.</p>
        <p className="muted">Perhitungan pertama untuk M1 memakan waktu sekitar setengah menit karena harus membaca 3 juta candle. Hasilnya disimpan per timeframe dan per pilihan jam, jadi berikutnya langsung muncul.</p>
      </section>

      {message && <p className="notice">{message}</p>}

      {data && <>
        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>{data.timeframe} · {count(data.coverage.bars)} candle · {data.coverage.years} tahun · {data.display_timezone === "WIB" ? "jam WIB" : "jam broker"}</h2>
            <p>{data.coverage.start?.slice(0, 10)} sampai {data.coverage.end?.slice(0, 10)} · sidik jari {data.fingerprint.slice(0, 12)}</p>
          </div><span className="mode-badge">{data.reused ? "TERSIMPAN" : "BARU DIHITUNG"}</span></div>
          <section className="command-metrics">
            <article><small>Candle hijau</small><strong>{percent(data.coverage.up_rate)}</strong></article>
            <article><small>Candle merah</small><strong>{percent(data.coverage.down_rate)}</strong></article>
            <article><small>Rata-rata range</small><strong>{price(data.coverage.mean_range)}</strong></article>
            <article><small>Tahun terukur</small><strong>{data.coverage.years}</strong></article>
          </section>
          <p className="warning-line">{data.clock.note}</p>
          <details className="discovery-advanced">
            <summary>Dari mana selisih jam ini diketahui?</summary>
            <p>{data.clock.measured_from}</p>
            <p>Jam broker terhadap UTC: <strong>{data.clock.broker_offset_utc.us_daylight_saving}</strong> saat daylight saving Amerika, <strong>{data.clock.broker_offset_utc.us_standard_time}</strong> di luar itu.</p>
            <p>{data.clock.caveat}</p>
            <p>{data.clock.ambiguous_window}</p>
            <p>Status zona waktu yang tercatat di dataset: <code>{data.clock.dataset_timezone_status}</code>.</p>
          </details>
        </section>

        <section className="panel result-panel">
          <div className="panel-header"><div>
            <h2>Pertanyaan</h2>
            <p>Pilih apa yang ingin Anda lihat. Semua angka selalu ditemani jumlah sampelnya.</p>
          </div></div>
          <div className="explorer-controls">
            <div className="timeframes">
              {/* Weekdays read wrong ranked by rate -- Rabu, Senin, Kamis is not
                  a week. Ranking is still one click away. */}
              {VIEWS.map(item => <button key={item.id} className={item.id === view ? "selected" : ""}
                onClick={() => { setView(item.id); if (item.id === "day_of_week") setSort("time"); }}>{item.label}</button>)}
            </div>
            {(view === "time_of_day" || view === "hour_of_day" || view === "day_of_week") && <>
              <div className="timeframes">
                {SORTS.map(item => <button key={item.id} className={item.id === sort ? "selected" : ""} onClick={() => setSort(item.id)}>{item.label}</button>)}
              </div>
              <label className="explorer-filter">
                <input type="checkbox" checked={onlySufficient} onChange={event => setOnlySufficient(event.target.checked)} />
                Hanya yang sampelnya cukup (min {count(data.policy.minimum_samples)} candle)
              </label>
              {view === "time_of_day" && <label className="explorer-filter">
                Cari jam <input value={query} placeholder="12:40" onChange={event => setQuery(event.target.value)} />
              </label>}
            </>}
          </div>

          {(view === "time_of_day" || view === "hour_of_day" || view === "day_of_week") &&
            <RowTable rows={rows} minimumSamples={data.policy.minimum_samples} onlySufficient={view === "day_of_week" ? false : onlySufficient} query={view === "time_of_day" ? query : ""} limit={60} />}
          {view === "runs" && <RunsPanel runs={data.runs} />}
          {view === "follow" && <FollowPanel rows={data.follow_through} minimumSamples={data.policy.minimum_samples} policy={data.policy} />}
        </section>

        <section className="panel result-panel">
          <div className="panel-header"><div><h2>Ringkasan per tahun</h2><p>Untuk melihat apakah pasar ini berubah sifat dari tahun ke tahun.</p></div></div>
          <div className="explorer-table"><table>
            <thead><tr><th>Tahun</th><th>Candle</th><th>Hijau</th><th>Rata-rata range</th></tr></thead>
            <tbody>{data.per_year.map(item => <tr key={item.year}>
              <td>{item.year}</td><td>{count(item.bars)}</td><td>{percent(item.up_rate)}</td><td>{price(item.mean_range)}</td>
            </tr>)}</tbody>
          </table></div>
          <p className="warning-line">{data.warning}</p>
        </section>
      </>}
  </>;

  if (embedded) return body;
  return <main className="backtest-page">
    <header>
      <div>
        <Link className="back-link" href="/">← Data Pasar</Link>
        <h1>Eksplorasi Market</h1>
        <p>Mengukur pasar apa adanya. Belum ada strategi, belum ada backtest, belum ada sinyal.</p>
      </div>
      <span className="mode-badge">PENGUKURAN SAJA</span>
    </header>
    <section className="backtest-content">{body}</section>
  </main>;
}

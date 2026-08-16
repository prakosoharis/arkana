"use client";

import Link from "next/link";
import React, { useState } from "react";
import { CandlestickChart } from "./candlestick-chart";
import type { Bar } from "../lib/market";

type Outcome = { occurrences:number; positive_rate:number|null; mean_forward_return:number|null };
type ContextBar = Bar;
type Sample = { timestamp:string; partition?:"TRAIN"|"HOLDOUT"; forward_return:number; mfe:number; mae:number; context:ContextBar[] };
type Candidate = { name:string; conditions:string; status:string; train:Outcome; holdout:Outcome; samples:Sample[] };
type Split = { train_rows:number; holdout_rows:number; train_period:{start:string;end:string}; holdout_period:{start:string;end:string}; minimum_support:number };
type Discovery = { version:string; fingerprint:string; timeframe:string; coverage:{start:string;end:string;bar_count:number}; split:Split; search_space:{evaluated:number;status_counts:Record<string,number>}; candidates:Candidate[]; warning:string };
type Analog = Sample & { similarity_score:number; feature_delta:Record<string,number> };
type Similarity = { selected:Sample; analogs:Analog[]; aggregate:Outcome & { mean_mfe:number|null;mean_mae:number|null }; method:{embargo_bars:number}; warning:string };
type ErrorBody = { detail?:string };
const frames=["M1","M5","M15","M30","H1","H4"];

const statusLabel:Record<string,string>={
  WORTH_INVESTIGATING:"Layak Diteliti",
  OVERFIT_RISK:"Bagus di Data Lama, Lemah di Data Baru",
  UNSTABLE:"Hasil Belum Konsisten",
  INSUFFICIENT_SUPPORT:"Data Kejadian Belum Cukup",
};
const statusExplanation:Record<string,string>={
  WORTH_INVESTIGATING:"Jumlah kejadian dan hasil antara data penemuan dan data uji baru memenuhi pemeriksaan awal ARKANA. Ini belum merupakan strategi atau rekomendasi trading.",
  OVERFIT_RISK:"Hasil tampak lebih baik pada data penemuan daripada data uji baru. Jangan menyimpulkan pola ini dapat diandalkan.",
  UNSTABLE:"Hasil antara data penemuan dan data uji baru berbeda cukup besar.",
  INSUFFICIENT_SUPPORT:"Jumlah kejadian belum memenuhi batas minimum untuk penilaian awal.",
};
const tooltip={
  discovery:"Data historis yang dipakai ARKANA untuk mencari kondisi awal.",
  holdout:"Data yang lebih baru, dipisahkan sejak awal dan tidak dipakai untuk memilih kondisi pola.",
  similarity:"Nilai 0 sampai 1 untuk kedekatan fitur OHLC; bukan peluang atau prediksi.",
  mfe:"Gerakan harga maksimum ke arah menguntungkan selama tiga candle setelah kejadian.",
  mae:"Gerakan harga maksimum ke arah berlawanan selama tiga candle setelah kejadian.",
};

function Help({ children, title }: { children:string; title:string }) { return <abbr className="discovery-help" title={title}>ⓘ {children}</abbr>; }
function percent(value:number|null) { return value===null ? "—" : `${(value*100).toFixed(2)}%`; }
function signedPercent(value:number|null) { return value===null ? "—" : `${value>=0?"+":""}${(value*100).toFixed(3)}%`; }
function toApiTimestamp(value:string) { return value ? `${value.replace("T"," ")}${value.length===16 ? ":00" : ""}` : ""; }

function Evidence({ label, outcome }: { label:string; outcome:Outcome }) {
  return <article className="discovery-evidence">
    <small>{label}</small>
    <strong>{percent(outcome.positive_rate)}</strong>
    <span>Harga penutupan 3 candle setelah kejadian lebih tinggi</span>
    <em>{outcome.occurrences.toLocaleString("id-ID")} kejadian · rata-rata {signedPercent(outcome.mean_forward_return)}</em>
  </article>;
}

function SampleViewer({ sample, title }: { sample:Sample; title:string }) {
  return <section className="discovery-sample">
    <div className="panel-header"><div><h3>{title}</h3><p>{sample.timestamp} · {sample.partition === "TRAIN" ? "Data Penemuan" : sample.partition === "HOLDOUT" ? "Data Uji Baru" : "Kondisi yang dipilih"}</p></div></div>
    <CandlestickChart bars={sample.context} />
    <div className="discovery-sample-metrics"><span><strong>Apa yang Terjadi Setelahnya</strong>{signedPercent(sample.forward_return)} dalam 3 candle</span><span><Help title={tooltip.mfe}>Gerakan maksimum yang menguntungkan</Help>{signedPercent(sample.mfe)}</span><span><Help title={tooltip.mae}>Gerakan maksimum yang berlawanan</Help>{signedPercent(sample.mae)}</span></div>
  </section>;
}

export function DiscoveryLab(){
  const [tf,setTf]=useState("M15");
  const [data,setData]=useState<Discovery|null>(null);
  const [timestamp,setTimestamp]=useState("");
  const [sim,setSim]=useState<Similarity|null>(null);
  const [msg,setMsg]=useState("");
  const [advanced,setAdvanced]=useState(false);
  const [openCandidate,setOpenCandidate]=useState<string|null>(null);
  const [selectedSample,setSelectedSample]=useState<Sample|null>(null);
  const [busy,setBusy]=useState(false);

  async function run(){
    setBusy(true); setSim(null); setMsg("");
    try { const r=await fetch(`/api/v1/discovery?timeframe=${tf}`); const b=await r.json() as Discovery&ErrorBody; setData(r.ok?b:null); setMsg(r.ok?"Pencarian pola selesai menggunakan data OHLC historis terdaftar.":b.detail??"Pencarian pola belum tersedia"); }
    finally { setBusy(false); }
  }
  async function find(){
    const value=toApiTimestamp(timestamp); if(!value){setMsg("Pilih tanggal dan waktu kondisi historis terlebih dahulu."); return;}
    setBusy(true); setMsg("");
    try { const r=await fetch(`/api/v1/similarity?timeframe=${tf}&timestamp=${encodeURIComponent(value)}`); const b=await r.json() as Similarity&ErrorBody; setSim(r.ok?b:null); setMsg(r.ok?"Kondisi historis serupa berhasil ditemukan.":b.detail??"Kondisi tersebut tidak tersedia untuk timeframe ini."); }
    finally { setBusy(false); }
  }
  function useSample(sample:Sample){ setTimestamp(sample.timestamp.replace(" ","T").slice(0,16)); setSim(null); document.getElementById("similarity")?.scrollIntoView({behavior:"smooth"}); }

  return <main className="backtest-page discovery-page"><header><div><Link className="back-link" href="/research">← Research Lab</Link><h1>Temukan Bukti Historis</h1><p>Cari pola pasar atau kondisi historis yang mirip. Hasil adalah bukti historis, bukan prediksi atau instruksi trading.</p></div><span className="mode-badge">RISET SAJA</span></header>
    <section className="backtest-content">
      <div className="discovery-goals">
        <section className="panel discovery-goal"><p className="discovery-kicker">TUJUAN 1</p><h2>Cari Pola Historis</h2><p>Biarkan ARKANA mencari kondisi pasar yang sering muncul dan menarik untuk diteliti.</p><label className="deploy-label">Timeframe analisis<select value={tf} onChange={e=>setTf(e.target.value)}>{frames.map(x=><option key={x}>{x}</option>)}</select></label><button className="run-button" disabled={busy} onClick={run}>{busy?"Memproses…":"Cari Pola Historis"}</button></section>
        <section id="similarity" className="panel discovery-goal"><p className="discovery-kicker">TUJUAN 2</p><h2>Cari Kondisi yang Mirip</h2><p>Pilih kondisi pasar historis dan lihat kejadian masa lalu yang paling mirip.</p><label className="deploy-label">Tanggal dan waktu historis<input type="datetime-local" step="60" value={timestamp} onChange={e=>setTimestamp(e.target.value)} /></label><button className="secondary" disabled={busy} onClick={find}>{busy?"Memproses…":"Cari Kondisi yang Mirip"}</button></section>
      </div>
      <details className="discovery-advanced" open={advanced} onToggle={e=>setAdvanced(e.currentTarget.open)}><summary>Pengaturan Lanjutan</summary><p>Timeframe menentukan candle yang dibandingkan. Metode, feature contract, batas minimum kejadian, dan pemisahan data dikunci untuk menjaga hasil dapat diaudit.</p>{data&&<p>Feature contract: <code>{data.version}</code> · fingerprint: <code>{data.fingerprint}</code> · dataset: {data.coverage.bar_count.toLocaleString("id-ID")} candle ({data.coverage.start} — {data.coverage.end}).</p>}</details>
      {msg&&<p className="notice">{msg}</p>}
      {data&&<section className="discovery-results"><div className="panel result-panel"><div className="panel-header"><div><p className="discovery-kicker">HASIL PENCARIAN POLA</p><h2>Pola yang Ditemukan</h2><p>{data.search_space.evaluated} kondisi diperiksa pada {data.timeframe}. Hasil di bawah bukan strategi otomatis.</p></div></div><div className="discovery-overview"><span><strong>{data.split.train_rows.toLocaleString("id-ID")}</strong><Help title={tooltip.discovery}>Data Penemuan</Help></span><span><strong>{data.split.holdout_rows.toLocaleString("id-ID")}</strong><Help title={tooltip.holdout}>Data Uji Baru</Help></span><span><strong>{data.split.minimum_support}</strong> minimum kejadian</span></div>
          <div className="discovery-cards">{data.candidates.map(candidate=>{const open=openCandidate===candidate.name;return <article className="discovery-card" key={candidate.name}><div className="discovery-card-head"><div><h3>{candidate.conditions.replaceAll("_"," ")}</h3><p className="status-friendly">{statusLabel[candidate.status]??candidate.status}</p></div><span className="status-chip">{candidate.status}</span></div><p>{statusExplanation[candidate.status]??"Status belum memiliki penjelasan tampilan."}</p><div className="discovery-total"><strong>{(candidate.train.occurrences+candidate.holdout.occurrences).toLocaleString("id-ID")}</strong><span>Jumlah Kejadian historis</span></div><div className="discovery-evidence-grid"><Evidence label="Hasil di Data Penemuan" outcome={candidate.train}/><Evidence label="Hasil di Data Uji Baru" outcome={candidate.holdout}/></div><div className="actions"><button className="secondary" onClick={()=>setOpenCandidate(open?null:candidate.name)}>{open?"Tutup Contoh":"Lihat Contoh Kejadian"}</button><button className="secondary" onClick={()=>setAdvanced(true)}>Lihat Detail Analisis</button></div>{open&&<div className="discovery-samples">{candidate.samples.map((sample,index)=><div key={`${candidate.name}-${sample.timestamp}`}><SampleViewer sample={sample} title={`Contoh kejadian ${index+1}`}/><button className="sample-use" onClick={()=>useSample(sample)}>Gunakan kondisi ini untuk mencari yang mirip</button></div>)}</div>}</article>})}</div><p className="warning-line">{data.warning}</p></div></section>}
      {sim&&<section className="panel result-panel discovery-similarity"><div className="panel-header"><div><p className="discovery-kicker">HASIL KONDISI SERUPA</p><h2>Kondisi Historis yang Mirip</h2><p>Dipilih: {sim.selected.timestamp} · {sim.analogs.length} kondisi serupa ditemukan</p></div></div><p className="warning-line">Historical evidence, bukan prediksi pergerakan berikutnya.</p><div className="discovery-evidence-grid"><article className="discovery-evidence"><small><Help title={tooltip.similarity}>Tingkat Kemiripan tertinggi</Help></small><strong>{percent(sim.analogs[0]?.similarity_score??null)}</strong><span>Skor kedekatan fitur OHLC, bukan probabilitas.</span></article><Evidence label="Rata-rata yang terjadi setelahnya" outcome={sim.aggregate}/><article className="discovery-evidence"><small>Gerakan setelah kejadian</small><strong>{signedPercent(sim.aggregate.mean_mfe)}</strong><span><Help title={tooltip.mfe}>Maksimum menguntungkan rata-rata</Help></span><em><Help title={tooltip.mae}>Maksimum berlawanan rata-rata</Help> {signedPercent(sim.aggregate.mean_mae)}</em></article></div><SampleViewer sample={sim.selected} title="Kondisi yang dipilih"/><div className="discovery-analog-list">{sim.analogs.map((analog,index)=><article className="discovery-analog" key={analog.timestamp}><button className="secondary" onClick={()=>setSelectedSample(selectedSample?.timestamp===analog.timestamp?null:analog)}>{selectedSample?.timestamp===analog.timestamp?"Tutup contoh":`Lihat contoh #${index+1}`}</button><div><h3>{analog.timestamp}</h3><p><Help title={tooltip.similarity}>Tingkat Kemiripan</Help> {percent(analog.similarity_score)} · Apa yang terjadi setelahnya: {signedPercent(analog.forward_return)} dalam 3 candle</p></div>{selectedSample?.timestamp===analog.timestamp&&<><SampleViewer sample={analog} title={`Kejadian serupa #${index+1}`}/><details><summary>Perbedaan Kondisi Pasar</summary><pre>{JSON.stringify(analog.feature_delta,null,2)}</pre></details></>}</article>)}</div><details className="discovery-advanced"><summary>Detail Analisis</summary><p>Technical method: embargo {sim.method.embargo_bars} candle untuk mencegah kondisi yang sama atau terlalu berdekatan menjadi analog. MFE/MAE dihitung dari OHLC yang tersedia; tidak mencakup Bid/Ask atau tick historis.</p><p>{sim.warning}</p></details></section>}
    </section>
  </main>;
}

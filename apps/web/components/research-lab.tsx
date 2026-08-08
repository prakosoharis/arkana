/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import Link from "next/link";
import React from "react";
import { useState } from "react";
import { CandlestickChart } from "./candlestick-chart";
import type { Bar } from "../lib/market";
import styles from "./research-lab.module.css";

type Hypothesis = { id: string; status: string; parser_source: string; source_prompt: string; definition: Record<string, any>; version: number };
type ResearchRun = { id: string; reused: boolean; result: { mode: string; timeframe: string; occurrence_count: number; sample_count: number; summary: Record<string, number>; warning: string }; samples: Sample[] };
type Sample = { timestamp: string; direction: string; move?: number; outcome_move?: number | null; context: Bar[] };

const orderBlockQuestion = "Cari bullish order block M5 ketika trend H1 bullish untuk target $3 dan $5.";
const priceQuestion = "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?";
const fomcQuestion = "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?";

export function ResearchLab() {
  const [question, setQuestion] = useState(orderBlockQuestion);
  const [hypothesis, setHypothesis] = useState<Hypothesis | null>(null);
  const [message, setMessage] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [sampleIndex, setSampleIndex] = useState(0);
  const definition = hypothesis?.definition ?? {};
  const typed = definition.definition ?? {};
  const canRun = hypothesis?.status === "READY_FOR_RESEARCH" && definition.execution_eligibility === "ELIGIBLE";

  function setTyped(key: string, value: any) {
    setHypothesis((current) => current ? { ...current, definition: { ...current.definition, definition: { ...current.definition.definition, [key]: value } } } : current);
  }

  async function build() {
    const response = await fetch("/api/v1/hypotheses/draft", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt: question }) });
    const body = await response.json();
    setHypothesis(response.ok ? body : null);
    setRun(null);
    setMessage(response.ok ? "Interpretation created. Review its fields and availability before saving." : body.detail ?? "Could not create draft.");
  }

  async function save() {
    if (!hypothesis) return;
    const response = await fetch(`/api/v1/hypotheses/${hypothesis.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ definition: hypothesis.definition }) });
    const body = await response.json();
    setHypothesis(response.ok ? body : hypothesis);
    setRun(null);
    setMessage(response.ok ? "Interpretation saved and eligibility reassessed. No research computation has run yet." : body.detail ?? "Could not save draft.");
  }

  async function execute() {
    if (!hypothesis) return;
    const response = await fetch("/api/v1/research-runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hypothesis_id: hypothesis.id }) });
    const body = await response.json();
    if (response.ok) {
      setRun(body);
      setSampleIndex(0);
      setMessage(body.reused ? "The identical registered hypothesis and dataset were already executed; its reproducible result was reused." : "Historical descriptive scan completed. Inspect the supporting candle samples below.");
    } else setMessage(body.detail ?? "Could not execute research.");
  }

  const selectedSample = run?.samples[sampleIndex];
  return <div className={styles.page}>
    <header className={styles.header}>
      <div><Link href="/" className={styles.back}>← Market &amp; Data</Link><p className={styles.eyebrow}>RESEARCH LAB · SPRINT 03</p><h1>Turn a question into inspectable historical research.</h1><p className={styles.lead}>ARKANA executes only a saved interpretation that is eligible against registered historical data. It does not create a signal, backtest, or trade instruction.</p></div>
      <span className={styles.badge}>RESEARCH ONLY</span>
    </header>
    <main className={styles.content}>
      <section className={styles.questionCard}>
        <div className={styles.cardTitle}><div><p className={styles.eyebrow}>STEP 1</p><h2>What do you want to investigate?</h2></div></div>
        <textarea aria-label="Research question" className={styles.question} value={question} onChange={(event) => setQuestion(event.target.value)} />
        <div className={styles.questionFooter}><div className={styles.examples}>Examples: <button onClick={() => setQuestion(priceQuestion)}>Price event</button><button onClick={() => setQuestion(orderBlockQuestion)}>Pattern</button><button onClick={() => setQuestion(fomcQuestion)}>FOMC event</button></div><button className={styles.primary} onClick={build}>Build interpretation →</button></div>
      </section>
      {message && <p className={styles.notice}>{message}</p>}
      {hypothesis && <section className={styles.draftCard}>
        <div className={styles.draftHead}><div><p className={styles.eyebrow}>STEP 2 · ARKANA&apos;S INTERPRETATION</p><h2>{definition.research_mode.replaceAll("_", " ")}</h2><p>Status: {hypothesis.status} · Version {hypothesis.version}</p></div><span className={styles.badge}>{hypothesis.status}</span></div>
        <div className={styles.summary}><span>Original question</span><strong>{hypothesis.source_prompt}</strong><span>Instrument</span><strong>{definition.instrument}</strong></div>
        <div className={styles.formGrid}>
          {definition.research_mode === "PATTERN_TO_OUTCOME" && <><label>Pattern<input value={typed.pattern ?? ""} onChange={(event) => setTyped("pattern", event.target.value)} /></label><label>Pattern timeframe<select value={typed.pattern_timeframe ?? "M5"} onChange={(event) => setTyped("pattern_timeframe", event.target.value)}>{["M1", "M5", "M15", "M30", "H1", "H4"].map((value) => <option key={value}>{value}</option>)}</select></label><label className={styles.wide}>Deterministic pattern definition<textarea value={typed.deterministic_pattern_definition ?? ""} onChange={(event) => setTyped("deterministic_pattern_definition", event.target.value)} /></label></>}
          {definition.research_mode === "PRICE_EVENT_TO_PATTERN" && <><label>Timeframe<select value={typed.timeframe ?? "M15"} onChange={(event) => setTyped("timeframe", event.target.value)}>{["M1", "M5", "M15", "M30", "H1", "H4"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Movement threshold<input type="number" step="any" value={typed.movement_threshold ?? ""} onChange={(event) => setTyped("movement_threshold", event.target.valueAsNumber)} /></label><label>Movement unit<select value={typed.movement_unit ?? "BROKER_POINTS"} onChange={(event) => setTyped("movement_unit", event.target.value)}><option value="BROKER_POINTS">Broker points (needs normalization)</option><option value="PRICE">Explicit XAUUSD price units</option></select></label><label>Broker normalization<input value={typed.broker_normalization_state ?? ""} onChange={(event) => setTyped("broker_normalization_state", event.target.value)} /></label></>}
          {definition.research_mode === "EXTERNAL_EVENT_TO_MARKET" && <><label>External event<input value={typed.external_event_type ?? ""} onChange={(event) => setTyped("external_event_type", event.target.value)} /></label><label>Event source<input value={typed.event_source ?? ""} onChange={(event) => setTyped("event_source", event.target.value)} /></label><label>Pre-event window<input value={typed.pre_event_window ?? ""} onChange={(event) => setTyped("pre_event_window", event.target.value)} /></label></>}
        </div>
        <div className={styles.warning}><strong>Availability assessment · {definition.execution_eligibility}</strong>{definition.data_requirements.map((item: any) => <span key={item.name}>{item.name}: {item.availability}</span>)}{definition.analytical_capability_requirements?.map((item: any) => <span key={item.id}>{item.id}: {item.available ? "AVAILABLE" : "NOT SUPPORTED"}</span>)}</div>
        <div className={styles.saveBar}><span>Save after editing to refresh eligibility. A run becomes available only for READY FOR RESEARCH / ELIGIBLE.</span><div className={styles.actions}><button className={styles.secondary} onClick={save}>Save interpretation</button><button className={styles.primary} disabled={!canRun} onClick={execute}>Run eligible research</button></div></div>
      </section>}
      {run && <section className={styles.resultsCard}><div className={styles.draftHead}><div><p className={styles.eyebrow}>STEP 3 · HISTORICAL RESULT</p><h2>{run.result.occurrence_count} matching occurrences</h2><p>{run.result.timeframe} · {run.result.sample_count} stored samples · run {run.id.slice(0, 8)}</p></div><span className={styles.badge}>COMPLETED</span></div><p className={styles.resultWarning}>{run.result.warning}</p><div className={styles.summaryMetrics}>{Object.entries(run.result.summary).map(([label, value]) => <span key={label}><strong>{value}</strong>{label.replaceAll("_", " ")}</span>)}</div>{run.samples.length > 0 ? <div className={styles.sampleArea}><div className={styles.sampleList}>{run.samples.map((sample, index) => <button key={`${sample.timestamp}-${index}`} className={index === sampleIndex ? styles.sampleActive : styles.sampleButton} onClick={() => setSampleIndex(index)}><strong>#{index + 1} · {sample.direction}</strong><span>{sample.timestamp}</span><span>{sample.move !== undefined ? `Move ${sample.move.toFixed(3)}` : sample.outcome_move === null ? "Outcome unavailable" : `Next move ${sample.outcome_move?.toFixed(3)}`}</span></button>)}</div><div className={styles.chartPanel}><p className={styles.eyebrow}>VISUAL VALIDATION · SAMPLE #{sampleIndex + 1}</p><CandlestickChart bars={selectedSample?.context ?? []} /><p>Showing the matching candle with up to two preceding and two following registered bars. Timestamp: {selectedSample?.timestamp}.</p></div></div> : <p className={styles.empty}>No occurrences met the saved definition in this registered dataset. This is a result, not an error.</p>}</section>}
    </main>
  </div>;
}

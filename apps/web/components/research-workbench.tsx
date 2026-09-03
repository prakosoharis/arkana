"use client";

import Link from "next/link";
import React, { useState } from "react";

import { LevelTouchLab } from "./level-touch-lab";
import { MarketExplorer } from "./market-explorer";

/**
 * ARK-S28-03. One menu for the questions that need no strategy.
 *
 * These shipped as two sidebar entries a sprint apart, which is how the
 * navigation came to be organised by the order things were built rather than
 * by what the Owner is trying to find out. Both answer "what does this market
 * actually do", neither creates a strategy, and both are bounded by the same
 * partition rule -- so they are one screen with two tabs.
 */
const TABS = [
  { id: "waktu", label: "Pola & Waktu", hint: "Jam berapa sering merah, rentetan, pola lanjutan" },
  { id: "sentuhan", label: "Sentuhan Garis", hint: "Harga menyentuh EMA: duluan TP atau SL?" },
] as const;

export type WorkbenchTab = (typeof TABS)[number]["id"];

export function ResearchWorkbench({ initial = "waktu" }: { initial?: WorkbenchTab }) {
  const [tab, setTab] = useState<WorkbenchTab>(initial);
  const active = TABS.find(item => item.id === tab) ?? TABS[0];
  return <main className="backtest-page">
    <header>
      <div>
        <Link className="back-link" href="/">← Data Pasar</Link>
        <h1>Riset Pasar</h1>
        <p>{active.hint} · Belum ada strategi, belum ada sinyal.</p>
      </div>
      <span className="mode-badge">PENGUKURAN SAJA</span>
    </header>
    <section className="backtest-content">
      <div className="timeframes workbench-tabs">
        {TABS.map(item => <button key={item.id} className={item.id === tab ? "selected" : ""} onClick={() => setTab(item.id)}>
          {item.label}<small> · {item.hint}</small>
        </button>)}
      </div>
      {tab === "waktu" ? <MarketExplorer embedded /> : <LevelTouchLab embedded />}
    </section>
  </main>;
}

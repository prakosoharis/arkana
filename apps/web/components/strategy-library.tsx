"use client";

import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";

type Candidate = { id: string; name: string; source: string; status: string; provenance: Record<string, unknown> };
type Contract = { stop_loss_rule: { distance: number; [key: string]: unknown }; take_profit_rule: { distance: number; [key: string]: unknown }; no_trade_conditions: Array<{ block_id: string; maximum?: number; [key: string]: unknown }>; cost_assumptions: { commission_price: number } };
type Strategy = { id: string; name: string; strategy_key: string; version: number; profile: string; status: string; checksum: string; backtest_run_id: string | null; strategy_candidate_id: string | null; strategy_contract: Contract | null; configuration: { entry?: { rule_set?: string }; strategy_contract_fingerprint?: string } };
type Validation = { ready: boolean; fingerprint?: string; issues?: string[] };
type Backtest = { id: string; fingerprint: string; reused: boolean; result: { warning: string; metrics: { trade_count: number; net_pnl_price: number }; strategy_lineage?: { evaluator_version: string; strategy_contract_fingerprint: string; execution_semantics: { entry_timing: string; ambiguity_policy: string } } | null } };

const defaultDraft = { name: "Legacy Compatibility Candidate", source: "MANUAL", note: "Created in Strategy Factory UI" };
const defaultTerms = { stop: 0.1, target: 0.1, spread: 0.02, commission: 0 };

function contractFor(terms: typeof defaultTerms): Contract & Record<string, unknown> {
  const completed = { block_id: "ALWAYS", uses_completed_candles: true };
  return {
    schema_version: 1, instrument: "XAUUSD", direction_eligibility: "LONG", context_timeframes: ["M1"], setup_timeframes: ["M1"], execution_timeframe: "M1",
    context_rules: [completed], setup_rules: [completed], trigger_rules: [{ block_id: "CANDLE_DIRECTION", uses_completed_candles: true, previous: "BEARISH", current: "BULLISH" }, { block_id: "SEQUENCE_PREVIOUS_THEN_CURRENT", uses_completed_candles: true }],
    entry_rule: { block_id: "NEXT_BAR_OPEN", uses_completed_candles: true, uses_future_ohlc: false }, invalidation_rule: completed,
    stop_loss_rule: { block_id: "FIXED_PRICE_DISTANCE_SL", uses_completed_candles: true, unit: "PRICE", distance: terms.stop },
    take_profit_rule: { block_id: "FIXED_PRICE_DISTANCE_TP", uses_completed_candles: true, unit: "PRICE", distance: terms.target },
    position_sizing_rule: { block_id: "FIXED_LOT_DEMO", uses_completed_candles: true, volume: 0.01 },
    no_trade_conditions: [{ block_id: "FIXED_SPREAD_GUARD", uses_completed_candles: true, unit: "PRICE", maximum: terms.spread }, { block_id: "MAX_OPEN_POSITIONS", uses_completed_candles: true, maximum: 1 }, { block_id: "STOP_FIRST", uses_completed_candles: true }],
    cost_assumptions: { commission_price: terms.commission }, provenance: { source: "STRATEGY_FACTORY_UI" },
  };
}

function ruleName(item: Strategy) { return item.strategy_contract ? "Legacy bullish reversal compatibility contract" : item.configuration.entry?.rule_set ?? "Legacy recorded strategy"; }
function errorOf(body: unknown) { return typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : "Request could not be completed."; }

export function StrategyLibrary() {
  const [items, setItems] = useState<Strategy[]>([]); const [candidates, setCandidates] = useState<Candidate[]>([]); const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState(defaultDraft); const [terms, setTerms] = useState(defaultTerms); const [validation, setValidation] = useState<Validation | null>(null); const [run, setRun] = useState<Backtest | null>(null);
  const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  const contract = useMemo(() => contractFor(terms), [terms]);
  const load = async () => {
    const [versions, factory] = await Promise.all([fetch("/api/v1/strategy-versions", { cache: "no-store" }), fetch("/api/v1/strategy-candidates", { cache: "no-store" })]);
    const versionBody = await versions.json(); const factoryBody = await factory.json();
    if (versions.ok) setItems(versionBody.strategy_versions ?? []); else setMessage(errorOf(versionBody));
    if (factory.ok) { const next = factoryBody.strategy_candidates ?? []; setCandidates(next); setSelected(current => current || next[0]?.id || ""); } else setMessage(errorOf(factoryBody));
  };
  useEffect(() => { void load(); }, []);
  const request = async (url: string, body?: unknown) => {
    const response = await fetch(url, { method: "POST", headers: body ? { "content-type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
    const value = await response.json(); if (!response.ok) throw Error(errorOf(value)); return value;
  };
  async function createCandidate() {
    setBusy(true); setMessage(""); try {
      const created = await request("/api/v1/strategy-candidates", { name: draft.name, source: draft.source, provenance: { note: draft.note, source: "STRATEGY_FACTORY_UI" } }) as Candidate;
      setCandidates(current => [created, ...current]); setSelected(created.id); setMessage("Draft candidate tersimpan. Validasi contract sebelum mengonfirmasi versi.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Candidate gagal dibuat."); } finally { setBusy(false); }
  }
  async function validateContract() {
    setBusy(true); setMessage(""); try {
      const report = await request("/api/v1/strategy-candidates/validate", { strategy_contract: contract }) as Validation;
      setValidation(report); setMessage(report.ready ? "Contract valid untuk capability compatibility yang tersedia." : "Contract belum valid; lihat issues.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Validasi gagal."); } finally { setBusy(false); }
  }
  async function confirmVersion() {
    if (!selected) { setMessage("Buat atau pilih draft candidate terlebih dahulu."); return; }
    setBusy(true); setMessage(""); try {
      const version = await request("/api/v1/strategy-versions/confirm", { strategy_candidate_id: selected, strategy_contract: contract }) as Strategy;
      setItems(current => [version, ...current]); setValidation({ ready: true, fingerprint: version.configuration.strategy_contract_fingerprint }); setMessage("StrategyVersion CONTRACT_VALID dibuat. Jalankan canonical backtest untuk merekam evidence.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Version tidak dapat dikonfirmasi."); } finally { setBusy(false); }
  }
  async function backtest(version: Strategy) {
    setBusy(true); setMessage(""); try {
      const result = await request("/api/v1/backtests", { strategy_version_id: version.id }) as Backtest;
      setRun(result); setMessage(result.reused ? "Evidence dengan input identik digunakan kembali." : "Canonical Backtest V1 selesai direkam.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Backtest gagal."); } finally { setBusy(false); }
  }
  async function revise(version: Strategy) {
    setBusy(true); try { const candidate = await request(`/api/v1/strategy-versions/${version.id}/revision`) as Candidate; setCandidates(current => [candidate, ...current]); setSelected(candidate.id); setMessage("Draft revisi dibuat. Version yang telah dikonfirmasi tidak diubah."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Revisi gagal dibuat."); } finally { setBusy(false); }
  }
  async function approve(id: string) { setBusy(true); try { await request(`/api/v1/strategy-versions/${id}/approve`); setMessage("Manual approval legacy tercatat. Ini tidak melakukan deployment."); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Approval gagal."); } finally { setBusy(false); } }
  const updateTerm = (key: keyof typeof defaultTerms, value: number) => { setTerms(current => ({ ...current, [key]: value })); setValidation(null); };

  return <main className="backtest-page"><header><div><Link className="back-link" href="/backtest">← Backtest Lab</Link><h1>Strategy Factory</h1><p>Build an inspectable compatibility contract, then record canonical historical evidence.</p></div><span className="mode-badge">NO LIVE ACTION</span></header><section className="backtest-content">
    {message && <p className="notice">{message}</p>}
    <section className="factory-grid"><section className="panel backtest-config factory-panel"><p className="discovery-kicker">1 · DRAFT CANDIDATE</p><h2>Identity and provenance</h2><label className="deploy-label">Name<input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label><label className="deploy-label">Source<select value={draft.source} onChange={event => setDraft({ ...draft, source: event.target.value })}><option>MANUAL</option><option>RESEARCH</option><option>DISCOVERY</option><option>ANALOG</option><option>KNOWN_METHOD</option><option>AI_ASSISTED</option></select></label><label className="deploy-label">Provenance note<input value={draft.note} onChange={event => setDraft({ ...draft, note: event.target.value })} /></label><button className="secondary" disabled={busy || !draft.name.trim() || !draft.note.trim()} onClick={createCandidate}>Save draft candidate</button><label className="deploy-label">Draft used for this contract<select value={selected} onChange={event => setSelected(event.target.value)}><option value="">Choose draft candidate</option>{candidates.map(candidate => <option value={candidate.id} key={candidate.id}>{candidate.name} · {candidate.status}</option>)}</select></label></section>
      <section className="panel backtest-config factory-panel"><p className="discovery-kicker">2 · CONTRACT</p><h2>Legacy-compatible V1 terms</h2><p className="muted">Only completed M1 candles, LONG, next-bar open, one position, and STOP_FIRST are supported in this thin slice.</p><div className="backtest-form">{([ ["stop", "Stop distance"], ["target", "Target distance"], ["spread", "Spread guard"], ["commission", "Commission price"] ] as Array<[keyof typeof defaultTerms, string]>).map(([key, label]) => <label key={key}>{label}<input aria-label={label} type="number" min="0" step="0.01" value={terms[key]} onChange={event => updateTerm(key, event.target.valueAsNumber)} /></label>)}</div><div className="actions"><button className="secondary" disabled={busy} onClick={validateContract}>Validate contract</button><button className="run-button" disabled={busy || !selected || validation?.ready !== true} onClick={confirmVersion}>Confirm immutable version</button></div>{validation && <div className={validation.ready ? "factory-state ready" : "factory-state invalid"}><strong>{validation.ready ? "CONTRACT VALID" : "CONTRACT NEEDS FIXES"}</strong><span>{validation.fingerprint ? `Fingerprint ${validation.fingerprint.slice(0, 16)}` : validation.issues?.join(" ")}</span></div>}</section>
      <section className="panel backtest-info factory-panel"><p className="discovery-kicker">WHAT THIS DOES NOT DO</p><h2>Safety boundary</h2><p>Confirmation creates an immutable contract version; it does not mark it <strong>VALIDATED</strong>, approve it, deploy it, configure MT5, or create an order.</p><p>Backtest V1 remains a single canonical kernel. This UI only reaches it through the recorded contract adapter.</p><p>Full OOS/robustness gates and any route to VALIDATED remain outside this checkpoint.</p></section></section>
    {run && <section className="panel result-panel factory-evidence"><div className="panel-header"><div><p className="discovery-kicker">CANONICAL BACKTEST EVIDENCE</p><h2>{run.reused ? "Recorded evidence reused" : "New evidence recorded"}</h2><p>Run {run.id.slice(0, 8)} · fingerprint {run.fingerprint.slice(0, 16)}</p></div><span className="mode-badge">HISTORICAL ONLY</span></div><section className="command-metrics"><article><small>Trades</small><strong>{run.result.metrics.trade_count}</strong></article><article><small>Net price PnL</small><strong>{run.result.metrics.net_pnl_price}</strong></article><article><small>Entry timing</small><strong>{run.result.strategy_lineage?.execution_semantics.entry_timing ?? "Legacy"}</strong></article><article><small>Ambiguity</small><strong>{run.result.strategy_lineage?.execution_semantics.ambiguity_policy ?? "Legacy"}</strong></article></section><p className="warning-line">{run.result.warning}</p><details className="discovery-advanced"><summary>Lineage evidence</summary><pre>{JSON.stringify(run.result.strategy_lineage, null, 2)}</pre></details></section>}
    <section className="panel result-panel"><div className="panel-header"><div><h2>Version registry</h2><p>Contract versions can be backtested or revised. Legacy candidates retain their established manual approval flow.</p></div></div>{items.length ? <div className="strategy-list">{items.map(item => <article className="strategy-card" key={item.id}><div><small>{item.status} · {item.profile} · v{item.version}.0.0</small><h2>{item.name}</h2><p>{ruleName(item)}</p><p className="muted">Checksum {item.checksum.slice(0, 12)} · {item.backtest_run_id ? `Legacy backtest ${item.backtest_run_id.slice(0, 8)}` : item.strategy_contract ? "Contract version; evidence not yet selected" : "No backtest reference"}</p></div><div className="actions">{item.strategy_contract && <><button className="run-button" disabled={busy} onClick={() => backtest(item)}>Run canonical backtest</button><button className="secondary" disabled={busy} onClick={() => revise(item)}>Create revision draft</button></>}{item.status === "CANDIDATE" && <button className="run-button" disabled={busy} onClick={() => approve(item.id)}>Approve legacy manually</button>}{item.status === "APPROVED" && <span className="mode-badge">APPROVED · NOT DEPLOYED</span>}{item.status === "CONTRACT_VALID" && <span className="mode-badge">CONTRACT VALID · NOT VALIDATED</span>}</div></article>)}</div> : <p className="muted empty-library">No strategy version yet. Create a draft, validate its contract, then confirm an immutable version.</p>}</section>
  </section></main>;
}

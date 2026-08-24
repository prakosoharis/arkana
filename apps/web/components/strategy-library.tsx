"use client";

import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";

type Candidate = { id: string; name: string; source: string; status: string; provenance: Record<string, unknown> };
type Contract = { stop_loss_rule: { distance: number; [key: string]: unknown }; take_profit_rule: { distance: number; [key: string]: unknown }; no_trade_conditions: Array<{ block_id: string; maximum?: number; [key: string]: unknown }>; cost_assumptions: { commission_price: number } };
type Strategy = { id: string; name: string; strategy_key: string; version: number; profile: string; status: string; checksum: string; backtest_run_id: string | null; strategy_candidate_id: string | null; strategy_contract: Contract | null; validation_evidence_id: string | null; validated_at: string | null; configuration: { entry?: { rule_set?: string }; strategy_contract_fingerprint?: string } };
type Validation = { ready: boolean; fingerprint?: string; issues?: string[] };
type CapabilityRegistry = { version: string; fingerprint: string; blocks: Array<{ id: string; category: string; execution: string; completed_candles: boolean }> };
type EvaluatorVerification = { owner_acceptance_readiness: string; fingerprint: string; checks: Record<string, { status: string }> };
type Backtest = { id: string; strategy_version_id: string | null; fingerprint: string; reused: boolean; result: { warning: string; metrics: { trade_count: number; net_pnl_price: number }; strategy_lineage?: { evaluator_version: string; execution_semantics: { entry_timing: string; ambiguity_policy: string } } | null } };
type SplitEvidence = { metrics: { trade_count: number; net_pnl_price: number; profit_factor: number | "INFINITE" | null } };
type GateCheck = { status: string; observed?: unknown; minimum_each?: number; strictly_greater_than?: number; maximum_observed?: number | null; maximum_allowed?: number };
export type OosEvidence = { id: string; fingerprint: string; reused?: boolean; protocol: { version: string }; result: { status: string; warning: string; gate_evaluation: { decision: "PASS" | "FAIL" | "INSUFFICIENT_EVIDENCE"; checks: Record<string, GateCheck> }; cost_stress: { scenarios: { baseline: { splits: Record<"train" | "holdout" | "final_oos", SplitEvidence> }; adverse_cost: { splits: Record<"train" | "holdout" | "final_oos", SplitEvidence> } } } } };
type OosEvidenceList = { validations: unknown[] };

const defaultDraft = { name: "Legacy Compatibility Candidate", source: "MANUAL", note: "Created in Strategy Factory UI" };
const defaultTerms = { stop: 0.1, target: 0.1, spread: 0.02, commission: 0 };

function contractFor(terms: typeof defaultTerms, expression: "LEGACY" | "M1_M5_COMPLETED"): Contract & Record<string, unknown> {
  const completed = { block_id: "ALWAYS", uses_completed_candles: true };
  const contract = {
    schema_version: 1, instrument: "XAUUSD", direction_eligibility: "LONG", context_timeframes: ["M1"], setup_timeframes: ["M1"], execution_timeframe: "M1",
    context_rules: [completed], setup_rules: [completed], trigger_rules: [{ block_id: "CANDLE_DIRECTION", uses_completed_candles: true, previous: "BEARISH", current: "BULLISH" }, { block_id: "SEQUENCE_PREVIOUS_THEN_CURRENT", uses_completed_candles: true }],
    entry_rule: { block_id: "NEXT_BAR_OPEN", uses_completed_candles: true, uses_future_ohlc: false }, invalidation_rule: completed,
    stop_loss_rule: { block_id: "FIXED_PRICE_DISTANCE_SL", uses_completed_candles: true, unit: "PRICE", distance: terms.stop },
    take_profit_rule: { block_id: "FIXED_PRICE_DISTANCE_TP", uses_completed_candles: true, unit: "PRICE", distance: terms.target },
    position_sizing_rule: { block_id: "FIXED_LOT_DEMO", uses_completed_candles: true, volume: 0.01 },
    no_trade_conditions: [{ block_id: "FIXED_SPREAD_GUARD", uses_completed_candles: true, unit: "PRICE", maximum: terms.spread }, { block_id: "MAX_OPEN_POSITIONS", uses_completed_candles: true, maximum: 1 }, { block_id: "STOP_FIRST", uses_completed_candles: true }],
    cost_assumptions: { commission_price: terms.commission }, provenance: { source: "STRATEGY_FACTORY_UI" },
  } as Contract & Record<string, unknown>;
  if (expression === "M1_M5_COMPLETED") {
    contract.context_timeframes = ["M1", "M5"]; contract.setup_timeframes = ["M1"];
    contract.context_rules = [{ block_id: "SMA_RELATION", uses_completed_candles: true, timeframe: "M5", fast_period: 2, slow_period: 5, relation: "ABOVE" }];
    contract.setup_rules = [{ block_id: "TWO_BAR_REVERSAL", uses_completed_candles: true, timeframe: "M1", direction: "BULLISH" }];
    contract.trigger_rules = [{ block_id: "ALL_OF", uses_completed_candles: true, children: [{ block_id: "CANDLE_DIRECTION", uses_completed_candles: true, timeframe: "M1", direction: "BULLISH" }, { block_id: "NOT", uses_completed_candles: true, child: { block_id: "CANDLE_DIRECTION", uses_completed_candles: true, timeframe: "M1", direction: "BEARISH" } }] }];
  }
  return contract;
}

function ruleName(item: Strategy) { return item.strategy_contract ? "Legacy bullish reversal compatibility contract" : item.configuration.entry?.rule_set ?? "Legacy recorded strategy"; }
function errorOf(body: unknown) { return typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : "Request could not be completed."; }
const checkLabels: Record<string, string> = { minimum_trades: "Minimum 100 trades per OOS partition", regime_calibration: "Train-only regime calibration", positive_net_pnl_after_costs: "Positive nominal net PnL", profit_factor: "Profit Factor strictly above 1.10", adverse_final_oos_nonnegative: "Adverse final OOS nonnegative", year_pnl_concentration: "Year PnL concentration ≤ 50%", regime_pnl_concentration: "Regime PnL concentration ≤ 50%" };

export function latestRenderableOosEvidence(values: unknown[]): OosEvidence | undefined {
  return values.find((value): value is OosEvidence => {
    if (!value || typeof value !== "object") return false;
    const item = value as Partial<OosEvidence>;
    const scenarios = item.result?.cost_stress?.scenarios;
    return item.protocol?.version === "OOS_HISTORICAL_REVIEW_V3" &&
      typeof item.id === "string" && typeof item.fingerprint === "string" &&
      typeof item.result?.warning === "string" && !!item.result.gate_evaluation?.checks &&
      !!scenarios?.baseline?.splits && !!scenarios.adverse_cost?.splits;
  });
}

export function RobustnessEvidence({ evidence }: { evidence: OosEvidence }) {
  const gate = evidence.result.gate_evaluation; const baseline = evidence.result.cost_stress.scenarios.baseline.splits; const adverse = evidence.result.cost_stress.scenarios.adverse_cost.splits;
  return <section className="panel result-panel factory-evidence" aria-label="Historical robustness evidence"><div className="panel-header"><div><p className="discovery-kicker">HISTORICAL ROBUSTNESS EVIDENCE · {evidence.protocol.version}</p><h2>{gate.decision}</h2><p>Evidence {evidence.id.slice(0, 8)} · fingerprint {evidence.fingerprint.slice(0, 16)}{evidence.reused ? " · reused" : ""}</p></div><span className="mode-badge">{gate.decision === "PASS" ? "VALIDATED · HISTORICAL ONLY" : "NOT VALIDATED"}</span></div>
    <section className="command-metrics"><article><small>Holdout trades</small><strong>{baseline.holdout.metrics.trade_count}</strong></article><article><small>Holdout net / PF</small><strong>{baseline.holdout.metrics.net_pnl_price} / {String(baseline.holdout.metrics.profit_factor)}</strong></article><article><small>Final OOS net / PF</small><strong>{baseline.final_oos.metrics.net_pnl_price} / {String(baseline.final_oos.metrics.profit_factor)}</strong></article><article><small>Adverse final net</small><strong>{adverse.final_oos.metrics.net_pnl_price}</strong></article></section>
    <div className="strategy-list">{Object.entries(gate.checks).map(([key, check]) => <article className="strategy-card" key={key}><div><small>{check.status}</small><strong>{checkLabels[key] ?? key}</strong><p className="muted">Observed: {JSON.stringify(check.observed ?? check.maximum_observed ?? "see evidence")}</p></div><span className="mode-badge">{check.status}</span></article>)}</div>
    <p className="warning-line">{evidence.result.warning}</p><p className="warning-line"><strong>No automatic DEMO or LIVE action.</strong> PASS is historical validation only.</p><details className="discovery-advanced"><summary>Complete immutable evidence</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details></section>;
}

export function StrategyLibrary() {
  const [items, setItems] = useState<Strategy[]>([]); const [candidates, setCandidates] = useState<Candidate[]>([]); const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState(defaultDraft); const [terms, setTerms] = useState(defaultTerms); const [validation, setValidation] = useState<Validation | null>(null); const [run, setRun] = useState<Backtest | null>(null); const [oos, setOos] = useState<OosEvidence | null>(null);
  const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false); const [registry, setRegistry] = useState<CapabilityRegistry | null>(null); const [verification, setVerification] = useState<EvaluatorVerification | null>(null); const [expression, setExpression] = useState<"LEGACY" | "M1_M5_COMPLETED">("LEGACY");
  const contract = useMemo(() => contractFor(terms, expression), [terms, expression]);
  const load = async () => {
    const [versions, factory] = await Promise.all([fetch("/api/v1/strategy-versions", { cache: "no-store" }), fetch("/api/v1/strategy-candidates", { cache: "no-store" })]);
    const versionBody = await versions.json(); const factoryBody = await factory.json();
    if (versions.ok) setItems(versionBody.strategy_versions ?? []); else setMessage(errorOf(versionBody));
    if (factory.ok) { const next = factoryBody.strategy_candidates ?? []; setCandidates(next); setSelected(current => current || next[0]?.id || ""); } else setMessage(errorOf(factoryBody));
  };
  useEffect(() => { void load(); void fetch("/api/v1/strategy-capabilities", { cache: "no-store" }).then(response => response.json()).then(setRegistry).catch(() => undefined); }, []);
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
  async function verifyEvaluatorEvidence() { if (!run?.strategy_version_id) return; setBusy(true); try { const value = await request(`/api/v1/strategy-versions/${run.strategy_version_id}/backtests/${run.id}/verification`) as EvaluatorVerification; setVerification(value); setMessage(value.owner_acceptance_readiness === "READY_FOR_OWNER_ACCEPTANCE" ? "Evaluator verifier PASSED; artifact immutable dan read-only." : "Evaluator verifier menemukan invariant yang gagal."); } catch (error) { setMessage(error instanceof Error ? error.message : "Verifier gagal."); } finally { setBusy(false); } }
  async function revise(version: Strategy) {
    setBusy(true); try { const candidate = await request(`/api/v1/strategy-versions/${version.id}/revision`) as Candidate; setCandidates(current => [candidate, ...current]); setSelected(candidate.id); setMessage("Draft revisi dibuat. Version yang telah dikonfirmasi tidak diubah."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Revisi gagal dibuat."); } finally { setBusy(false); }
  }
  async function validateOos(version: Strategy) {
    setBusy(true); setMessage(""); try {
      const evidence = await request(`/api/v1/strategy-versions/${version.id}/oos-validations`) as OosEvidence;
      setOos(evidence); setMessage(evidence.result.gate_evaluation.decision === "PASS" ? "Historical robustness gate PASS. StrategyVersion berstatus VALIDATED, tetapi tetap bukan DEMO/LIVE-ready." : `Historical robustness decision: ${evidence.result.gate_evaluation.decision}. Tidak ada promosi.`); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "OOS robustness gate gagal."); } finally { setBusy(false); }
  }
  async function viewLatestOos(version: Strategy) {
    setBusy(true); setMessage(""); try {
      const response = await fetch(`/api/v1/strategy-versions/${version.id}/oos-validations`, { cache: "no-store" });
      const body = await response.json() as OosEvidenceList & { detail?: unknown };
      if (!response.ok) throw Error(errorOf(body));
      const evidence = latestRenderableOosEvidence(body.validations ?? []);
      if (!evidence) { setMessage("Belum ada protocol V3 historical robustness evidence untuk versi ini."); return; }
      setOos(evidence); setMessage(`Evidence terbaru dibuka: ${evidence.result.gate_evaluation.decision}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Evidence tidak dapat dibuka."); } finally { setBusy(false); }
  }
  async function approve(id: string) { setBusy(true); try { await request(`/api/v1/strategy-versions/${id}/approve`); setMessage("Manual approval legacy tercatat. Ini tidak melakukan deployment."); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Approval gagal."); } finally { setBusy(false); } }
  const updateTerm = (key: keyof typeof defaultTerms, value: number) => { setTerms(current => ({ ...current, [key]: value })); setValidation(null); };

  return <main className="backtest-page"><header><div><Link className="back-link" href="/backtest">← Backtest Lab</Link><h1>Strategy Factory</h1><p>Build an inspectable compatibility contract, then record canonical historical evidence.</p></div><span className="mode-badge">NO LIVE ACTION</span></header><section className="backtest-content">
    {message && <p className="notice">{message}</p>}
    {registry && <section className="panel result-panel factory-evidence"><p className="discovery-kicker">REGISTERED EVALUATOR CAPABILITIES · {registry.version}</p><p className="muted">Only listed completed-candle blocks are accepted. Unsupported fields are rejected by the API; this UI does not submit hidden defaults.</p><div className="strategy-list">{registry.blocks.map(block => <article className="strategy-card" key={block.id}><div><strong>{block.id}</strong><p>{block.category} · {block.execution} · completed candles: {String(block.completed_candles)}</p></div></article>)}</div></section>}
    <section className="factory-grid"><section className="panel backtest-config factory-panel"><p className="discovery-kicker">1 · DRAFT CANDIDATE</p><h2>Identity and provenance</h2><label className="deploy-label">Name<input value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label><label className="deploy-label">Source<select value={draft.source} onChange={event => setDraft({ ...draft, source: event.target.value })}><option>MANUAL</option><option>RESEARCH</option><option>DISCOVERY</option><option>ANALOG</option><option>KNOWN_METHOD</option><option>AI_ASSISTED</option></select></label><label className="deploy-label">Provenance note<input value={draft.note} onChange={event => setDraft({ ...draft, note: event.target.value })} /></label><button className="secondary" disabled={busy || !draft.name.trim() || !draft.note.trim()} onClick={createCandidate}>Save draft candidate</button><label className="deploy-label">Draft used for this contract<select value={selected} onChange={event => setSelected(event.target.value)}><option value="">Choose draft candidate</option>{candidates.map(candidate => <option value={candidate.id} key={candidate.id}>{candidate.name} · {candidate.status}</option>)}</select></label></section>
      <section className="panel backtest-config factory-panel"><p className="discovery-kicker">2 · CONTRACT</p><h2>Registered V1 expression</h2><label className="deploy-label">Completed-candle block picker<select value={expression} onChange={event => { setExpression(event.target.value as "LEGACY" | "M1_M5_COMPLETED"); setValidation(null); }}><option value="LEGACY">Legacy bullish reversal · M1</option><option value="M1_M5_COMPLETED">SMA M5 + bullish reversal M1</option></select></label><p className="muted">The picker offers only registered blocks. Both expressions remain XAUUSD LONG, next-bar open, one position, and STOP_FIRST.</p><div className="backtest-form">{([ ["stop", "Stop distance"], ["target", "Target distance"], ["spread", "Spread guard"], ["commission", "Commission price"] ] as Array<[keyof typeof defaultTerms, string]>).map(([key, label]) => <label key={key}>{label}<input aria-label={label} type="number" min="0" step="0.01" value={terms[key]} onChange={event => updateTerm(key, event.target.valueAsNumber)} /></label>)}</div><div className="actions"><button className="secondary" disabled={busy} onClick={validateContract}>Validate contract</button><button className="run-button" disabled={busy || !selected || validation?.ready !== true} onClick={confirmVersion}>Confirm immutable version</button></div>{validation && <div className={validation.ready ? "factory-state ready" : "factory-state invalid"}><strong>{validation.ready ? "CONTRACT VALID" : "CONTRACT NEEDS FIXES"}</strong><span>{validation.fingerprint ? `Fingerprint ${validation.fingerprint.slice(0, 16)}` : validation.issues?.join(" ")}</span></div>}</section>
      <section className="panel backtest-info factory-panel"><p className="discovery-kicker">WHAT THIS DOES NOT DO</p><h2>Safety boundary</h2><p>Confirmation alone does not mark a version <strong>VALIDATED</strong>, deploy it, configure MT5, or create an order.</p><p>Backtest V1 remains the single canonical kernel. The historical robustness gate may set VALIDATED only when every frozen check passes.</p><p><strong>VALIDATED is historical-only.</strong> It never means DEMO-ready, LIVE-ready, routed, or recommended.</p></section></section>
    {run && <section className="panel result-panel factory-evidence"><div className="panel-header"><div><p className="discovery-kicker">CANONICAL BACKTEST EVIDENCE</p><h2>{run.reused ? "Recorded evidence reused" : "New evidence recorded"}</h2><p>Run {run.id.slice(0, 8)} · fingerprint {run.fingerprint.slice(0, 16)}</p></div><span className="mode-badge">HISTORICAL ONLY</span></div><section className="command-metrics"><article><small>Trades</small><strong>{run.result.metrics.trade_count}</strong></article><article><small>Net price PnL</small><strong>{run.result.metrics.net_pnl_price}</strong></article><article><small>Entry timing</small><strong>{run.result.strategy_lineage?.execution_semantics.entry_timing ?? "Legacy"}</strong></article><article><small>Ambiguity</small><strong>{run.result.strategy_lineage?.execution_semantics.ambiguity_policy ?? "Legacy"}</strong></article></section>{run.strategy_version_id && <button className="secondary" disabled={busy} onClick={verifyEvaluatorEvidence}>Materialize evaluator acceptance verifier</button>}{verification && <p className="warning-line">Verifier: {verification.owner_acceptance_readiness} · {verification.fingerprint.slice(0, 16)} · {Object.values(verification.checks).every(check => check.status === "PASS") ? "all checks PASS" : "blocking check present"}</p>}<p className="warning-line">{run.result.warning}</p><details className="discovery-advanced"><summary>Lineage evidence</summary><pre>{JSON.stringify(run.result.strategy_lineage, null, 2)}</pre></details></section>}
    {oos && <RobustnessEvidence evidence={oos} />}
    <section className="panel result-panel"><div className="panel-header"><div><h2>Version registry</h2><p>Contract versions can be backtested, robustness-reviewed, or revised. Legacy candidates retain their established manual approval flow.</p></div></div>{items.length ? <div className="strategy-list">{items.map(item => <article className="strategy-card" key={item.id}><div><small>{item.status} · {item.profile} · v{item.version}.0.0</small><h2>{item.name}</h2><p>{ruleName(item)}</p><p className="muted">Checksum {item.checksum.slice(0, 12)} · {item.validation_evidence_id ? `Historical evidence ${item.validation_evidence_id.slice(0, 8)}` : item.backtest_run_id ? `Legacy backtest ${item.backtest_run_id.slice(0, 8)}` : item.strategy_contract ? "Contract version; evidence not yet selected" : "No backtest reference"}</p></div><div className="actions">{item.strategy_contract && <><button className="run-button" disabled={busy} onClick={() => backtest(item)}>Run canonical backtest</button><button className="run-button" disabled={busy} onClick={() => validateOos(item)}>Run OOS robustness gate</button><button className="secondary" disabled={busy} onClick={() => viewLatestOos(item)}>View latest OOS evidence</button><button className="secondary" disabled={busy} onClick={() => revise(item)}>Create revision draft</button></>}{item.status === "CANDIDATE" && <button className="run-button" disabled={busy} onClick={() => approve(item.id)}>Approve legacy manually</button>}{item.status === "APPROVED" && <span className="mode-badge">APPROVED · NOT DEPLOYED</span>}{item.status === "CONTRACT_VALID" && <span className="mode-badge">CONTRACT VALID · NOT VALIDATED</span>}{item.status === "VALIDATED" && <span className="mode-badge">VALIDATED · HISTORICAL ONLY</span>}</div></article>)}</div> : <p className="muted empty-library">No strategy version yet. Create a draft, validate its contract, then confirm an immutable version.</p>}</section>
  </section></main>;
}

"use client";

import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";

import { FixtureBadge, isFixture, type Lineage } from "../lib/lineage";

type Candidate = { id: string; name: string; source: string; status: string; provenance: Record<string, unknown> };
type Contract = { stop_loss_rule: { distance: number; [key: string]: unknown }; take_profit_rule: { distance: number; [key: string]: unknown }; no_trade_conditions: Array<{ block_id: string; maximum?: number; [key: string]: unknown }>; cost_assumptions: { commission_price: number } };
type Strategy = { id: string; name: string; strategy_key: string; version: number; profile: string; status: string; checksum: string; lineage?: Lineage; backtest_run_id: string | null; strategy_candidate_id: string | null; strategy_contract: Contract | null; validation_evidence_id: string | null; generic_validation_promotion_id: string | null; generic_validation_retirement_id: string | null; validated_at: string | null; retired_at: string | null; configuration: { entry?: { rule_set?: string }; strategy_contract_fingerprint?: string; strategy_capability_assessment?: { evaluator_capability_id?: string } } };
type Validation = { ready: boolean; status?: string; fingerprint?: string; issues?: string[] };
type CapabilityRegistry = { version: string; fingerprint: string; blocks: Array<{ id: string; category: string; execution: string; completed_candles: boolean }> };
type EvaluatorVerification = { owner_acceptance_readiness: string; fingerprint: string; checks: Record<string, { status: string }> };
type Backtest = { id: string; strategy_version_id: string | null; fingerprint: string; reused: boolean; result: { warning: string; metrics: { trade_count: number; net_pnl_price: number }; strategy_lineage?: { evaluator_version: string; execution_semantics: { entry_timing: string; ambiguity_policy: string } } | null } };
type SplitEvidence = { metrics: { trade_count: number; net_pnl_price: number; profit_factor: number | "INFINITE" | null } };
type GateCheck = { status: string; observed?: unknown; minimum_each?: number; strictly_greater_than?: number; maximum_observed?: number | null; maximum_allowed?: number };
export type OosEvidence = { id: string; fingerprint: string; reused?: boolean; protocol: { version: string }; result: { status: string; warning: string; gate_evaluation: { decision: "PASS" | "FAIL" | "INSUFFICIENT_EVIDENCE"; checks: Record<string, GateCheck> }; cost_stress: { scenarios: { baseline: { splits: Record<"train" | "holdout" | "final_oos", SplitEvidence> }; adverse_cost: { splits: Record<"train" | "holdout" | "final_oos", SplitEvidence> } } } } };
type OosEvidenceList = { validations: unknown[] };
type GenericOosEvidence = OosEvidence & { strategy_version_id: string; protocol: { version: "GENERIC_OOS_EVIDENCE_V1"; gate_policy: Record<string, unknown> } };
type GenericStabilityEvidence = { id: string; strategy_version_id: string; fingerprint: string; protocol_version: string; status: "PASS" | "FAIL" | "INSUFFICIENT_EVIDENCE"; policy: Record<string, unknown>; result: { stability: { candidate_count: number; supported_candidate_count: number; passing_candidate_count: number; passing_candidate_fraction: number; minimum_passing_candidate_fraction: number }; split_access: Record<string, unknown>; lifecycle: Record<string, boolean> } };
export type GenericDecision = { id: string; strategy_version_id: string; oos_validation_id: string; robustness_evidence_id: string; fingerprint: string; protocol_version: string; decision: "PASS" | "FAIL" | "INSUFFICIENT_EVIDENCE"; result: { source_outcomes: Record<string, string>; thresholds: Record<string, unknown>; observations: Record<string, unknown>; lineage: Record<string, unknown>; owner_gate: { acknowledgement_required: boolean; acknowledgement_creates_validation: boolean; future_promotion_workflow_required: boolean }; lifecycle: Record<string, boolean> } };
export type GenericEvidenceVerification = { id: string; decision_id: string; fingerprint: string; verifier_version: string; status: "PASSED" | "FAILED"; owner_acceptance_readiness: string; evidence_outcome: string; owner_boundary: { acknowledgement_required: boolean; acknowledgement_present: boolean; acknowledgement_is_not_validation: boolean; future_promotion_contract_required: boolean }; checks: Record<string, { status: string; observed?: unknown; expected?: unknown }>; warning: string; reused?: boolean };
type GenericChain = { strategyVersionId: string; oos?: GenericOosEvidence; stability?: GenericStabilityEvidence; decision?: GenericDecision; verifier?: GenericEvidenceVerification };
type LifecycleArtifact = { id: string; fingerprint: string; status: string; reason?: string; result: Record<string, unknown> };
export type LifecycleVerification = { id: string; strategy_version_id: string; fingerprint: string; verifier_version: string; status: "PASSED" | "FAILED"; owner_acceptance_readiness: string; lifecycle_status: string; lifecycle_claim: string; checks: Record<string, { status: string; observed?: unknown; expected?: unknown }>; artifacts: { eligibility: LifecycleArtifact | null; promotion: LifecycleArtifact | null; retirement: LifecycleArtifact | null }; safety_boundary: { historical_only: boolean; demo_or_live_authorized: boolean; capital_authorized: boolean; router_or_trade_decision_created: boolean; deployment_created: boolean; profitability_proven: boolean }; warning: string; reused?: boolean };

const defaultDraft = { name: "Legacy Compatibility Candidate", source: "MANUAL", note: "Created in Strategy Factory UI" };
const defaultTerms = { stop: 0.1, target: 0.1, spread: 0.02, commission: 0 };

// ARK-S27-02/03. Direction and execution timeframe are the Owner's to choose on
// a generic contract. The legacy expression keeps neither: its envelope is
// XAUUSD LONG M1 by definition, so the controls are disabled rather than
// silently ignored.
export const EXPRESSIONS = ["LEGACY", "M1_M5_COMPLETED", "EMA_MINIMUM_RANGE"] as const;
export type Expression = (typeof EXPRESSIONS)[number];
export const EXECUTION_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"] as const;
export type Direction = "LONG" | "SHORT";

export function supportsChoices(expression: Expression) { return expression !== "LEGACY"; }

function contractFor(terms: typeof defaultTerms, expression: Expression, direction: Direction = "LONG", execution: string = "M1"): Contract & Record<string, unknown> {
  const completed = { block_id: "ALWAYS", uses_completed_candles: true };
  const polarity = direction === "LONG" ? "BULLISH" : "BEARISH";
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
    contract.direction_eligibility = direction; contract.execution_timeframe = execution;
    contract.context_timeframes = Array.from(new Set([execution, "M5"])).sort(); contract.setup_timeframes = [execution];
    contract.context_rules = [{ block_id: "SMA_RELATION", uses_completed_candles: true, timeframe: "M5", fast_period: 2, slow_period: 5, relation: "ABOVE" }];
    contract.setup_rules = [{ block_id: "TWO_BAR_REVERSAL", uses_completed_candles: true, timeframe: execution, direction: polarity }];
    contract.trigger_rules = [{ block_id: "ALL_OF", uses_completed_candles: true, children: [{ block_id: "CANDLE_DIRECTION", uses_completed_candles: true, timeframe: execution, direction: polarity }, { block_id: "NOT", uses_completed_candles: true, child: { block_id: "CANDLE_DIRECTION", uses_completed_candles: true, timeframe: execution, direction: polarity === "BULLISH" ? "BEARISH" : "BULLISH" } }] }];
  }
  if (expression === "EMA_MINIMUM_RANGE") {
    // The Owner's own example, written down for the first time.
    contract.direction_eligibility = direction; contract.execution_timeframe = execution;
    contract.context_timeframes = [execution]; contract.setup_timeframes = [execution];
    contract.context_rules = [
      { block_id: "PRICE_VS_MA", uses_completed_candles: true, timeframe: execution, method: "EMA", period: 31, relation: direction === "LONG" ? "ABOVE" : "BELOW" },
      { block_id: "MINIMUM_RANGE", uses_completed_candles: true, timeframe: execution, lookback: 12, minimum_distance: 5 },
    ];
    contract.setup_rules = [completed];
    contract.trigger_rules = [{ block_id: "CANDLE_DIRECTION", uses_completed_candles: true, timeframe: execution, direction: polarity }];
  }
  return contract;
}

function ruleName(item: Strategy) { return item.strategy_contract ? "Legacy bullish reversal compatibility contract" : item.configuration.entry?.rule_set ?? "Legacy recorded strategy"; }
function isGenericStrategy(item: Strategy) { return item.configuration.strategy_capability_assessment?.evaluator_capability_id === "GENERIC_COMPLETED_CANDLE_V1"; }
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

export function GenericEvidenceChain({ chain, onVerify, busy = false }: { chain: GenericChain; onVerify?: () => void; busy?: boolean }) {
  const { oos, stability, decision, verifier } = chain;
  const outcome = decision?.decision ?? stability?.status ?? oos?.result.gate_evaluation.decision ?? "INCOMPLETE";
  return <section className="panel result-panel factory-evidence" aria-label="Generic historical evidence chain"><div className="panel-header"><div><p className="discovery-kicker">GENERIC HISTORICAL EVIDENCE CHAIN</p><h2>{outcome}</h2><p>{decision ? `Decision ${decision.id.slice(0, 8)} · ${decision.fingerprint.slice(0, 16)}` : "Complete split, stability, and decision evidence before verification."}</p></div><span className="mode-badge">NOT VALIDATED</span></div>
    <section className="command-metrics"><article><small>Split evidence</small><strong>{oos?.result.gate_evaluation.decision ?? "MISSING"}</strong></article><article><small>Parameter stability</small><strong>{stability?.status ?? "MISSING"}</strong></article><article><small>Combined decision</small><strong>{decision?.decision ?? "MISSING"}</strong></article><article><small>Chain verifier</small><strong>{verifier?.status ?? "NOT MATERIALIZED"}</strong></article></section>
    {oos && <div><h3>Declared OOS policy and checks</h3><div className="strategy-list">{Object.entries(oos.result.gate_evaluation.checks).map(([key, check]) => <article className="strategy-card" key={key}><div><strong>{checkLabels[key] ?? key}</strong><p className="muted">Observed: {JSON.stringify(check.observed ?? check.maximum_observed ?? "see evidence")}</p></div><span className="mode-badge">{check.status}</span></article>)}</div><details className="discovery-advanced"><summary>Frozen split policy</summary><pre>{JSON.stringify(oos.protocol, null, 2)}</pre></details></div>}
    {stability && <div><h3>Bounded parameter stability</h3><p>{stability.result.stability.passing_candidate_count}/{stability.result.stability.candidate_count} candidates pass; required fraction {stability.result.stability.minimum_passing_candidate_fraction}. Final OOS access remains prohibited during this step.</p><details className="discovery-advanced"><summary>Stability policy and split access</summary><pre>{JSON.stringify({ policy: stability.policy, split_access: stability.result.split_access }, null, 2)}</pre></details></div>}
    {decision && <div><h3>Explicit Owner decision boundary</h3><p><strong>Outcome {decision.decision} is evidence only and is NOT VALIDATED.</strong> Owner acknowledgement is required, but acknowledgement itself cannot promote the strategy. Eligibility and a separate explicit promotion authorization are required.</p><details className="discovery-advanced"><summary>Combined thresholds, observations, and lineage</summary><pre>{JSON.stringify(decision.result, null, 2)}</pre></details></div>}
    {decision && !verifier && onVerify && <button className="secondary" disabled={busy} onClick={onVerify}>Materialize generic evidence verifier</button>}
    {verifier && <div><h3>Materialized acceptance verifier · {verifier.status}</h3><p>{verifier.owner_acceptance_readiness} · {verifier.fingerprint.slice(0, 16)}{verifier.reused ? " · reused" : ""}</p><div className="strategy-list">{Object.entries(verifier.checks).map(([key, check]) => <article className="strategy-card" key={key}><strong>{key.replaceAll("_", " ")}</strong><span className="mode-badge">{check.status}</span></article>)}</div><p className="warning-line">{verifier.warning}</p></div>}
    <p className="warning-line"><strong>No VALIDATED claim. No DEMO/LIVE deployment, capital authority, router decision, order, or trade recommendation.</strong></p>
  </section>;
}

export function LifecycleGovernance({ verification, onPromote, onRetire, retirementReason, onRetirementReasonChange, busy = false }: { verification: LifecycleVerification; onPromote?: () => void; onRetire?: () => void; retirementReason?: string; onRetirementReasonChange?: (value: string) => void; busy?: boolean }) {
  const { eligibility, promotion, retirement } = verification.artifacts;
  return <section className="panel result-panel factory-evidence" aria-label="Generic validation lifecycle governance"><div className="panel-header"><div><p className="discovery-kicker">GENERIC VALIDATION LIFECYCLE · {verification.verifier_version}</p><h2>{verification.lifecycle_status}</h2><p>{verification.lifecycle_claim} · fingerprint {verification.fingerprint.slice(0, 16)}{verification.reused ? " · reused" : ""}</p></div><span className={`validation-status ${verification.status === "PASSED" ? "passed" : "failed"}`}>{verification.status}</span></div>
    <section className="command-metrics"><article><small>Eligibility</small><strong>{eligibility?.status ?? "MISSING"}</strong></article><article><small>Promotion</small><strong>{promotion?.status ?? "NONE"}</strong></article><article><small>Retirement</small><strong>{retirement?.status ?? "NONE"}</strong></article><article><small>Claim</small><strong>{verification.lifecycle_claim}</strong></article></section>
    <div className="strategy-list">{Object.entries(verification.checks).map(([key, check]) => <article className="strategy-card" key={key}><div><strong>{key.replaceAll("_", " ")}</strong><p className="muted">{check.status === "PASS" ? "Exact stored lineage verified" : "Blocking mismatch; inspect immutable evidence"}</p></div><span className="mode-badge">{check.status}</span></article>)}</div>
    {eligibility && <details className="discovery-advanced"><summary>Eligibility evidence · {eligibility.status}</summary><pre>{JSON.stringify(eligibility, null, 2)}</pre></details>}
    {promotion && <details className="discovery-advanced"><summary>Promotion lineage · HISTORICAL ONLY</summary><pre>{JSON.stringify(promotion, null, 2)}</pre></details>}
    {retirement && <details className="discovery-advanced"><summary>Immutable retirement · {retirement.reason}</summary><pre>{JSON.stringify(retirement, null, 2)}</pre></details>}
    {verification.lifecycle_status === "CONTRACT_VALID" && eligibility?.status === "ELIGIBLE" && !promotion && onPromote && <button className="run-button" disabled={busy || verification.status !== "PASSED"} onClick={onPromote}>Explicitly authorize historical validation</button>}
    {verification.lifecycle_status === "VALIDATED" && promotion && !retirement && onRetire && <div className="backtest-form"><label>Required retirement reason<input aria-label="Required retirement reason" value={retirementReason ?? ""} onChange={event => onRetirementReasonChange?.(event.target.value)} /></label><button className="secondary" disabled={busy || (retirementReason?.trim().length ?? 0) < 10} onClick={onRetire}>Explicitly retire this immutable version</button></div>}
    <p className="warning-line"><strong>Safety boundary:</strong> historical-only; profitability is not proven. DEMO/LIVE, capital, Router, deployment, order, and trade authority are all false.</p><p className="warning-line">{verification.warning}</p>
  </section>;
}

export function StrategyLibrary() {
  const [items, setItems] = useState<Strategy[]>([]); const [candidates, setCandidates] = useState<Candidate[]>([]); const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState(defaultDraft); const [terms, setTerms] = useState(defaultTerms); const [validation, setValidation] = useState<Validation | null>(null); const [run, setRun] = useState<Backtest | null>(null); const [oos, setOos] = useState<OosEvidence | null>(null); const [genericChain, setGenericChain] = useState<GenericChain | null>(null);
  const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false); const [registry, setRegistry] = useState<CapabilityRegistry | null>(null); const [verification, setVerification] = useState<EvaluatorVerification | null>(null); const [lifecycle, setLifecycle] = useState<LifecycleVerification | null>(null); const [retirementReason, setRetirementReason] = useState(""); const [expression, setExpression] = useState<Expression>("LEGACY"); const [direction, setDirection] = useState<Direction>("LONG"); const [execution, setExecution] = useState<string>("M1");
  const contract = useMemo(() => contractFor(terms, expression, direction, execution), [terms, expression, direction, execution]);
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
  const read = async <T,>(url: string): Promise<T> => { const response = await fetch(url, { cache: "no-store" }); const value = await response.json(); if (!response.ok) throw Error(errorOf(value)); return value as T; };
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
      if (evidence.protocol.version === "GENERIC_OOS_EVIDENCE_V1") {
        setOos(null); setGenericChain({ strategyVersionId: version.id, oos: evidence as GenericOosEvidence });
        setMessage(`Generic split evidence: ${evidence.result.gate_evaluation.decision}. Evidence ini tidak membuat VALIDATED.`);
      } else {
        setGenericChain(null); setOos(evidence); setMessage(evidence.result.gate_evaluation.decision === "PASS" ? "Legacy historical robustness gate PASS. StrategyVersion berstatus VALIDATED, tetapi tetap bukan DEMO/LIVE-ready." : `Historical robustness decision: ${evidence.result.gate_evaluation.decision}. Tidak ada promosi.`);
      }
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "OOS robustness gate gagal."); } finally { setBusy(false); }
  }
  async function runGenericStability(version: Strategy) {
    setBusy(true); setMessage(""); try {
      let split = genericChain?.strategyVersionId === version.id ? genericChain.oos : undefined;
      if (!split) { const body = await read<OosEvidenceList>(`/api/v1/strategy-versions/${version.id}/oos-validations`); split = body.validations.find((item): item is GenericOosEvidence => !!item && typeof item === "object" && (item as GenericOosEvidence).protocol?.version === "GENERIC_OOS_EVIDENCE_V1"); }
      if (!split) throw Error("Jalankan generic split evidence terlebih dahulu.");
      const stability = await request(`/api/v1/strategy-versions/${version.id}/generic-robustness`, { baseline_oos_validation_id: split.id }) as GenericStabilityEvidence;
      setOos(null); setGenericChain({ strategyVersionId: version.id, oos: split, stability }); setMessage(`Parameter stability: ${stability.status}. Final OOS tidak diakses dan tidak ada promosi.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Parameter stability gagal."); } finally { setBusy(false); }
  }
  async function materializeGenericDecision(version: Strategy) {
    setBusy(true); setMessage(""); try {
      let stability = genericChain?.strategyVersionId === version.id ? genericChain.stability : undefined;
      if (!stability) { const body = await read<{ evidence: GenericStabilityEvidence[] }>(`/api/v1/strategy-versions/${version.id}/generic-robustness`); stability = body.evidence[0]; }
      if (!stability) throw Error("Jalankan parameter stability terlebih dahulu.");
      const decision = await request(`/api/v1/strategy-versions/${version.id}/generic-evidence-decisions`, { robustness_evidence_id: stability.id }) as GenericDecision;
      const body = await read<OosEvidenceList>(`/api/v1/strategy-versions/${version.id}/oos-validations`); const split = body.validations.find((item): item is GenericOosEvidence => !!item && typeof item === "object" && (item as GenericOosEvidence).id === decision.oos_validation_id);
      setOos(null); setGenericChain({ strategyVersionId: version.id, oos: split, stability, decision }); setMessage(`Combined decision: ${decision.decision}. Status tetap NOT VALIDATED sampai eligibility dan explicit promotion authorization lulus.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Generic decision gagal."); } finally { setBusy(false); }
  }
  async function viewGenericEvidence(version: Strategy) {
    setBusy(true); setMessage(""); try {
      const [splits, stabilities, decisions] = await Promise.all([
        read<OosEvidenceList>(`/api/v1/strategy-versions/${version.id}/oos-validations`),
        read<{ evidence: GenericStabilityEvidence[] }>(`/api/v1/strategy-versions/${version.id}/generic-robustness`),
        read<{ decisions: GenericDecision[] }>(`/api/v1/strategy-versions/${version.id}/generic-evidence-decisions`),
      ]);
      const decision = decisions.decisions[0]; const stability = decision ? stabilities.evidence.find(item => item.id === decision.robustness_evidence_id) : stabilities.evidence[0];
      const splitId = decision?.oos_validation_id; const split = splits.validations.find((item): item is GenericOosEvidence => !!item && typeof item === "object" && (item as GenericOosEvidence).protocol?.version === "GENERIC_OOS_EVIDENCE_V1" && (!splitId || (item as GenericOosEvidence).id === splitId));
      let verifier: GenericEvidenceVerification | undefined;
      if (decision) { try { verifier = await read<GenericEvidenceVerification>(`/api/v1/generic-evidence-decisions/${decision.id}/verification`); } catch { verifier = undefined; } }
      setOos(null); setGenericChain({ strategyVersionId: version.id, oos: split, stability, decision, verifier }); setMessage(decision ? `Generic evidence chain dibuka: ${decision.decision}; tetap NOT VALIDATED.` : "Generic evidence chain belum lengkap.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Generic evidence chain tidak dapat dibuka."); } finally { setBusy(false); }
  }
  async function verifyGenericEvidence() {
    if (!genericChain?.decision) return; setBusy(true); setMessage(""); try {
      const verifier = await request(`/api/v1/generic-evidence-decisions/${genericChain.decision.id}/verification`) as GenericEvidenceVerification;
      setGenericChain(current => current ? { ...current, verifier } : current); setMessage(`Generic verifier ${verifier.status}; ini memverifikasi integritas evidence, bukan VALIDATED atau izin trading.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Generic verifier gagal."); } finally { setBusy(false); }
  }
  async function materializeLifecycle(version: Strategy) {
    setBusy(true); setMessage(""); try {
      const value = await request(`/api/v1/strategy-versions/${version.id}/lifecycle-verification`) as LifecycleVerification;
      setLifecycle(value); setRetirementReason(""); setMessage(`Lifecycle verifier ${value.status}: ${value.lifecycle_claim}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Lifecycle verifier gagal."); } finally { setBusy(false); }
  }
  async function promoteLifecycle() {
    const eligibility = lifecycle?.artifacts.eligibility; if (!lifecycle || !eligibility) return; setBusy(true); setMessage(""); try {
      await request(`/api/v1/generic-validation-eligibilities/${eligibility.id}/promotion`, { authorization: "AUTHORIZE_GENERIC_HISTORICAL_VALIDATION_V1" });
      const value = await request(`/api/v1/strategy-versions/${lifecycle.strategy_version_id}/lifecycle-verification`) as LifecycleVerification;
      setLifecycle(value); await load(); setMessage("Owner authorization recorded: VALIDATED means historical validation only.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Promotion gagal."); } finally { setBusy(false); }
  }
  async function retireLifecycle() {
    if (!lifecycle) return; setBusy(true); setMessage(""); try {
      await request(`/api/v1/strategy-versions/${lifecycle.strategy_version_id}/retirement`, { authorization: "AUTHORIZE_GENERIC_STRATEGY_RETIREMENT_V1", reason: retirementReason });
      const value = await request(`/api/v1/strategy-versions/${lifecycle.strategy_version_id}/lifecycle-verification`) as LifecycleVerification;
      setLifecycle(value); setRetirementReason(""); await load(); setMessage("StrategyVersion retired immutably; reactivation is unavailable.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Retirement gagal."); } finally { setBusy(false); }
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
      <section className="panel backtest-config factory-panel"><p className="discovery-kicker">2 · CONTRACT</p><h2>Registered V1 expression</h2><label className="deploy-label">Completed-candle block picker<select value={expression} onChange={event => { setExpression(event.target.value as Expression); setValidation(null); }}><option value="LEGACY">Legacy bullish reversal · M1</option><option value="M1_M5_COMPLETED">SMA M5 + bullish reversal</option><option value="EMA_MINIMUM_RANGE">Harga vs EMA 31 + range minimal</option></select></label>
        <label className="deploy-label">Arah<select value={direction} disabled={!supportsChoices(expression)} onChange={event => { setDirection(event.target.value as Direction); setValidation(null); }}><option value="LONG">LONG (beli)</option><option value="SHORT">SHORT (jual)</option></select></label>
        <label className="deploy-label">Timeframe eksekusi<select value={execution} disabled={!supportsChoices(expression)} onChange={event => { setExecution(event.target.value); setValidation(null); }}>{EXECUTION_TIMEFRAMES.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
        <p className="muted">{supportsChoices(expression) ? "Arah dan timeframe bisa dipilih. Simbol tetap XAUUSD, entry di open candle berikutnya, satu posisi, STOP_FIRST." : "Ekspresi legacy terkunci di XAUUSD LONG M1 — itu memang batas kemampuannya, jadi kedua pilihan di atas dimatikan."}</p><div className="backtest-form">{([ ["stop", "Stop distance"], ["target", "Target distance"], ["spread", "Spread guard"], ["commission", "Commission price"] ] as Array<[keyof typeof defaultTerms, string]>).map(([key, label]) => <label key={key}>{label}<input aria-label={label} type="number" min="0" step="0.01" value={terms[key]} onChange={event => updateTerm(key, event.target.valueAsNumber)} /></label>)}</div><div className="actions"><button className="secondary" disabled={busy} onClick={validateContract}>Validate contract</button><button className="run-button" disabled={busy || !selected || validation?.ready !== true} onClick={confirmVersion}>Confirm immutable version</button></div>{validation && <div className={validation.ready ? "factory-state ready" : "factory-state invalid"}><strong>{validation.ready ? "CONTRACT VALID" : "CONTRACT NEEDS FIXES"}</strong><span>{validation.ready ? `Fingerprint ${validation.fingerprint?.slice(0, 16)}` : (validation.issues?.join(" ") || validation.status || "Kontrak ditolak.")}</span></div>}</section>
      <section className="panel backtest-info factory-panel"><p className="discovery-kicker">WHAT THIS DOES NOT DO</p><h2>Safety boundary</h2><p>Confirmation alone does not mark a version <strong>VALIDATED</strong>, deploy it, configure MT5, or create an order.</p><p>Backtest V1 remains the single canonical kernel. Eligibility and acknowledgement cannot promote by themselves; promotion requires its own explicit Owner authorization.</p><p><strong>VALIDATED always means historical validation only.</strong> It never means profitable, DEMO-ready, LIVE-ready, capital-authorized, routed, or recommended. RETIRED is immutable and revisions create new versions.</p></section></section>
    {run && <section className="panel result-panel factory-evidence"><div className="panel-header"><div><p className="discovery-kicker">CANONICAL BACKTEST EVIDENCE</p><h2>{run.reused ? "Recorded evidence reused" : "New evidence recorded"}</h2><p>Run {run.id.slice(0, 8)} · fingerprint {run.fingerprint.slice(0, 16)}</p></div><span className="mode-badge">HISTORICAL ONLY</span></div><section className="command-metrics"><article><small>Trades</small><strong>{run.result.metrics.trade_count}</strong></article><article><small>Net price PnL</small><strong>{run.result.metrics.net_pnl_price}</strong></article><article><small>Entry timing</small><strong>{run.result.strategy_lineage?.execution_semantics.entry_timing ?? "Legacy"}</strong></article><article><small>Ambiguity</small><strong>{run.result.strategy_lineage?.execution_semantics.ambiguity_policy ?? "Legacy"}</strong></article></section>{run.strategy_version_id && <button className="secondary" disabled={busy} onClick={verifyEvaluatorEvidence}>Materialize evaluator acceptance verifier</button>}{verification && <p className="warning-line">Verifier: {verification.owner_acceptance_readiness} · {verification.fingerprint.slice(0, 16)} · {Object.values(verification.checks).every(check => check.status === "PASS") ? "all checks PASS" : "blocking check present"}</p>}<p className="warning-line">{run.result.warning}</p><details className="discovery-advanced"><summary>Lineage evidence</summary><pre>{JSON.stringify(run.result.strategy_lineage, null, 2)}</pre></details></section>}
    {oos && <RobustnessEvidence evidence={oos} />}
    {genericChain && <GenericEvidenceChain chain={genericChain} busy={busy} onVerify={verifyGenericEvidence} />}
    {lifecycle && <LifecycleGovernance verification={lifecycle} busy={busy} onPromote={promoteLifecycle} onRetire={retireLifecycle} retirementReason={retirementReason} onRetirementReasonChange={setRetirementReason} />}
    <section className="panel result-panel"><div className="panel-header"><div><h2>Version registry</h2><p>Contract versions expose exact eligibility, promotion, retirement, and verifier lineage. Historical evidence never authorizes execution.</p></div></div>{items.length ? <div className="strategy-list">{items.map(item => <article className={`strategy-card${isFixture(item.lineage) ? " is-fixture" : ""}`} key={item.id}><div><small>{item.status} · {item.profile} · v{item.version}.0.0</small><h2>{item.name}<FixtureBadge lineage={item.lineage} /></h2><p>{ruleName(item)}</p>{isFixture(item.lineage) && <p className="muted">Rekaman ini dibuat untuk menguji kode, bukan dari data pasar nyata. Statusnya tidak boleh dibaca sebagai bukti. Alasan: {item.lineage?.reasons.join("; ")}</p>}<p className="muted">Checksum {item.checksum.slice(0, 12)} · {item.generic_validation_retirement_id ? `Retirement ${item.generic_validation_retirement_id.slice(0, 8)}` : item.generic_validation_promotion_id ? `Historical promotion ${item.generic_validation_promotion_id.slice(0, 8)}` : item.validation_evidence_id ? `Historical evidence ${item.validation_evidence_id.slice(0, 8)}` : item.backtest_run_id ? `Legacy backtest ${item.backtest_run_id.slice(0, 8)}` : item.strategy_contract ? "Contract version; evidence not yet selected" : "No backtest reference"}</p></div><div className="actions">{item.strategy_contract && <><button className="run-button" disabled={busy || item.status === "RETIRED"} onClick={() => backtest(item)}>Run canonical backtest</button>{isGenericStrategy(item) ? <><button className="run-button" disabled={busy || item.status !== "CONTRACT_VALID"} onClick={() => validateOos(item)}>1 · Run split evidence</button><button className="run-button" disabled={busy || item.status !== "CONTRACT_VALID"} onClick={() => runGenericStability(item)}>2 · Run parameter stability</button><button className="run-button" disabled={busy || item.status !== "CONTRACT_VALID"} onClick={() => materializeGenericDecision(item)}>3 · Materialize decision</button><button className="secondary" disabled={busy} onClick={() => viewGenericEvidence(item)}>View complete generic chain</button><button className="secondary" disabled={busy} onClick={() => materializeLifecycle(item)}>Verify lifecycle governance</button></> : <><button className="run-button" disabled={busy} onClick={() => validateOos(item)}>Run OOS robustness gate</button><button className="secondary" disabled={busy} onClick={() => viewLatestOos(item)}>View latest OOS evidence</button></>}<button className="secondary" disabled={busy} onClick={() => revise(item)}>Create revision draft</button></>}{item.status === "CANDIDATE" && <button className="run-button" disabled={busy} onClick={() => approve(item.id)}>Approve legacy manually</button>}{item.status === "APPROVED" && <span className="mode-badge">APPROVED · NOT DEPLOYED</span>}{item.status === "CONTRACT_VALID" && <span className="mode-badge">CONTRACT VALID · NOT VALIDATED</span>}{item.status === "VALIDATED" && <span className="mode-badge">VALIDATED · HISTORICAL ONLY</span>}{item.status === "RETIRED" && <span className="mode-badge">RETIRED · IMMUTABLE</span>}</div></article>)}</div> : <p className="muted empty-library">No strategy version yet. Create a draft, validate its contract, then confirm an immutable version.</p>}</section>
  </section></main>;
}

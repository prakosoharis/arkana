"use client";
import React, { useEffect, useState } from "react";

type Metrics = { trade_count: number; net_pnl_price: number; profit_factor: number | string | null; win_rate: number | null };
type Trial = { trial_id: string; trial_index: number; parameters: Record<string, string | number>; status: string; result: { splits?: Record<string, { metrics: Metrics }> } | null };
// The concentration checks report `maximum_observed`, not `observed`. Reading
// only `observed` silently hides the two numbers that refused the strategy.
type GateCheck = { status: string; observed?: unknown; maximum_observed?: unknown; maximum_allowed?: unknown };
type Outcome = { outcome_id: string; trial_index: number; gate_decision: string; parameters: Record<string, string | number>; gate_checks: Record<string, GateCheck>; splits: Record<string, Metrics>; budget: { sequence: number; budget: number; remaining_after: number }; strategy_version_id: string; strategy_status: string; oos_fingerprint: string };
type Disclosure = { trials_pre_registered: number; trials_recorded: number; final_oos_budget: number; final_oos_consumed: number; final_oos_remaining: number; multiple_testing_note: string; spread_assumption: string };
type Entry = {
  campaign: { campaign_id: string; fingerprint: string; status: string; trial_count: number; spread_assumption: string; grid: { dimensions: Record<string, Array<string | number>> } };
  progress: { recorded: number; pre_registered: number; complete: boolean; by_status: Record<string, number>; survivor_count: number; mean_seconds_per_trial: number | null };
  survivors: { survivor_count: number; ranked: Array<Trial & { rank: number }>; selection_disclosure: Disclosure };
  final_oos_outcomes: Outcome[];
  conclusion: { conclusion: string; fingerprint: string } | null;
  assessment: { conclusion: string; budget: { consumed: number; budget: number; remaining: number } };
  verification: { status: string; fingerprint: string; checks: Record<string, GateCheck> } | null;
};
type Overview = { campaigns: Entry[]; count: number; warning: string };

const pretty = (value: string) => value.replaceAll("_", " ");
const num = (value: number | string | null | undefined, digits = 4) =>
  typeof value === "number" ? value.toFixed(digits) : value === null || value === undefined ? "—" : String(value);

export function verdictLabel(conclusion: string) {
  // NO_EDGE_FOUND is a complete result, never a platform failure.
  if (conclusion === "NO_EDGE_FOUND") return "TIDAK ADA EDGE DITEMUKAN — HASIL LENGKAP, BUKAN KEGAGALAN";
  if (conclusion === "EDGE_CANDIDATE_FOUND") return "KANDIDAT EDGE — BUKTI HISTORIS SAJA";
  return pretty(conclusion);
}

function Chip({ value, pass }: { value: string; pass?: boolean }) {
  return <span className={`validation-status ${pass ? "passed" : "failed"}`}>{value}</span>;
}

export function gateObservation(check: GateCheck): string | null {
  const value = check.observed ?? check.maximum_observed;
  if (value === undefined || value === null) return null;
  const limit = check.maximum_allowed;
  const shown = JSON.stringify(value).slice(0, 120);
  return limit === undefined ? shown : `${shown} (max ${JSON.stringify(limit)})`;
}

function GateChecks({ checks }: { checks: Record<string, GateCheck> }) {
  return <div className="capital-checks">{Object.entries(checks).map(([name, check]) => {
    const observation = gateObservation(check);
    return <article key={name}><Chip value={check.status} pass={check.status === "PASS"} /><div><strong>{pretty(name)}</strong>
      {observation && <small>{observation}</small>}</div></article>;
  })}</div>;
}

function SplitTable({ splits }: { splits: Record<string, Metrics> }) {
  return <div className="trade-table"><table><thead><tr><th>Split</th><th>Trades</th><th>Net PnL</th><th>Profit factor</th><th>Win rate</th></tr></thead>
    <tbody>{["train", "holdout", "final_oos"].filter(name => splits[name]).map(name => {
      const m = splits[name];
      return <tr key={name}><td>{pretty(name)}</td><td>{m.trade_count}</td><td>{num(m.net_pnl_price, 2)}</td>
        <td><strong>{num(m.profit_factor)}</strong></td><td>{m.win_rate ? (m.win_rate * 100).toFixed(2) + "%" : "—"}</td></tr>;
    })}</tbody></table></div>;
}

export function EdgeSearchConsoleView({ data, onRefresh, onVerify, busy }: { data: Overview; onRefresh: () => void; onVerify: (id: string) => void; busy: boolean }) {
  return <main className="backtest-page">
    <header><div><p className="discovery-kicker">ARK-S22 · BOUNDED EDGE SEARCH</p><h1>Edge Search</h1>
      <p>A pre-registered grid, executed in full. A high holdout rank is not an edge.</p></div>
      <Chip value="NO VALIDATED STRATEGY CREATED" /></header>
    <section className="backtest-content">
      <section className="panel generic-safety"><div><p className="discovery-kicker">PERMANENT SAFETY BOUNDARY</p>
        <h2>Searching creates no authority</h2><p>{data.warning}</p></div>
        <div className="actions"><button className="secondary" onClick={onRefresh} disabled={busy}>Refresh evidence</button></div></section>

      {!data.campaigns.length && <p className="empty-library">No campaign has been pre-registered.</p>}

      {data.campaigns.map(entry => {
        const disclosure = entry.survivors.selection_disclosure;
        const verdict = entry.assessment.conclusion;
        return <section key={entry.campaign.campaign_id} className="panel generic-section">
          <div className="panel-header"><div><h2>{verdictLabel(verdict)}</h2>
            <p>Campaign {entry.campaign.campaign_id.slice(0, 8)} · fingerprint {entry.campaign.fingerprint.slice(0, 16)}
              {entry.conclusion && ` · verdict ${entry.conclusion.fingerprint.slice(0, 16)}`}</p></div>
            {entry.verification
              ? <Chip value={`VERIFIER ${entry.verification.status}`} pass={entry.verification.status === "PASSED"} />
              : <button className="secondary" disabled={busy} onClick={() => onVerify(entry.campaign.campaign_id)}>Materialize chain verifier</button>}
          </div>

          <section className="command-metrics">
            <article><small>Trials executed</small><strong>{entry.progress.recorded} / {entry.progress.pre_registered}</strong></article>
            <article><small>Holdout survivors</small><strong>{entry.progress.survivor_count}</strong></article>
            <article><small>Final-OOS budget spent</small><strong>{entry.assessment.budget.consumed} / {entry.assessment.budget.budget}</strong></article>
            <article><small>Assumed spread</small><strong>{entry.campaign.spread_assumption}</strong></article>
          </section>

          <p className="warning-line"><strong>Selection disclosure.</strong> {disclosure.multiple_testing_note}</p>

          {entry.final_oos_outcomes.map(outcome => <div key={outcome.outcome_id}>
            <h3>Final-OOS opening {outcome.budget.sequence} of {outcome.budget.budget} · gate {outcome.gate_decision}</h3>
            <p className="muted">Trial {outcome.trial_index} · {Object.entries(outcome.parameters).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>
            <p className="muted">StrategyVersion {outcome.strategy_version_id.slice(0, 8)} is <strong>{outcome.strategy_status}</strong>; the generic path never promotes automatically.</p>
            <SplitTable splits={outcome.splits} />
            <GateChecks checks={outcome.gate_checks} />
          </div>)}

          {entry.survivors.ranked.length > 0 && <details className="discovery-advanced">
            <summary>Top holdout survivors ({entry.survivors.survivor_count} total) — ranking selects nothing</summary>
            <div className="trade-table"><table><thead><tr><th>Rank</th><th>Trial</th><th>Parameters</th><th>Trades</th><th>Holdout PF</th></tr></thead>
              <tbody>{entry.survivors.ranked.map(item => {
                const m = item.result?.splits?.holdout?.metrics;
                return <tr key={item.trial_id}><td>{item.rank}</td><td>{item.trial_index}</td>
                  <td>{Object.entries(item.parameters).map(([k, v]) => `${k}=${v}`).join(" · ")}</td>
                  <td>{m?.trade_count ?? "—"}</td><td><strong>{num(m?.profit_factor)}</strong></td></tr>;
              })}</tbody></table></div></details>}

          {entry.verification && <details className="discovery-advanced">
            <summary>Chain verifier checks · {entry.verification.fingerprint.slice(0, 16)}</summary>
            <GateChecks checks={entry.verification.checks} /></details>}

          <details className="discovery-advanced"><summary>Pre-registered grid</summary>
            <pre>{JSON.stringify(entry.campaign.grid.dimensions, null, 2)}</pre></details>
        </section>;
      })}
    </section>
  </main>;
}

export function EdgeSearchConsole() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      const response = await fetch("/api/v1/edge-search/owner-overview", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Edge-search overview unavailable");
      setData(body); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Edge-search overview unavailable"); }
  }
  async function verify(id: string) {
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/edge-search/campaigns/${id}/chain-verification`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail ?? "Verifier failed");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Verifier failed"); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);
  if (!data) return <main className="backtest-page"><header><h1>Edge Search</h1></header>
    <section className="backtest-content"><p className={error ? "error" : "state"}>{error || "Loading immutable campaign evidence…"}</p>
      {error && <button className="secondary" onClick={() => void load()}>Retry</button>}</section></main>;
  return <><EdgeSearchConsoleView data={data} onRefresh={() => void load()} onVerify={id => void verify(id)} busy={busy} />
    {error && <p className="error">{error}</p>}</>;
}

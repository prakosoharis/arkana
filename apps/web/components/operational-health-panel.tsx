"use client";
import React, { useEffect, useState } from "react";

type Condition = { code: string; severity: "CRITICAL" | "WARNING"; detail: string; evidence: Record<string, unknown> };
type Check = { status: string; evidence?: Record<string, unknown> };
type Health = { status: "OK" | "WARNING" | "CRITICAL"; evaluated_at: string; conditions: Condition[]; checks: Record<string, Check>; warning: string };

const pretty = (value: string) => value.replaceAll("_", " ");

export function healthLabel(status: string) {
  // An alert that cannot be distinguished from a routine state gets ignored.
  if (status === "CRITICAL") return "PERLU TINDAKAN";
  if (status === "WARNING") return "PERLU DIPERHATIKAN";
  return "SEHAT";
}

export function OperationalHealthPanelView({ health }: { health: Health }) {
  return <section className="panel generic-section" aria-label="Operational health">
    <div className="panel-header">
      <div><p className="discovery-kicker">ARK-S23-04 · OPERATIONAL HEALTH</p>
        <h2>{healthLabel(health.status)}</h2>
        <p>Evaluated {health.evaluated_at}. {health.warning}</p></div>
      <span className={`validation-status ${health.status === "OK" ? "passed" : "failed"}`}>{health.status}</span>
    </div>
    <section className="command-metrics">{Object.entries(health.checks).map(([name, check]) =>
      <article key={name}><small>{pretty(name)}</small><strong>{pretty(check.status)}</strong></article>)}</section>
    {health.conditions.length === 0
      ? <p className="empty-library">No operational condition is open.</p>
      : <div className="generic-records">{health.conditions.map(condition =>
          <article key={condition.code}>
            <strong>{condition.severity} · {pretty(condition.code)}</strong>
            <p>{condition.detail}</p>
            <details><summary>Exact evidence</summary><pre>{JSON.stringify(condition.evidence, null, 2)}</pre></details>
          </article>)}</div>}
  </section>;
}

export function OperationalHealthPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/v1/operational-health", { cache: "no-store" });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? "Operational health unavailable");
        if (!cancelled) { setHealth(body); setError(""); }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Operational health unavailable");
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
  if (error) return <section className="panel generic-section"><p className="error">{error}</p></section>;
  if (!health) return <section className="panel generic-section"><p className="state">Loading operational health…</p></section>;
  return <OperationalHealthPanelView health={health} />;
}

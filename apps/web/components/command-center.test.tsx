import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommandCenterView, Snapshot, Validation, commandCenterState } from "./command-center";

const validation: Validation = { status: "NEEDS_MORE_EVIDENCE", observation: { period_start: "NOT_REPORTED", period_end: "NOT_REPORTED", days: 0 }, performance: { completed_trades: 0 }, checks: [], trades: [] };
const base: Snapshot = { adapter: { status: "TELEMETRY_UNAVAILABLE", imported: 0, error: "telemetry.csv does not exist" }, heartbeat: null, latest_decision: null, active_deployment: null, availability: { tick_age: "NOT_REPORTED", decision_latency: "NOT_REPORTED", broker_rtt: "NOT_REPORTED", trade_outcome: "NOT_REPORTED" }, generated_at: "2026-08-16T00:00:00Z" };

function markup(snapshot: Snapshot | null, currentValidation: Validation | null = validation) {
  return renderToStaticMarkup(<CommandCenterView snapshot={snapshot} events={[]} validation={currentValidation} error="" onRefresh={() => undefined} />);
}

describe("CommandCenter", () => {
  const activeDeployment = { id: "deployment-1", strategy_version_id: "strategy-1", strategy_name: "Bullish Reversal M1", strategy_key: "bullish-reversal-m1", strategy_version: "v1", checksum: "abc123", broker_symbol: "XAUUSD.m", acknowledged_at: "2026-08-16T00:00:00Z" };
  const heartbeat = { id: "event-1", timestamp: "2026.08.16 00:00", observed_at: "2026-08-16T00:00:00Z", strategy_id: "bullish-reversal-m1", strategy_version: "v1", broker_symbol: "XAUUSD.m", environment: "DEMO", decision: "HEARTBEAT", detail: "active", positions: "1", emergency_stop: "true" };
  const activeSnapshot: Snapshot = { ...base, adapter: { status: "CONNECTED", imported: 0, error: null }, heartbeat, latest_decision: { ...heartbeat, id: "event-2", decision: "NO_TRADE" }, active_deployment: activeDeployment };
  it("explains no active deployment without an endless loading dashboard", () => {
    const page = markup(base);
    expect(commandCenterState(base, "")).toBe("NO_ACTIVE_DEPLOYMENT");
    expect(page).toContain("Tidak ada strategy DEMO yang sedang berjalan.");
    expect(page).toContain("Lihat Demo Deployment");
    expect(page).toContain("LIVE");
    expect(page).toContain("LOCKED");
    expect(page).not.toContain("Adapter");
    expect(page).not.toContain("Deploy to Live");
  });

  it("shows a deployed strategy as waiting when no heartbeat exists", () => {
    const snapshot: Snapshot = { ...base, active_deployment: { id: "deployment-1", strategy_version_id: "strategy-1", strategy_name: "Bullish Reversal M1", strategy_key: "bullish-reversal-m1", strategy_version: "v1", checksum: "abc123", broker_symbol: "XAUUSD.m", acknowledged_at: "2026-08-16T00:00:00Z" } };
    const page = markup(snapshot);
    expect(commandCenterState(snapshot, "")).toBe("DEPLOYMENT_WAITING_FOR_TELEMETRY");
    expect(page).toContain("belum menerima telemetry dari MT5");
    expect(page).toContain("Bullish Reversal M1");
    expect(page).toContain("Refresh Telemetry");
  });

  it("shows the helicopter view only when heartbeat telemetry is available", () => {
    const page = markup(activeSnapshot);
    expect(commandCenterState(activeSnapshot, "")).toBe("ACTIVE");
    expect(page).toContain("MT5 Connection");
    expect(page).toContain("NO_TRADE");
    expect(page).toContain("Open Positions");
    expect(page).toContain("Emergency Stop");
    expect(page).toContain("Belum ada valid trade yang selesai. Ini bukan kegagalan sistem.");
    expect(page).toContain("Tick age belum dilaporkan oleh MT5");
    expect(page).toContain("NOT_REPORTED");
    expect(page).not.toContain("Deploy to Live");
  });

  it("explains zero-trade readiness with owner-friendly progress before technical evidence", () => {
    const report: Validation = { ...validation, historical_comparison: { status: "FORWARD_EVIDENCE_TOO_SMALL", historical: { strategy_name: "Bullish Reversal M1", strategy_version: 1, backtest_run_id: "backtest-1", backtest_fingerprint: "fingerprint", dataset_fingerprint: "dataset", period: { start: "2025-01-01", end: "2026-01-01" }, metrics: { completed_trades: 100, win_rate: 0.5, net_result: 12, profit_factor: 1.2, max_drawdown: -3 } }, forward: { trade_count: 0, win_rate: "NOT_REPORTED" }, coverage: { market_structure: { TRENDING: false, RANGING: false }, volatility: { LOW: false, MEDIUM: false, HIGH: false } } }, checks: [
      { criterion: "Deployment integrity", state: "PASSED", evidence: { deployment_id: "uuid", checksum: "abc123" } },
      { criterion: "Operational health", state: "PASSED", evidence: { heartbeat: "2026.08.16 00:00", telemetry: "AVAILABLE", emergency_stop: "true" } },
      { criterion: "Evidence sufficiency", state: "PENDING", evidence: { completed_trades: 0, required_trades: 30, observation_days: 0, required_days: 7 } },
      { criterion: "Performance / risk", state: "PENDING", evidence: { threshold_policy: "OWNER_CONFIGURATION_REQUIRED" } },
    ] };
    const page = markup(activeSnapshot, report);
    expect(page).toContain("Belum Cukup Bukti");
    expect(page).toContain("0 / 30");
    expect(page).toContain("0.0 / 7 hari");
    expect(page).toContain("eksekusi diblokir oleh Owner");
    expect(page).toContain("Performance belum dapat dinilai");
    expect(page).toContain("Lihat Technical Evidence");
    expect(page).toContain("Bukti Historis vs Bukti DEMO Aktual");
    expect(page).toContain("Trade historis dan trade DEMO tidak pernah digabungkan");
    expect(page).toContain("High volatility belum teramati");
    expect(page).not.toContain("Deploy to Live");
  });

  it("does not present owner review as LIVE and explains failed readiness", () => {
    const ready: Validation = { ...validation, status: "READY_FOR_OWNER_REVIEW", performance: { completed_trades: 30, net_realized_pnl: 12 }, checks: [] };
    const failed: Validation = { ...validation, status: "NOT_READY", checks: [] };
    expect(markup(activeSnapshot, ready)).toContain("Siap untuk Ditinjau Owner");
    expect(markup(activeSnapshot, ready)).toContain("tidak mengaktifkan LIVE trading");
    expect(markup(activeSnapshot, failed)).toContain("Ada kriteria penting yang belum lulus");
  });

  it("shows stale historical telemetry as disconnected rather than active", () => {
    const snapshot: Snapshot = { ...base, adapter: { status: "CONNECTED", imported: 0, error: null }, heartbeat: { id: "event-1", timestamp: "2026.08.11 21:18", observed_at: "2026-08-11T18:18:31Z", strategy_id: "bullish-reversal-m1", strategy_version: "v1", broker_symbol: "XAUUSD.m", environment: "DEMO", decision: "HEARTBEAT", detail: "cached config", positions: "0", emergency_stop: "true" }, active_deployment: { id: "deployment-1", strategy_version_id: "strategy-1", strategy_name: "Bullish Reversal M1", strategy_key: "bullish-reversal-m1", strategy_version: "v1", checksum: "abc123", broker_symbol: "XAUUSD.m", acknowledged_at: "2026-08-11T00:00:00Z" } };
    expect(commandCenterState(snapshot, "")).toBe("DISCONNECTED");
    expect(markup(snapshot)).toContain("heartbeat tidak dapat dibaca dalam 60 detik terakhir");
  });
});

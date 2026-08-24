import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CapitalSimulationEvidence, CapitalSimulationLab, isAcceptanceReady, type Verification } from "./capital-simulation-lab";

const pass = { status: "PASS" as const };
const verification: Verification = { status: "PASSED", owner_acceptance_readiness: "READY_FOR_OWNER_ACCEPTANCE", warning: "Integrity only", checks: { completed_result: pass, source_trade_invariant: pass, normalized_point_count: pass, contiguous_sequence: pass, exact_path_payloads: pass, exact_lineage: pass, broker_parity: pass, constraint_boundaries: pass, frozen_snapshot_disclosure: pass, lifecycle_safety: pass } };
const simulation = { id: "simulation-1", status: "COMPLETED_WITH_REJECTIONS", fingerprint: "f".repeat(64), capital_path_points: 3, result: { metrics: { source_trades_observed: 2, executed_trades: 1, rejected_trades: 1, rejections_by_reason: { INSUFFICIENT_MARGIN: 1 }, starting_capital: 10000, ending_balance: 10001, net_pnl: 1, maximum_drawdown: 0, capital_path_points: 3 }, lineage: { dataset_fingerprint: "d".repeat(64) }, boundaries: { demo_or_live_action: false }, warning: "Frozen snapshot historical evidence" } };

describe("CapitalSimulationLab", () => {
  it("renders the historical and lifecycle safety boundaries", () => { const markup = renderToStaticMarkup(<CapitalSimulationLab />); expect(markup).toContain("HISTORICAL ONLY · LIVE LOCKED"); expect(markup).toContain("does not claim VALIDATED"); expect(markup).toContain("historical broker-term changes are not reconstructed"); });
  it("requires the exact verifier schema and every check to pass", () => { expect(isAcceptanceReady(verification)).toBe(true); expect(isAcceptanceReady({ ...verification, checks: { ...verification.checks, exact_lineage: { status: "FAIL" } } })).toBe(false); const missing = { ...verification.checks }; delete missing.lifecycle_safety; expect(isAcceptanceReady({ ...verification, checks: missing })).toBe(false); });
  it("renders concrete metrics, rejection reason, lineage, and warning", () => { const markup = renderToStaticMarkup(<CapitalSimulationEvidence simulation={simulation} verification={verification} path={{ total: 3, capital_path: [{ sequence: 0 }, { sequence: 2 }] }} />); expect(markup).toContain("Ready for Owner acceptance"); expect(markup).toContain("INSUFFICIENT_MARGIN"); expect(markup).toContain("dataset_fingerprint"); expect(markup).toContain("not VALIDATED"); });
});

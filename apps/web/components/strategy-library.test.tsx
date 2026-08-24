import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GenericDecision, GenericEvidenceChain, GenericEvidenceVerification, latestRenderableOosEvidence, OosEvidence, RobustnessEvidence, StrategyLibrary } from "./strategy-library";

const split = (trade_count: number, net_pnl_price: number, profit_factor: number) => ({ metrics: { trade_count, net_pnl_price, profit_factor } });

const evidence: OosEvidence = {
  id: "12345678-1234-1234-1234-123456789012",
  fingerprint: "abcdef0123456789abcdef0123456789",
  protocol: { version: "OOS_HISTORICAL_REVIEW_V3" },
  result: {
    status: "VALIDATED",
    warning: "Historical evidence only; no deployment claim.",
    gate_evaluation: {
      decision: "PASS",
      checks: {
        minimum_trades: { status: "PASS", observed: { holdout: 125, final_oos: 120 } },
        profit_factor: { status: "PASS", observed: { holdout: 1.2, final_oos: 1.18 } },
        adverse_final_oos_nonnegative: { status: "PASS", observed: 1.5 },
      },
    },
    cost_stress: {
      scenarios: {
        baseline: { splits: { train: split(400, 12, 1.3), holdout: split(125, 4, 1.2), final_oos: split(120, 3, 1.18) } },
        adverse_cost: { splits: { train: split(400, 7, 1.2), holdout: split(125, 2, 1.12), final_oos: split(120, 1.5, 1.11) } },
      },
    },
  },
};

describe("StrategyLibrary", () => {
  it("keeps the factory explicit about its contract and safety boundary", () => {
    const markup = renderToStaticMarkup(<StrategyLibrary />);
    expect(markup).toContain("DRAFT CANDIDATE");
    expect(markup).toContain("Confirm immutable version");
    expect(markup).toContain("does not mark a version");
    expect(markup).toContain("NO LIVE ACTION");
    expect(markup).toContain("never create VALIDATED");
    expect(markup).toContain("future promotion requires a separate contract");
  });

  it("renders an inspectable PASS decision without implying deployment", () => {
    const markup = renderToStaticMarkup(<RobustnessEvidence evidence={evidence} />);
    expect(markup).toContain("OOS_HISTORICAL_REVIEW_V3");
    expect(markup).toContain("VALIDATED · HISTORICAL ONLY");
    expect(markup).toContain("Minimum 100 trades per OOS partition");
    expect(markup).toContain("Adverse final net");
    expect(markup).toContain("No automatic DEMO or LIVE action");
  });

  it("skips preserved pre-V3 evidence when reopening the latest gate result", () => {
    const legacy = { ...evidence, protocol: { version: "OOS_HISTORICAL_REVIEW_V2" } };
    expect(latestRenderableOosEvidence([legacy, evidence])).toBe(evidence);
    expect(latestRenderableOosEvidence([legacy])).toBeUndefined();
  });

  it.each(["FAIL", "INSUFFICIENT_EVIDENCE"] as const)("renders generic %s evidence as NOT VALIDATED with a separate Owner boundary", outcome => {
    const decision: GenericDecision = {
      id: "decision-12345678", strategy_version_id: "strategy-1", oos_validation_id: "oos-1", robustness_evidence_id: "stability-1", fingerprint: "decision-fingerprint", protocol_version: "GENERIC_EVIDENCE_DECISION_V1", decision: outcome,
      result: { source_outcomes: { generic_oos: outcome, parameter_stability: outcome }, thresholds: {}, observations: {}, lineage: {}, owner_gate: { acknowledgement_required: true, acknowledgement_creates_validation: false, future_promotion_workflow_required: true }, lifecycle: { validated_created: false } },
    };
    const verifier: GenericEvidenceVerification = { id: "verifier-1", decision_id: decision.id, fingerprint: "verifier-fingerprint", verifier_version: "GENERIC_EVIDENCE_ACCEPTANCE_VERIFIER_V1", status: "PASSED", owner_acceptance_readiness: "READY_FOR_OWNER_ACCEPTANCE", evidence_outcome: outcome, owner_boundary: { acknowledgement_required: true, acknowledgement_present: false, acknowledgement_is_not_validation: true, future_promotion_contract_required: true }, checks: { lifecycle_safety: { status: "PASS" } }, warning: "Integrity only; not trading authority." };
    const markup = renderToStaticMarkup(<GenericEvidenceChain chain={{ strategyVersionId: "strategy-1", decision, verifier }} />);
    expect(markup).toContain(outcome);
    expect(markup).toContain("NOT VALIDATED");
    expect(markup).toContain("separate future promotion contract");
    expect(markup).toContain("No VALIDATED claim");
  });
});

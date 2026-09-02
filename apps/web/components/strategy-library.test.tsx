import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EXPRESSIONS, GenericDecision, GenericEvidenceChain, PARAMETER_FIELDS, supportsChoices, GenericEvidenceVerification, latestRenderableOosEvidence, LifecycleGovernance, LifecycleVerification, OosEvidence, RobustnessEvidence, StrategyLibrary } from "./strategy-library";

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
    expect(markup).toContain("cannot promote by themselves");
    expect(markup).toContain("VALIDATED always means historical validation only");
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
    expect(markup).toContain("separate explicit promotion authorization");
    expect(markup).toContain("No VALIDATED claim");
  });

  it.each([
    ["CONTRACT_VALID", "NOT_VALIDATED", "INELIGIBLE", "NONE", "NONE"],
    ["VALIDATED", "HISTORICAL_VALIDATION_ONLY", "ELIGIBLE", "HISTORICALLY_VALIDATED", "NONE"],
    ["RETIRED", "RETIRED_IMMUTABLE", "ELIGIBLE", "HISTORICALLY_VALIDATED", "RETIRED"],
  ])("renders %s lifecycle with exact artifacts and execution boundaries", (status, claim, eligibilityStatus, promotionStatus, retirementStatus) => {
    const artifact = (id: string, artifactStatus: string) => ({ id, fingerprint: `${id}-fingerprint`, status: artifactStatus, result: {} });
    const verification: LifecycleVerification = {
      id: "lifecycle-1", strategy_version_id: "strategy-1", fingerprint: "lifecycle-fingerprint", verifier_version: "GENERIC_VALIDATION_LIFECYCLE_VERIFIER_V1", status: "PASSED", owner_acceptance_readiness: "READY_FOR_OWNER_ACCEPTANCE", lifecycle_status: status, lifecycle_claim: claim,
      checks: { transition_coherence: { status: "PASS" }, safety_boundaries: { status: "PASS" } },
      artifacts: { eligibility: artifact("eligibility", eligibilityStatus), promotion: promotionStatus === "NONE" ? null : artifact("promotion", promotionStatus), retirement: retirementStatus === "NONE" ? null : { ...artifact("retirement", retirementStatus), reason: "Owner retirement reason" } },
      safety_boundary: { historical_only: true, demo_or_live_authorized: false, capital_authorized: false, router_or_trade_decision_created: false, deployment_created: false, profitability_proven: false }, warning: "Governance only; no trading authority.",
    };
    const markup = renderToStaticMarkup(<LifecycleGovernance verification={verification} />);
    expect(markup).toContain(status); expect(markup).toContain(claim); expect(markup).toContain(eligibilityStatus);
    expect(markup).toContain("profitability is not proven"); expect(markup).toContain("trade authority are all false");
  });
});

describe("Strategy Factory choices (ARK-S27)", () => {
  it("offers direction and execution timeframe, and says when they do not apply", () => {
    const markup = renderToStaticMarkup(<StrategyLibrary />);
    expect(markup).toContain("Arah");
    expect(markup).toContain("Timeframe eksekusi");
    expect(markup).toContain("LONG (beli)");
    expect(markup).toContain("SHORT (jual)");
    expect(markup).toContain("Harga vs EMA 31 + range minimal");
    // The legacy expression is selected first, and it cannot honour either
    // choice, so the controls must read as disabled rather than as ignored.
    expect(markup).toContain("terkunci di XAUUSD LONG M1");
  });

  it("keeps the legacy expression out of the generic choices", () => {
    expect(supportsChoices("LEGACY")).toBe(false);
    expect(supportsChoices("M1_M5_COMPLETED")).toBe(true);
    expect(supportsChoices("EMA_MINIMUM_RANGE")).toBe(true);
  });
});

describe("Strategy Factory parameters (ARK-S27-04)", () => {
  it("exposes a field for every number a generic expression actually reads", () => {
    // "31" was given as an example and shipped as the only period. A number the
    // Owner cannot change is a number the Owner cannot test, and a backtest of
    // it measures my arbitrary choice rather than their idea.
    expect(PARAMETER_FIELDS.EMA_MINIMUM_RANGE.map(([key]) => key)).toEqual(["maPeriod", "rangeLookback", "rangeDistance"]);
    expect(PARAMETER_FIELDS.M1_M5_COMPLETED.map(([key]) => key)).toEqual(["smaFast", "smaSlow"]);
  });

  it("shows no parameter fields for an expression that reads none", () => {
    // A field the contract ignores is worse than a hidden one: the Owner would
    // change it and see nothing move.
    expect(PARAMETER_FIELDS.LEGACY).toEqual([]);
    const markup = renderToStaticMarkup(<StrategyLibrary />);
    expect(markup).not.toContain("Periode EMA");
  });

  it("declares a field for every expression, so a new one cannot ship unlabelled", () => {
    expect(Object.keys(PARAMETER_FIELDS).sort()).toEqual([...EXPRESSIONS].sort());
    for (const fields of Object.values(PARAMETER_FIELDS)) {
      for (const [, label, step] of fields) {
        expect(label.length).toBeGreaterThan(0);
        expect(Number(step)).toBeGreaterThan(0);
      }
    }
  });
});

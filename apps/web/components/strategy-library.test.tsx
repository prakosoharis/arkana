import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { latestRenderableOosEvidence, OosEvidence, RobustnessEvidence, StrategyLibrary } from "./strategy-library";

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
    expect(markup).toContain("VALIDATED is historical-only");
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
});

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EdgeSearchConsoleView, gateObservation, verdictLabel } from "./edge-search-console";

const OVERVIEW = {
  count: 1,
  warning: "Searching creates no authority.",
  campaigns: [{
    campaign: { campaign_id: "320d1159-de1f-4a15-924b-7731933287d8", fingerprint: "9c679ecda501991052d1749b632068e1", status: "PRE_REGISTERED", trial_count: 384, spread_assumption: "0.25", grid: { dimensions: { stop_scale: [10, 20, 40, 80] } } },
    progress: { recorded: 384, pre_registered: 384, complete: true, by_status: { EXECUTED: 192, INSUFFICIENT_EVIDENCE: 192 }, survivor_count: 73, mean_seconds_per_trial: 250 },
    survivors: {
      survivor_count: 73,
      ranked: [{ rank: 1, trial_id: "t-1", trial_index: 360, status: "EXECUTED", parameters: { stop_scale: 80 }, result: { splits: { holdout: { metrics: { trade_count: 138, net_pnl_price: 840.46, profit_factor: 1.4699, win_rate: 0.4275 } } } } }],
      selection_disclosure: { trials_pre_registered: 384, trials_recorded: 384, final_oos_budget: 3, final_oos_consumed: 1, final_oos_remaining: 2, spread_assumption: "0.25", multiple_testing_note: "any survivor is one of 384 pre-registered hypotheses; a single pass is weak evidence consistent with multiple testing" },
    },
    final_oos_outcomes: [{
      outcome_id: "o-1", trial_index: 360, gate_decision: "FAIL", parameters: { stop_scale: 80 },
      gate_checks: { profit_factor: { status: "FAIL", observed: { final_oos: 1.0519 } }, year_pnl_concentration: { status: "FAIL", maximum_observed: 0.6594, maximum_allowed: 0.5 } },
      splits: { train: { trade_count: 299, net_pnl_price: 807.47, profit_factor: 1.1907, win_rate: 0.3746 }, holdout: { trade_count: 138, net_pnl_price: 840.46, profit_factor: 1.4699, win_rate: 0.4275 }, final_oos: { trade_count: 1211, net_pnl_price: 932.38, profit_factor: 1.0519, win_rate: 0.3452 } },
      budget: { sequence: 1, budget: 3, remaining_after: 2 },
      strategy_version_id: "19be930b-0000-0000-0000-000000000000", strategy_status: "CONTRACT_VALID", oos_fingerprint: "44c0f76ca18c5a30",
    }],
    conclusion: { conclusion: "NO_EDGE_FOUND", fingerprint: "8cf4b7870f739188796b1ffaceca3aed" },
    assessment: { conclusion: "NO_EDGE_FOUND", budget: { consumed: 1, budget: 3, remaining: 2 } },
    verification: { status: "PASSED", fingerprint: "abc123def456", checks: { verdict_recomputes: { status: "PASS" } } },
  }],
};

function markup(data = OVERVIEW) {
  return renderToStaticMarkup(<EdgeSearchConsoleView data={data as never} onRefresh={() => undefined} onVerify={() => undefined} busy={false} />);
}

describe("verdictLabel", () => {
  it("never presents NO_EDGE_FOUND as a platform failure", () => {
    expect(verdictLabel("NO_EDGE_FOUND")).toContain("BUKAN KEGAGALAN");
  });
  it("keeps a found candidate scoped to historical evidence", () => {
    expect(verdictLabel("EDGE_CANDIDATE_FOUND")).toContain("BUKTI HISTORIS");
  });
});

describe("gateObservation", () => {
  it("reads the concentration checks, which report maximum_observed", () => {
    expect(gateObservation({ status: "FAIL", maximum_observed: 0.6594, maximum_allowed: 0.5 })).toBe("0.6594 (max 0.5)");
  });
  it("still reads a plain observed value", () => {
    expect(gateObservation({ status: "PASS", observed: 819.055 })).toBe("819.055");
  });
  it("returns nothing when the gate reported no number", () => {
    expect(gateObservation({ status: "PASS" })).toBeNull();
  });
});

describe("EdgeSearchConsoleView", () => {
  it("shows the verdict and the spent budget", () => {
    const html = markup();
    expect(html).toContain("TIDAK ADA EDGE DITEMUKAN");
    expect(html).toContain("1 / 3");
  });

  it("never shows a survivor without its selection disclosure", () => {
    expect(markup()).toContain("384 pre-registered hypotheses");
  });

  it("shows why the gate refused, not only that it refused", () => {
    const html = markup();
    expect(html).toContain("profit factor");
    expect(html).toContain("year pnl concentration");
    expect(html).toContain("1.0519");
    // the number that actually refused the strategy must be visible
    expect(html).toContain("0.6594");
  });

  it("states that no strategy was promoted", () => {
    const html = markup();
    expect(html).toContain("never promotes automatically");
    expect(html).toContain("CONTRACT_VALID");
  });

  it("declares that no validated strategy was created", () => {
    expect(markup()).toContain("NO VALIDATED STRATEGY CREATED");
  });
});

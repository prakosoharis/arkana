import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { judge, LevelTouchLab, resolvedShare } from "./level-touch-lab";

const row = (over: Partial<Parameters<typeof judge>[0]> = {}) => ({
  event: "BOUNCE_FROM_ABOVE", distance: "FIXED_5", timeout_bars: 24,
  events: 8366, target_first: 3389, stop_first: 3693, unresolved: 1284, beyond_data: 0,
  target_rate: 0.405, target_rate_of_resolved: 0.479,
  ...over,
} as Parameters<typeof judge>[0]);

describe("judge", () => {
  it("refuses to grade a row with too few finished cases", () => {
    const state = judge(row({ target_first: 40, stop_first: 30 }), 300);
    expect(state.label).toBe("SAMPEL KURANG");
  });

  it("calls a below-even row exactly that", () => {
    // The real measurement: an EMA touch resolves in the trader's favour 47.9%
    // of the time, because the stop wins an ambiguous bar and the spread is paid.
    expect(judge(row(), 300).label).toBe("TIDAK UNGGUL");
  });

  it("separates barely-above-even from genuinely interesting", () => {
    expect(judge(row({ target_rate_of_resolved: 0.52 }), 300).label).toBe("TIPIS");
    expect(judge(row({ target_rate_of_resolved: 0.57 }), 300).label).toBe("MENARIK");
  });
});

describe("resolvedShare", () => {
  it("says what fraction of touches finished at all", () => {
    // 40% of touches never reach either barrier in time, and a winrate quoted
    // without that number would look like a plan it is not.
    expect(resolvedShare(row())).toBeCloseTo(0.847, 3);
    expect(resolvedShare(row({ events: 0 }))).toBeNull();
  });
});

describe("LevelTouchLab", () => {
  it("states the pessimistic rules on the form, not in a footnote", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Uji Sentuhan Garis");
    expect(markup).toContain("PENGUKURAN SAJA");
    expect(markup).toContain("SL yang menang");
    expect(markup).toContain("60% data pertama");
    expect(markup).toContain("winrate adalah satu-satunya angka yang penting");
  });

  it("does not offer to deploy, validate or confirm anything", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    for (const forbidden of ["Deploy", "Confirm", "VALIDATED"]) {
      expect(markup).not.toContain(forbidden);
    }
  });
});

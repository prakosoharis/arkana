import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FollowPanel, MarketExplorer, RunsPanel, sortRows, verdict } from "./market-explorer";

const row = (over: Partial<Parameters<typeof verdict>[0]> = {}) => ({
  key: 0, label: "12:40", bars: 2185, up: 1100, down: 1085, flat: 0,
  up_rate: 0.503, down_rate: 0.497, mean_range: 1.9, mean_body: 0.01,
  sufficient_sample: true,
  consistency: { years_measured: 7, sufficient_years: true, minimum_up_rate: 0.48, maximum_up_rate: 0.52, spread: 0.04, years_above_half: 4 },
  per_year: {},
  ...over,
} as Parameters<typeof verdict>[0]);

describe("verdict", () => {
  it("refuses to call a thin row anything but thin", () => {
    const state = verdict(row({ bars: 12, sufficient_sample: false }), 200);
    expect(state.label).toBe("SAMPEL KURANG");
    expect(state.tone).toBe("weak");
  });

  it("refuses a row measured across too few years", () => {
    const state = verdict(row({ consistency: { years_measured: 1, sufficient_years: false, minimum_up_rate: null, maximum_up_rate: null, spread: null, years_above_half: null } }), 200);
    expect(state.label).toBe("TAHUN KURANG");
  });

  it("calls a rate that moves 30 points between years inconsistent", () => {
    // The failure the Owner must be protected from: one good year averaged
    // into several ordinary ones still reads as a high rate on its own.
    const state = verdict(row({ consistency: { years_measured: 7, sufficient_years: true, minimum_up_rate: 0.35, maximum_up_rate: 0.65, spread: 0.3, years_above_half: 2 } }), 200);
    expect(state.label).toBe("TIDAK KONSISTEN");
    expect(state.tone).toBe("weak");
  });

  it("only calls a row consistent when the sample, the years and the spread all hold", () => {
    expect(verdict(row(), 200).label).toBe("KONSISTEN");
    expect(verdict(row(), 200).tone).toBe("strong");
  });
});

describe("sortRows", () => {
  const rows = [row({ key: 1, label: "01:00", down_rate: 0.4, up_rate: 0.6, mean_range: 1 }),
                row({ key: 2, label: "02:00", down_rate: 0.7, up_rate: 0.3, mean_range: 3 }),
                row({ key: 3, label: "03:00", down_rate: 0.5, up_rate: 0.5, mean_range: 2 })];

  it("ranks by the column asked for and leaves the input alone", () => {
    expect(sortRows(rows, "down").map(item => item.key)).toEqual([2, 3, 1]);
    expect(sortRows(rows, "up").map(item => item.key)).toEqual([1, 3, 2]);
    expect(sortRows(rows, "range").map(item => item.key)).toEqual([2, 3, 1]);
    expect(sortRows(rows, "time").map(item => item.key)).toEqual([1, 2, 3]);
    expect(rows.map(item => item.key)).toEqual([1, 2, 3]);
  });
});

describe("MarketExplorer", () => {
  it("says on first paint that it measures and nothing more", () => {
    const markup = renderToStaticMarkup(<MarketExplorer />);
    expect(markup).toContain("Eksplorasi Market");
    expect(markup).toContain("PENGUKURAN SAJA");
    expect(markup).toContain("Belum ada strategi");
    expect(markup).not.toContain("Deploy");
  });

  it("reports a run length beside how often it happened, never alone", () => {
    const markup = renderToStaticMarkup(<RunsPanel runs={{
      UP: { total: 100, mean_length: 1.95, lengths: [{ length: 1, occurrences: 51, closed_runs: 51, mean_move: 0.95 }] },
      DOWN: { total: 100, mean_length: 1.92, lengths: [{ length: 1, occurrences: 51, closed_runs: 50, mean_move: 0.94 }] },
    }} />);
    expect(markup).toContain("Rentetan candle hijau");
    expect(markup).toContain("1.95");
    expect(markup).toContain("51");
  });

  it("states how big is measured rather than leaving it to be assumed", () => {
    const markup = renderToStaticMarkup(<FollowPanel
      rows={[{ key: "UP_BESAR", bars: 42529, up_rate: 0.48, down_rate: 0.513, mean_range: 2, mean_body: -0.01, sufficient_sample: true }]}
      minimumSamples={200}
      policy={{ minimum_samples: 200, minimum_years: 3, size_window: 20, large_multiple: 1.5, small_multiple: 0.5 }} />);
    expect(markup).toContain("20 candle sebelumnya");
    expect(markup).toContain("1.5");
    expect(markup).toContain("Hijau besar");
    expect(markup).toContain("42.529");
  });
});

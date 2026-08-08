import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BacktestLab } from "./backtest-lab";

describe("BacktestLab", () => {
  it("renders an explicitly non-executable deterministic experiment", () => {
    const markup = renderToStaticMarkup(<BacktestLab />);
    expect(markup).toContain("BULLISH REVERSAL M1");
    expect(markup).toContain("Run deterministic backtest");
    expect(markup).toContain("cannot activate a strategy");
  });
});

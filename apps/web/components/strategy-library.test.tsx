import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StrategyLibrary } from "./strategy-library";

describe("StrategyLibrary", () => {
  it("keeps the factory explicit about its contract and safety boundary", () => {
    const markup = renderToStaticMarkup(<StrategyLibrary />);
    expect(markup).toContain("DRAFT CANDIDATE");
    expect(markup).toContain("Confirm immutable version");
    expect(markup).toContain("does not mark it");
    expect(markup).toContain("NO LIVE ACTION");
  });
});

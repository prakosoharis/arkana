import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeploymentLab } from "./deployment-lab";

describe("DeploymentLab", () => {
  it("renders demo-only deployment controls", () => {
    const markup = renderToStaticMarkup(<DeploymentLab />);
    expect(markup).toContain("Deploy to Demo");
    expect(markup).toContain("LIVE = LOCKED");
    expect(markup).not.toContain("Deploy to Live");
  });
});

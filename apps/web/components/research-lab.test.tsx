import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResearchLab } from "./research-lab";

describe("ResearchLab", () => {
  it("renders a question-first research workspace", () => {
    const markup = renderToStaticMarkup(<ResearchLab />);
    expect(markup).toContain("What do you want to investigate?");
    expect(markup).toContain("Build interpretation");
    expect(markup).not.toContain("Entry trigger");
  });
});

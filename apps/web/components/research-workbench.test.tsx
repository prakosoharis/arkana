import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResearchWorkbench } from "./research-workbench";

describe("ResearchWorkbench", () => {
  it("puts both strategy-free measurements behind one menu", () => {
    // They shipped as two sidebar entries a sprint apart, which is how the
    // navigation came to be ordered by what was built rather than by what the
    // Owner is trying to find out.
    const markup = renderToStaticMarkup(<ResearchWorkbench />);
    expect(markup).toContain("Riset Pasar");
    expect(markup).toContain("Pola &amp; Waktu");
    expect(markup).toContain("Sentuhan Garis");
  });

  it("opens on the tab it was asked for", () => {
    // The embedded labs no longer carry their own headings, so the tab is
    // identified by the controls it owns.
    expect(renderToStaticMarkup(<ResearchWorkbench />)).toContain("Pilih timeframe dan jam");
    expect(renderToStaticMarkup(<ResearchWorkbench />)).not.toContain("Susun percobaan Anda");
    expect(renderToStaticMarkup(<ResearchWorkbench initial="sentuhan" />)).toContain("Susun percobaan Anda");
    expect(renderToStaticMarkup(<ResearchWorkbench initial="sentuhan" />)).not.toContain("Pilih timeframe dan jam");
  });

  it("carries the safety boundary once, at the top, for both tabs", () => {
    const markup = renderToStaticMarkup(<ResearchWorkbench />);
    expect(markup).toContain("PENGUKURAN SAJA");
    expect(markup).toContain("Belum ada strategi, belum ada sinyal");
  });
});

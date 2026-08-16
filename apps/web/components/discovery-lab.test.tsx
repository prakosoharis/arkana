import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DiscoveryLab } from "./discovery-lab";

describe("DiscoveryLab", () => {
  it("renders the two owner-facing research goals and keeps advanced detail optional", () => {
    const markup = renderToStaticMarkup(<DiscoveryLab />);
    expect(markup).toContain("Cari Pola Historis");
    expect(markup).toContain("Cari Kondisi yang Mirip");
    expect(markup).toContain("Pengaturan Lanjutan");
    expect(markup).toContain("bukan prediksi atau instruksi trading");
    expect(markup).not.toContain("BUY");
  });
});

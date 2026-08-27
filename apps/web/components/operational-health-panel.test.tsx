import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OperationalHealthPanelView, healthLabel } from "./operational-health-panel";

const CRITICAL = {
  status: "CRITICAL" as const,
  evaluated_at: "2026-08-27T21:30:00Z",
  warning: "Operational health reports conditions only.",
  checks: { backup: { status: "FRESH" }, heartbeat: { status: "STALE" }, incidents: { status: "NONE_OPEN" }, dataset: { status: "FRESH" } },
  conditions: [{
    code: "HEARTBEAT_STALE", severity: "CRITICAL" as const,
    detail: "3 deployment(s) are DEMO_ACTIVE but MT5 telemetry stopped arriving.",
    evidence: { active_demo_deployments: 3, age_seconds: 1391488.9 },
  }],
};

describe("healthLabel", () => {
  it("makes a critical state impossible to mistake for routine", () => {
    expect(healthLabel("CRITICAL")).toBe("PERLU TINDAKAN");
    expect(healthLabel("WARNING")).toBe("PERLU DIPERHATIKAN");
    expect(healthLabel("OK")).toBe("SEHAT");
  });
});

describe("OperationalHealthPanelView", () => {
  it("shows the condition detail, not only its code", () => {
    const html = renderToStaticMarkup(<OperationalHealthPanelView health={CRITICAL} />);
    expect(html).toContain("PERLU TINDAKAN");
    expect(html).toContain("DEMO_ACTIVE but MT5 telemetry stopped arriving");
    expect(html).toContain("heartbeat");
  });

  it("says plainly when nothing is open", () => {
    const html = renderToStaticMarkup(<OperationalHealthPanelView health={{ ...CRITICAL, status: "OK", conditions: [] }} />);
    expect(html).toContain("No operational condition is open");
  });
});

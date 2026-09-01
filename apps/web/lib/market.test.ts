import { describe, expect, it } from "vitest";
import { displayBrokerTime, displayTime, evidenceDataset } from "./market";

describe("displayTime", () => {
  it("shows an empty value honestly", () => {
    expect(displayTime()).toBe("—");
  });
});

describe("displayBrokerTime", () => {
  it("never converts a broker-time-naive timestamp through JavaScript Date", () => {
    expect(displayBrokerTime("2026-08-12T01:49:00")).toBe("2026-08-12 01:49:00");
  });
});

describe("evidenceDataset", () => {
  const base = { timezone_status: "UNVERIFIED_BROKER_TIME", imported_at: "2026-01-01T00:00:00Z", timeframes: [] };
  // The registry is newest-first, which is how the Market & Data page came to
  // report the Owner's data source as "S13-03 pass fixture" with 1,000 rows.
  const registry = [
    { ...base, id: "fixture", symbol: "XAUUSD", source: "S13-03 pass fixture", evidence_grade: false },
    { ...base, id: "real", symbol: "XAUUSD", source: "MT5", evidence_grade: true },
    { ...base, id: "eur", symbol: "EURUSD", source: "MT5", evidence_grade: true },
  ];

  it("skips a newer fixture in favour of real evidence", () => {
    expect(evidenceDataset(registry, "XAUUSD")?.id).toBe("real");
  });

  it("is scoped to the requested symbol", () => {
    expect(evidenceDataset(registry, "EURUSD")?.id).toBe("eur");
  });

  it("still returns something when every dataset is a fixture", () => {
    const only = [{ ...base, id: "fixture", symbol: "XAUUSD", source: "TEST", evidence_grade: false }];
    expect(evidenceDataset(only, "XAUUSD")?.id).toBe("fixture");
  });

  it("treats a dataset from an API without the flag as usable", () => {
    const legacy = [{ ...base, id: "legacy", symbol: "XAUUSD", source: "MT5" }];
    expect(evidenceDataset(legacy, "XAUUSD")?.id).toBe("legacy");
  });

  it("returns undefined when the symbol is absent", () => {
    expect(evidenceDataset(registry, "GBPUSD")).toBeUndefined();
  });
});

describe("deployment acknowledgement text", () => {
  // ARK-S24-09: a partial acknowledgement rendered the literal "undefined".
  const ackText = (ack: { strategy_version?: string; checksum?: string; broker_symbol?: string }) =>
    `EA acknowledged ${ack.strategy_version ?? "NOT_REPORTED"} / ${ack.broker_symbol ?? "NOT_REPORTED"} / ${ack.checksum ?? "NOT_REPORTED"}`;

  it("never renders the literal undefined for a partial acknowledgement", () => {
    const text = ackText({ checksum: "8632" });
    expect(text).not.toContain("undefined");
    expect(text).toBe("EA acknowledged NOT_REPORTED / NOT_REPORTED / 8632");
  });

  it("renders every field when the acknowledgement is complete", () => {
    expect(ackText({ strategy_version: "1.0.0", broker_symbol: "XAUUSD.m", checksum: "8917" }))
      .toBe("EA acknowledged 1.0.0 / XAUUSD.m / 8917");
  });
});

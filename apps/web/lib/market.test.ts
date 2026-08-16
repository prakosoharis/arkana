import { describe, expect, it } from "vitest";
import { displayBrokerTime, displayTime } from "./market";

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

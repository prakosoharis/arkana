import { describe, expect, it } from "vitest";
import { displayTime } from "./market";

describe("displayTime", () => {
  it("shows an empty value honestly", () => {
    expect(displayTime()).toBe("—");
  });
});

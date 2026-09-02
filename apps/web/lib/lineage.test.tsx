import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FIXTURE_LABEL, FixtureBadge, isFixture, optionSuffix, type Lineage } from "./lineage";

const fixture: Lineage = {
  classification: "SYNTHETIC_CHECKSUM",
  is_fixture: true,
  may_satisfy_generic_gate: false,
  reasons: ["checksum is 12 characters and is not a SHA-256 digest"],
};

const real: Lineage = {
  classification: "REAL_LINEAGE",
  is_fixture: false,
  may_satisfy_generic_gate: true,
  reasons: [],
};

describe("lineage", () => {
  it("marks a fixture and leaves a real record alone", () => {
    expect(isFixture(fixture)).toBe(true);
    expect(isFixture(real)).toBe(false);
  });

  it("says nothing when the row predates the lineage field", () => {
    // A response served by an older API must not silently read as "real"
    // *or* as "fixture"; absence of the field is absence of the claim.
    expect(isFixture(undefined)).toBe(false);
    expect(optionSuffix(undefined)).toBe("");
    expect(renderToStaticMarkup(<FixtureBadge lineage={undefined} />)).toBe("");
  });

  it("renders the badge with the classifier's own reason", () => {
    const markup = renderToStaticMarkup(<FixtureBadge lineage={fixture} />);
    expect(markup).toContain(FIXTURE_LABEL);
    expect(markup).toContain("BUKAN BUKTI NYATA");
    expect(markup).toContain("not a SHA-256 digest");
  });

  it("renders nothing at all for a real record", () => {
    expect(renderToStaticMarkup(<FixtureBadge lineage={real} />)).toBe("");
    expect(optionSuffix(real)).toBe("");
  });

  it("suffixes a plain option, which cannot carry markup", () => {
    expect(optionSuffix(fixture)).toBe(` · ${FIXTURE_LABEL}`);
  });
});

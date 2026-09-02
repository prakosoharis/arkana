/**
 * ARK-S26-00. Six strategy versions in the production ledger carry the status
 * VALIDATED and are fixtures: rows written to exercise a code path, over
 * fabricated bars or with a checksum that is not a digest. Every picker in the
 * application rendered them beside real records with nothing to tell them apart.
 *
 * The classifier already knew. The surfaces simply never asked, so the fact
 * travels with the row now and every picker renders it the same way.
 */
import React from "react";

export type Lineage = {
  classification: string;
  is_fixture: boolean;
  may_satisfy_generic_gate: boolean;
  reasons: string[];
};

export const FIXTURE_LABEL = "DATA UJI COBA";

export function isFixture(lineage?: Lineage | null): boolean {
  return lineage?.is_fixture === true;
}

/** The suffix for a plain <option>, which cannot carry markup. */
export function optionSuffix(lineage?: Lineage | null): string {
  return isFixture(lineage) ? ` · ${FIXTURE_LABEL}` : "";
}

export function FixtureBadge({ lineage }: { lineage?: Lineage | null }) {
  if (!isFixture(lineage)) return null;
  return (
    <span className="fixture-badge" title={lineage?.reasons?.join("; ")}>
      {FIXTURE_LABEL} · BUKAN BUKTI NYATA
    </span>
  );
}

export const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export type Bar = { timestamp: string; open: number; high: number; low: number; close: number; tick_volume?: number | null };
export type DatasetTimeframe = { timeframe: Timeframe; row_count: number; range_start: string; range_end: string };
export type Dataset = { id: string; symbol: string; source: string; timezone_status: string; imported_at: string; timeframes: DatasetTimeframe[]; evidence_grade?: boolean; synthetic_reason?: string | null; future_dated?: boolean };

// ARK-S24-07.  The registry listing is newest-first and deliberately includes
// fixtures, so taking the first row takes a fixture.  The backend decides what
// counts as evidence -- there is one rule for that and it is not in TypeScript.
// A dataset from an older API without the flag is treated as usable, so this
// can never blank the page.
export function evidenceDataset(datasets: Dataset[], symbol: string): Dataset | undefined {
  const forSymbol = datasets.filter(item => item.symbol === symbol);
  return forSymbol.find(item => item.evidence_grade !== false) ?? forSymbol[0];
}
export type BarsResponse = { bars: Bar[]; meta: { status: "READY" | "NO_DATA"; source?: string; timezone_status?: string; range_start?: string; range_end?: string } };

export function displayTime(value?: string | null): string {
  return value ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) : "—";
}

// MT5 historical timestamps are deliberately broker-time-naive.  Do not parse
// or relabel them as UTC/local time in the presentation layer.
export function displayBrokerTime(value?: string | null): string {
  return value ? value.replace("T", " ").replace(/\.\d+$/, "") : "—";
}

export const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export type Bar = { timestamp: string; open: number; high: number; low: number; close: number; tick_volume?: number | null };
export type DatasetTimeframe = { timeframe: Timeframe; row_count: number; range_start: string; range_end: string };
export type Dataset = { id: string; symbol: string; source: string; timezone_status: string; imported_at: string; timeframes: DatasetTimeframe[] };
export type BarsResponse = { bars: Bar[]; meta: { status: "READY" | "NO_DATA"; source?: string; timezone_status?: string; range_start?: string; range_end?: string } };

export function displayTime(value?: string): string {
  return value ? new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) : "—";
}

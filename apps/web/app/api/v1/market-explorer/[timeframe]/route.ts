import { NextRequest, NextResponse } from "next/server";

// A first M1 measurement reads 3M bars and takes about twenty seconds, which is
// well past Next's default fetch behaviour on a slow upstream, so this route
// exists mainly to carry the refresh flag through and to keep the wait honest.
export const maxDuration = 120;

export async function GET(request: NextRequest, { params }: { params: Promise<{ timeframe: string }> }) {
  const { timeframe } = await params;
  const refresh = request.nextUrl.searchParams.get("refresh") === "true" ? "?refresh=true" : "";
  try {
    const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/market-explorer/${encodeURIComponent(timeframe)}${refresh}`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

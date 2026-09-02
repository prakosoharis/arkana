import { NextRequest, NextResponse } from "next/server";

// A first M1 measurement walks 1.8M bars and takes about a minute.
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  const refresh = request.nextUrl.searchParams.get("refresh") === "true" ? "?refresh=true" : "";
  try {
    const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/level-touch${refresh}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(await request.json()), cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

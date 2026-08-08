import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const upstream = new URL("/api/v1/bars", process.env.RESEARCH_API_URL ?? "http://localhost:8000");
  upstream.search = request.nextUrl.search;
  try {
    const response = await fetch(upstream, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

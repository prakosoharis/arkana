import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const upstream = new URL("/api/v1/imports/csv", process.env.RESEARCH_API_URL ?? "http://localhost:8000");
  upstream.search = request.nextUrl.search;
  try {
    const body = await request.formData();
    const response = await fetch(upstream, { method: "POST", body, cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const upstream = new URL(`/api/v1/research-runs/${id}/samples`, process.env.RESEARCH_API_URL ?? "http://localhost:8000");
  upstream.search = request.nextUrl.search;
  try {
    const response = await fetch(upstream, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 });
  }
}

import { NextRequest, NextResponse } from "next/server";

const upstream = `${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-candidates`;

export async function GET() {
  try { const response = await fetch(upstream, { cache: "no-store" }); return NextResponse.json(await response.json(), { status: response.status }); }
  catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); }
}

export async function POST(request: NextRequest) {
  try { const response = await fetch(upstream, { method: "POST", headers: { "content-type": "application/json" }, body: await request.text(), cache: "no-store" }); return NextResponse.json(await response.json(), { status: response.status }); }
  catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); }
}

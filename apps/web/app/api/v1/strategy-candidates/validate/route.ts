import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${process.env.RESEARCH_API_URL ?? "http://localhost:8000"}/api/v1/strategy-candidates/validate`, { method: "POST", headers: { "content-type": "application/json" }, body: await request.text(), cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch { return NextResponse.json({ detail: "Research service is unavailable" }, { status: 503 }); }
}
